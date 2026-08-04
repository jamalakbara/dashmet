"""On-demand AI diagnosis over already-computed insights numbers.

This service narrates; it never computes metrics. It is handed dicts produced by
the shared read path (`insights.get_overview`, `insights.get_table`,
`insights.get_timeseries` — the *same* functions the Overview page and PPTX use)
and asks OpenAI to DIAGNOSE what changed vs the prior period and why — using ONLY
the figures already in those dicts. The model does no arithmetic and states no
number that isn't provided (P-1/P-6/P-7).

Two entry points:
  * `generate_overview_diagnosis` — the on-screen card. Returns a STRUCTURED dict
    with exactly the keys `headline`, `driver`, `watch`, `next_step` (each a short
    diagnostic paragraph). The "driver" is SELECTED from the per-campaign data
    handed in — the model picks the campaign whose already-given change best
    explains the account move; it does not compute or rank numerically.
  * `generate_narrative` — the PPTX deck. Returns `{section: prose}` for the
    requested slide sections, grounded in the same enriched bundle.

Trust rules baked in here:
  * P-4 / anti-fake-zero — on ANY failure (missing key, timeout, API error,
    empty/unparseable completion, blank field) we raise `AISummaryError`. We
    never return placeholder or empty text dressed up as a real summary.
  * P-7 — this module imports no repository and runs no SQL. It only transforms
    the dicts it's given and calls OpenAI. The only backend imports are the
    formatting helpers (so wording matches the UI/PPTX) and `settings`. The only
    arithmetic here is turning two already-computed figures into a display
    "% change" string for the model to QUOTE — the model itself never computes.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from openai import OpenAI, OpenAIError

from app.config import settings
from app.services.export import (
    _fmt_money,
    _fmt_number,
    _fmt_percent,
    _fmt_roas,
)

logger = logging.getLogger(__name__)

# Fail fast rather than hang a request thread on a stalled OpenAI call.
_REQUEST_TIMEOUT = 30.0

# Rate/percent metrics surfaced to the model — formatted with a percent sign.
_PCT_KEYS = {"ctr", "outbound_clicks_ctr"}

# Structured card contract: the four fields the on-screen diagnosis carries.
_CARD_FIELDS = ("headline", "driver", "watch", "next_step")

# Cap the daily trajectory so the prompt stays token-frugal on long ranges.
_MAX_TRAJECTORY_DAYS = 45

_EM_DASH = "—"


class AISummaryError(Exception):
    """Raised when a grounded narrative cannot be produced.

    The caller maps this to a distinguishable HTTP error (502) — never a 200
    with empty/placeholder text (P-4).
    """


_CARD_SYSTEM_PROMPT = (
    "You are a senior performance-marketing analyst writing the monthly review "
    "for a single ad account. You are given ALREADY-COMPUTED figures for a "
    "current period and the immediately preceding period of equal length: "
    "account-level metrics, the top campaigns (each with its objective and its "
    "own current | previous | change), and a compact day-by-day trajectory for "
    "both periods.\n\n"
    "Your job is to DIAGNOSE, not describe. Do not merely restate the delta "
    "pills. Identify the single most material change, name its most likely "
    "driver, and say what to do about it.\n\n"
    "HOW TO JUDGE:\n"
    "- Judge every metric AGAINST the campaign objective. Low ROAS is NOT a "
    "failure for a TRAFFIC, REACH, ENGAGEMENT or awareness objective — judge "
    "those on reach/CTR/CPC/CPM. Judge a SALES/CONVERSIONS/OUTCOME_SALES "
    "objective on ROAS, conversions and cost-per-acquisition.\n"
    "- To name a driver, SELECT the campaign whose already-given change best "
    "explains the account-level move, and contrast it with the campaigns that "
    "held steady. You are choosing, not calculating.\n"
    "- Use the daily trajectory to say WHEN within the period the change "
    "happened (e.g. a mid-month drop-off) when the days support it.\n\n"
    "STRICT RULES — non-negotiable:\n"
    "1. Use ONLY the numbers provided. Never state a figure not present in the "
    "input.\n"
    "2. NEVER perform arithmetic. Do not compute, derive, sum, average, rank by "
    "computed value, or recalculate anything. Every percentage change is "
    "already given — QUOTE it, do not recompute it. When you name a driver you "
    "are selecting a provided row, not computing which is largest.\n"
    "3. Phrase any cause as a hypothesis, not a fact ('this may reflect...', "
    "'a likely driver is...'), never as a definitive claim.\n"
    "4. Do not invent campaigns, dates, objectives, or external events not in "
    "the input.\n"
    "5. Reference the actual campaign names and labelled figures — be concrete."
)

_CARD_USER_INSTRUCTIONS = (
    "Respond with a single JSON object whose keys are EXACTLY "
    '"headline", "driver", "watch", "next_step" and nothing else. Do not wrap '
    "the JSON in markdown fences. Each value is 1-3 substantive sentences:\n"
    "- headline: the single most important change stated as a DIAGNOSIS, not a "
    "restatement (e.g. 'Conversions down 86% on flat spend — an efficiency "
    "problem, not a budget one').\n"
    "- driver: the most likely driver, SELECTED from the campaigns above — name "
    "the campaign, quote its given ROAS/conversion change, note its objective, "
    "and contrast it with campaigns that held.\n"
    "- watch: a secondary signal worth watching (e.g. CTR, frequency, or a "
    "trend visible in the daily trajectory).\n"
    "- next_step: one concrete, specific action to investigate or fix the "
    "issue you diagnosed."
)


_NARRATIVE_SYSTEM_PROMPT = (
    "You are a senior performance-marketing analyst writing the monthly review "
    "for a single ad account, for a slide deck. You are given ALREADY-COMPUTED "
    "figures for a current period and the immediately preceding period of equal "
    "length: account-level metrics, the top campaigns (each with objective and "
    "its own current | previous | change), and a compact day-by-day trajectory "
    "for both periods.\n\n"
    "Diagnose, don't just describe. Judge every metric AGAINST the campaign "
    "objective (do not treat low ROAS as failure for a traffic/awareness "
    "objective; judge a sales objective on ROAS/conversions/CPA). When you "
    "attribute a movement to a campaign, SELECT the campaign whose given change "
    "best explains it — you are choosing a provided row, not calculating.\n\n"
    "STRICT RULES — non-negotiable:\n"
    "1. Use ONLY the numbers provided. Never state a figure not present.\n"
    "2. NEVER perform arithmetic — the percentage changes are given, QUOTE "
    "them, never recompute or rank by a computed value.\n"
    "3. Phrase causes as hypotheses, not facts.\n"
    "4. Do not invent campaigns, dates, objectives, or external events.\n"
    "5. Be concrete — reference the actual campaign names and labelled figures. "
    "Plain professional prose, no bullet lists, no markdown headers. Each "
    "section is 2-4 sentences."
)


# ── formatters ────────────────────────────────────────────────────────────


def _fmt_metric(key: str, value: Optional[float], currency: str) -> str:
    """Format a single metric the same way the UI/PPTX would.

    Money keys use the account currency; rates use percent; roas uses `x`;
    counts fall back to the compact number formatter. None renders as an em dash
    so the model sees "no data" explicitly rather than a misleading zero (P-4)."""
    if value is None:
        return _EM_DASH
    if key == "roas":
        return _fmt_roas(value)
    if key in _PCT_KEYS:
        return _fmt_percent(value)
    if key == "spend" or key.startswith("cost_per_") or key in {
        "cpm", "cpc", "cpa", "cpp", "conversion_value",
    }:
        return _fmt_money(value, currency)
    return _fmt_number(value)


def _fmt_delta(value: Optional[float]) -> str:
    """Pre-formatted period-over-period % change; the model must quote, not
    recompute (rule 2). None → 'n/a' so it isn't read as 0%."""
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Display-only % change from two ALREADY-COMPUTED figures.

    This is the service pre-formatting a delta for the model to QUOTE — the model
    never does this itself (rule 2). Mirrors insights._pct_change semantics: no
    prior value (or zero) → None, so we don't fabricate a spurious 0% / ∞%."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100.0


def _campaign_change(cur: Optional[dict], prev: Optional[dict], key: str) -> str:
    """Given a campaign's current + previous metric dicts, produce the display
    '% change' string for one metric (service-side, for the model to quote)."""
    cur_v = (cur or {}).get(key)
    prev_v = (prev or {}).get(key)
    return _fmt_delta(_pct_change(cur_v, prev_v))


# ── prompt blocks ───────────────────────────────────────────────────────────


def _build_metrics_block(overview: dict, currency: str) -> str:
    """Serialize the account-level overview dict into a compact, labelled block.

    Only pre-formatted strings go to the model — never raw floats it could be
    tempted to do math on. Every number here comes straight from get_overview."""
    period = overview.get("period") or {}
    summary = overview.get("summary") or {}
    previous = overview.get("previous") or {}
    vs = overview.get("vs_previous") or {}

    metric_keys = [
        ("spend", "Spend"),
        ("impressions", "Impressions"),
        ("reach", "Reach"),
        ("clicks", "Clicks"),
        ("ctr", "CTR"),
        ("cpm", "CPM"),
        ("cpc", "CPC"),
        ("conversions", "Conversions"),
        ("roas", "ROAS"),
        ("outbound_clicks", "Outbound clicks"),
        ("outbound_clicks_ctr", "Outbound CTR"),
    ]

    lines: list[str] = []
    lines.append(f"Currency: {currency}")
    lines.append(
        f"Current period: {period.get('date_start')} to {period.get('date_stop')}"
    )
    lines.append("")
    lines.append("ACCOUNT METRICS (current | previous | change vs previous):")
    for key, label in metric_keys:
        cur = _fmt_metric(key, summary.get(key), currency)
        prev = _fmt_metric(key, previous.get(key), currency)
        delta = _fmt_delta(vs.get(key)) if key in vs else "n/a"
        lines.append(f"  {label}: {cur} | {prev} | {delta}")

    return "\n".join(lines)


def _build_campaigns_block(campaigns: list[dict], currency: str) -> str:
    """Serialize per-campaign period-over-period rows (from get_table with
    compare_previous=True). For each campaign: name, objective, and
    current | previous | given-change for spend, ROAS, conversions, CTR.

    This is what the model SELECTS a driver from — no ranking/arithmetic here,
    the rows are just listed with their pre-formatted changes."""
    if not campaigns:
        return "CAMPAIGNS: (none)"

    metric_specs = [
        ("spend", "Spend"),
        ("roas", "ROAS"),
        ("conversions", "Conversions"),
        ("ctr", "CTR"),
    ]

    lines: list[str] = []
    lines.append(
        "CAMPAIGNS (each metric shown as current | previous | change vs "
        "previous). Objective governs how to judge the campaign:"
    )
    for c in campaigns:
        name = c.get("name") or "(unnamed)"
        objective = c.get("objective") or "UNKNOWN"
        status = c.get("status") or "?"
        cur = c.get("metrics") or {}
        prev = c.get("metrics_previous") or {}
        lines.append(f"  - {name} [objective: {objective}, status: {status}]")
        for key, label in metric_specs:
            cur_s = _fmt_metric(key, cur.get(key), currency)
            prev_s = _fmt_metric(key, prev.get(key), currency)
            chg_s = _campaign_change(cur, prev, key)
            lines.append(f"      {label}: {cur_s} | {prev_s} | {chg_s}")
    return "\n".join(lines)


def _build_trajectory_block(timeseries: dict, currency: str) -> str:
    """Compact day-by-day lines (date + spend + conversions) for the current and
    prior periods, so the model can speak to WHEN a change happened.

    Token-frugal by design: only spend + conversions per day, capped to
    _MAX_TRAJECTORY_DAYS with an explicit truncation note (P-1: never silently
    hide that data was elided)."""
    if not timeseries:
        return "DAILY TRAJECTORY: (none)"

    def _days(points: Optional[list[dict]], header: str) -> list[str]:
        pts = points or []
        out = [header]
        if not pts:
            out.append("  (no data)")
            return out
        truncated = len(pts) > _MAX_TRAJECTORY_DAYS
        shown = pts[:_MAX_TRAJECTORY_DAYS]
        for p in shown:
            out.append(
                "  {d}: spend {s}, conversions {c}".format(
                    d=p.get("date"),
                    s=_fmt_metric("spend", p.get("spend"), currency),
                    c=_fmt_metric("conversions", p.get("conversions"), currency),
                )
            )
        if truncated:
            out.append(
                f"  ... ({len(pts) - _MAX_TRAJECTORY_DAYS} more days omitted)"
            )
        return out

    lines: list[str] = ["DAILY TRAJECTORY (spend + conversions per day):"]
    lines.extend(_days(timeseries.get("series"), "Current period:"))
    lines.append("")
    lines.extend(_days(timeseries.get("previous_series"), "Previous period:"))
    return "\n".join(lines)


def _build_bundle_block(
    overview: dict,
    currency: str,
    *,
    campaigns: list[dict],
    timeseries: dict,
) -> str:
    """Assemble the full enriched context (account + campaigns + trajectory)."""
    return "\n\n".join(
        [
            _build_metrics_block(overview, currency),
            _build_campaigns_block(campaigns, currency),
            _build_trajectory_block(timeseries, currency),
        ]
    )


def _section_instructions(sections: list[str]) -> str:
    """Per-section guidance for the PPTX narrative. Keys map to deck slides."""
    blurbs = {
        "overview": (
            "overview: one holistic diagnosis of the account's movement this "
            "period vs last — lead with the most material change and its likely "
            "driver."
        ),
        "performance": (
            "performance: diagnose the hero metrics (spend, conversions, ROAS, "
            "CTR) — what moved and, judged against objective, whether it's good."
        ),
        "trend": (
            "trend: describe the trajectory using the DAILY figures — when in "
            "the period momentum built or fell off, current period vs previous. "
            "Ground this in the day-by-day data, do not infer a shape you can't "
            "see."
        ),
        "campaigns": (
            "campaigns: what the campaigns show — concentration of spend, which "
            "campaign (by name) drove the account move, which held, judged "
            "against each campaign's objective."
        ),
    }
    return "\n".join(f"- {blurbs[s]}" for s in sections if s in blurbs)


# ── entry points ──────────────────────────────────────────────────────────


def _call_openai(system_prompt: str, user_prompt: str):
    """Shared OpenAI call. Any failure surfaces as AISummaryError (P-4)."""
    if not settings.OPENAI_API_KEY:
        raise AISummaryError("OpenAI API key is not configured.")
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=_REQUEST_TIMEOUT)
        completion = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        logger.warning("ai_summary: OpenAI request failed: %s", exc)
        raise AISummaryError(f"AI summary generation failed: {exc}")
    except Exception as exc:  # noqa: BLE001 - any failure must surface, never fake success
        logger.warning("ai_summary: unexpected error calling OpenAI: %s", exc)
        raise AISummaryError(f"AI summary generation failed: {exc}")

    if not completion.choices:
        raise AISummaryError("OpenAI returned no choices.")
    return completion.choices[0].message.content or ""


def _parse_json_object(content: str) -> dict:
    """Parse a JSON object from the completion, or raise AISummaryError (P-4)."""
    if not content or not content.strip():
        raise AISummaryError("OpenAI returned an empty completion.")
    try:
        data = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise AISummaryError(f"Could not parse the AI summary response: {exc}")
    if not isinstance(data, dict):
        raise AISummaryError("AI summary response was not a JSON object.")
    return data


def _require_string_keys(data: dict, keys) -> dict[str, str]:
    """Every requested key must be a non-blank string, or raise (P-4)."""
    result: dict[str, str] = {}
    for key in keys:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AISummaryError(
                f"AI summary response missing or blank field '{key}'."
            )
        result[key] = value.strip()
    return result


def generate_overview_diagnosis(
    overview: dict,
    account,
    *,
    campaigns: list[dict],
    timeseries: dict,
) -> dict[str, str]:
    """Produce the STRUCTURED on-screen diagnosis card.

    Args:
        overview: dict from `insights.get_overview` (keys `period`, `summary`,
            `previous`, `vs_previous`, `top_campaigns`). Sole source of
            account-level numbers; nothing is queried here (P-7).
        account: SQLAlchemy Account model, used only for `account.currency`.
        campaigns: per-campaign rows from `insights.get_table` with
            `compare_previous=True` — each has `name`, `status`, `objective`,
            `metrics` (current) and `metrics_previous` (prior). The model SELECTS
            the driver from these; it does not compute over them.
        timeseries: dict from `insights.get_timeseries` with `series` +
            `previous_series` daily points (grounds the "when" of the change).

    Returns:
        dict with exactly the keys `headline`, `driver`, `watch`, `next_step`,
        each a non-blank diagnostic string.

    Raises:
        AISummaryError: on missing/empty API key, network/timeout, API error, or
            an empty/unparseable/incomplete completion. Never returns fake or
            empty text as a success (P-4).
    """
    currency = getattr(account, "currency", None) or "USD"
    bundle = _build_bundle_block(
        overview, currency, campaigns=campaigns, timeseries=timeseries
    )
    user_prompt = (
        f"Here is the already-computed data for this account:\n\n{bundle}\n\n"
        f"{_CARD_USER_INSTRUCTIONS}"
    )
    content = _call_openai(_CARD_SYSTEM_PROMPT, user_prompt)
    data = _parse_json_object(content)
    return _require_string_keys(data, _CARD_FIELDS)


def generate_narrative(
    overview: dict,
    account,
    *,
    sections: list[str],
    campaigns: Optional[list[dict]] = None,
    timeseries: Optional[dict] = None,
) -> dict[str, str]:
    """Produce grounded narrative prose for the requested PPTX sections.

    Enriched to the same bundle as the on-screen card: account metrics plus (when
    provided) per-campaign period-over-period rows and the daily trajectory, so
    the trend/campaigns slides are grounded in real day-by-day data rather than a
    trajectory the model never saw.

    Args:
        overview: dict from `insights.get_overview`.
        account: Account model, used only for `account.currency`.
        sections: which narratives to produce, e.g. `["performance", "trend",
            "campaigns"]`. Returned dict is keyed by section name.
        campaigns: optional per-campaign rows (get_table, compare_previous=True).
        timeseries: optional daily series dict (get_timeseries).

    Returns:
        {section: narrative} for exactly the requested sections.

    Raises:
        AISummaryError: on any failure — never fake/empty success (P-4).
    """
    if not sections:
        raise AISummaryError("No summary sections requested.")

    currency = getattr(account, "currency", None) or "USD"
    bundle = _build_bundle_block(
        overview,
        currency,
        campaigns=campaigns or [],
        timeseries=timeseries or {},
    )
    keys_list = ", ".join(f'"{s}"' for s in sections)
    user_prompt = (
        f"Here is the already-computed data for this account:\n\n{bundle}\n\n"
        "Produce a grounded, diagnostic narrative. Respond with a single JSON "
        f"object whose keys are exactly {keys_list} and whose values are the "
        "narrative strings for each. Do not include any other keys. Do not wrap "
        "the JSON in markdown fences.\n\n"
        "Section guidance:\n"
        f"{_section_instructions(sections)}"
    )
    content = _call_openai(_NARRATIVE_SYSTEM_PROMPT, user_prompt)
    data = _parse_json_object(content)
    return _require_string_keys(data, sections)
