"""Tests for the grounded AI diagnosis service (PRD §4 P-1/P-4/P-6/P-7).

`ai_summary` is handed the dicts the shared read path produces
(`insights.get_overview`, `insights.get_table`, `insights.get_timeseries`) and
asks OpenAI to *diagnose* over them — it does no math and states no number not
already in those dicts. There are two entry points:

  * `generate_overview_diagnosis(overview, account, *, campaigns, timeseries)`
    — the on-screen card. Returns a STRUCTURED dict keyed by exactly
    `headline`, `driver`, `watch`, `next_step`. This is what POST
    /overview/summary calls.
  * `generate_narrative(overview, account, *, sections, campaigns=None,
    timeseries=None)` — the PPTX deck. Returns `{section: prose}`.

These tests pin the trust guarantees the feature exists for:

  * Prompt grounding — the system prompt forbids inventing figures / doing
    arithmetic / asserting causes as fact, instructs the model to SELECT (not
    compute) the driver and to judge every metric AGAINST the campaign
    objective; the user content carries the already-formatted account numbers,
    the campaign names + objectives, and the daily trajectory lines (and nothing
    the code fabricated).
  * Structured parse — a valid JSON completion yields all four card fields,
    stripped. Any missing/blank field → `AISummaryError`.
  * Fail-loud — on ANY failure (empty key, network/API error, empty or
    unparseable completion, blank field) it raises `AISummaryError`. It never
    returns a fake/empty dict dressed up as a success (P-4 / anti-fake-zero).
  * P-7 structural — the module imports no repository and runs no SQL; it only
    transforms the dicts it's given and calls OpenAI.

Everything here is DB-free and network-free: the OpenAI client is replaced with
an in-process fake by patching `ai_summary.OpenAI`, so nothing leaves the
process and no real tokens are spent.

Run:
    cd backend && \
    $HOME/.pyenv/versions/3.12.13/bin/python -m pytest tests/test_ai_summary.py -v
"""
import re
import types
from pathlib import Path

import pytest
from openai import OpenAIError

from app.services import ai_summary
from app.services.ai_summary import (
    AISummaryError,
    generate_narrative,
    generate_overview_diagnosis,
)


# ─── Fakes: an in-process stand-in for the OpenAI client ─────────────────────


def _make_completion(content):
    """Shape a fake object like the OpenAI SDK's ChatCompletion (choices ->
    [choice] -> message.content). `content=None` and empty choices are both
    exercised by the failure tests below."""
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice])


def _valid_card_json():
    """A minimally-valid structured card the parser must accept."""
    return (
        '{"headline": "Conversions down on flat spend.", '
        '"driver": "Alpha Launch (SALES) drove the drop.", '
        '"watch": "CTR softening late in the period.", '
        '"next_step": "Audit Alpha Launch targeting."}'
    )


class _FakeOpenAI:
    """Replacement for `openai.OpenAI`. Captures the messages sent to
    chat.completions.create so the grounding test can inspect the prompt, and
    returns/raises whatever the test wired up."""

    # Class-level hooks the tests set before calling into the service.
    captured_messages = None
    to_return = None
    to_raise = None

    def __init__(self, *args, **kwargs):
        self.init_args = kwargs

        outer = _FakeOpenAI

        class _Completions:
            def create(self, *, model, messages, **kwargs):
                outer.captured_messages = messages
                if outer.to_raise is not None:
                    raise outer.to_raise
                return outer.to_return

        self.chat = types.SimpleNamespace(completions=_Completions())


@pytest.fixture
def fake_openai(monkeypatch):
    """Patch the OpenAI client at its call site in ai_summary and ensure a key
    is present so the code reaches the (faked) network call. Resets the class
    hooks each test to avoid cross-test bleed."""
    monkeypatch.setattr(ai_summary.settings, "OPENAI_API_KEY", "test-key-123")
    monkeypatch.setattr(ai_summary.settings, "OPENAI_MODEL", "gpt-4o-mini")
    _FakeOpenAI.captured_messages = None
    _FakeOpenAI.to_return = None
    _FakeOpenAI.to_raise = None
    monkeypatch.setattr(ai_summary, "OpenAI", _FakeOpenAI)
    return _FakeOpenAI


def _fake_account(currency="USD"):
    """The service only reads `account.currency`, so a namespace suffices."""
    return types.SimpleNamespace(currency=currency)


def _sample_overview():
    """Shaped like insights.get_overview: period / summary / previous /
    vs_previous / top_campaigns. Values chosen so their FORMATTED strings are
    distinctive enough to grep for in the prompt (grounding test)."""
    return {
        "period": {"date_start": "2026-06-01", "date_stop": "2026-06-30", "preset": "last_30d"},
        "summary": {
            "spend": 12345.67,
            "impressions": 2_500_000,
            "clicks": 48_000,
            "ctr": 1.92,
            "cpm": 4.94,
            "conversions": 1_234,
            "roas": 3.75,
        },
        "previous": {
            "spend": 11000.0,
            "impressions": 2_600_000,
            "clicks": 47_500,
            "ctr": 1.80,
            "cpm": 5.10,
            "conversions": 1_130,
            "roas": 3.20,
        },
        "vs_previous": {
            "spend": 12.3,
            "impressions": -4.1,
            "clicks": 1.1,
            "ctr": 6.7,
            "cpm": -3.1,
            "conversions": 9.2,
            "roas": 17.2,
        },
        "top_campaigns": [
            {"name": "Alpha Launch", "spend": 5000.0, "ctr": 2.10,
             "conversions": 600.0, "roas": 4.00},
        ],
    }


def _sample_campaigns():
    """Shaped like insights.get_table(level="campaign", compare_previous=True):
    each row carries name/status/objective plus `metrics` (current) and
    `metrics_previous` (prior). The model SELECTS a driver from these."""
    return [
        {
            "name": "Alpha Launch",
            "status": "ACTIVE",
            "objective": "OUTCOME_SALES",
            "metrics": {"spend": 5000.0, "roas": 4.00, "conversions": 600.0, "ctr": 2.10},
            "metrics_previous": {"spend": 4800.0, "roas": 6.00, "conversions": 900.0, "ctr": 2.30},
        },
        {
            "name": "Beta Awareness",
            "status": "ACTIVE",
            "objective": "OUTCOME_AWARENESS",
            "metrics": {"spend": 2500.0, "roas": 0.50, "conversions": 20.0, "ctr": 3.40},
            "metrics_previous": {"spend": 2450.0, "roas": 0.48, "conversions": 18.0, "ctr": 3.30},
        },
    ]


def _sample_timeseries():
    """Shaped like insights.get_timeseries(compare_previous=True): `series` +
    `previous_series` daily points (spend + conversions grounded)."""
    return {
        "series": [
            {"date": "2026-06-01", "spend": 400.0, "conversions": 42},
            {"date": "2026-06-02", "spend": 415.5, "conversions": 40},
            {"date": "2026-06-03", "spend": 500.0, "conversions": 55},
        ],
        "previous_series": [
            {"date": "2026-05-01", "spend": 380.0, "conversions": 60},
            {"date": "2026-05-02", "spend": 402.0, "conversions": 58},
        ],
    }


# ─── 1a. Prompt grounding: generate_overview_diagnosis ───────────────────────


def test_card_system_prompt_forbids_invention_and_arithmetic(fake_openai):
    """The system message for the diagnosis card must instruct: use only
    provided numbers, no arithmetic, causes as hypotheses not facts, SELECT (not
    compute) the driver, and judge metrics against the campaign objective. These
    are the guardrails that keep the feature trustworthy (PRD §4 / P-7)."""
    fake_openai.to_return = _make_completion(_valid_card_json())

    generate_overview_diagnosis(
        _sample_overview(), _fake_account(),
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )

    messages = fake_openai.captured_messages
    assert messages, "generate_overview_diagnosis did not send any messages"
    system = next(m["content"] for m in messages if m["role"] == "system").lower()

    # "use ONLY the numbers provided / never state a figure not present"
    assert "only" in system and "provided" in system
    # "NEVER perform arithmetic / do not compute/derive/recalculate"
    assert "arithmetic" in system
    # causes are hypotheses, not facts
    assert "hypothes" in system and "fact" in system
    # SELECT the driver — the model chooses, it does not calculate
    assert "select" in system
    assert "not calculat" in system or "not comput" in system or "choosing, not" in system
    # judge every metric AGAINST the campaign objective
    assert "objective" in system


def test_card_user_prompt_contains_account_numbers_campaigns_and_trajectory(fake_openai):
    """The user content must carry:
      * the formatted account metric values (P-1/P-6 — same export helpers as UI),
      * the campaign names AND their objectives (what the driver is SELECTED from),
      * the daily-trajectory lines (grounds the "when" of a change).
    Formatting goes through the SAME export helpers the UI/PPTX use."""
    fake_openai.to_return = _make_completion(_valid_card_json())

    ov = _sample_overview()
    generate_overview_diagnosis(
        ov, _fake_account(currency="USD"),
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )

    user = next(
        m["content"] for m in fake_openai.captured_messages if m["role"] == "user"
    )

    from app.services.export import _fmt_money, _fmt_roas, _fmt_percent, _fmt_number

    # Account metrics, formatted by the export helpers.
    assert _fmt_money(12345.67, "USD") in user            # "$12,346"
    assert _fmt_roas(3.75) in user                        # "3.75x"
    assert _fmt_percent(1.92) in user                     # "1.92%"
    assert _fmt_number(2_500_000) in user                 # "2.5M" impressions
    # Pre-formatted account delta the model must QUOTE not recompute.
    assert "+12.3%" in user

    # Campaign names + objectives flow through untouched.
    assert "Alpha Launch" in user
    assert "Beta Awareness" in user
    assert "OUTCOME_SALES" in user
    assert "OUTCOME_AWARENESS" in user

    # Daily trajectory: current + previous period day lines present.
    assert "2026-06-01" in user            # a current-period day
    assert "2026-05-01" in user            # a previous-period day
    assert "conversions" in user.lower()   # trajectory carries conversions


def test_card_code_injects_no_number_absent_from_input(fake_openai):
    """The service itself must not inject a figure that isn't derivable from the
    input dicts. We assert every standalone number token in the account-metrics
    block is the formatting of a value present in the overview dict (or a
    structural literal like an ISO date), never a fabricated metric."""
    fake_openai.to_return = _make_completion(_valid_card_json())

    ov = _sample_overview()
    generate_overview_diagnosis(
        ov, _fake_account(),
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )
    user = next(
        m["content"] for m in fake_openai.captured_messages if m["role"] == "user"
    )

    # Every formatted metric string the code should have produced for the
    # ACCOUNT block (summary + previous + vs_previous deltas + period dates).
    expected_tokens = set()
    for key, val in ov["summary"].items():
        expected_tokens.add(ai_summary._fmt_metric(key, val, "USD"))
    for key, val in ov["previous"].items():
        expected_tokens.add(ai_summary._fmt_metric(key, val, "USD"))
    for val in ov["vs_previous"].values():
        expected_tokens.add(ai_summary._fmt_delta(val))

    def _digits(s):
        return re.sub(r"[^\d.]", "", str(s)).strip(".")

    expected_digits = {
        _digits(t) for t in expected_tokens if any(ch.isdigit() for ch in str(t))
    }

    # Isolate the account-metrics block: from "ACCOUNT METRICS" up to the
    # campaigns block. The fixed instruction scaffolding references no metric.
    start = user.index("ACCOUNT METRICS")
    end = user.index("CAMPAIGNS", start)
    metrics_block = user[start:end]

    # Period dates (ISO yyyy-mm-dd) come straight from period; assert present,
    # then drop them so their y/m/d parts don't confuse the digit scan.
    for iso in (ov["period"]["date_start"], ov["period"]["date_stop"]):
        assert iso in user
        metrics_block = metrics_block.replace(iso, " ")

    numeric_chunks = re.findall(r"[-+]?[\d][\d,\.]*[%xKMB]?", metrics_block)
    for chunk in numeric_chunks:
        core = _digits(chunk)
        if not core:
            continue
        assert core in expected_digits, (
            f"account block contains a numeric token {chunk!r} (core {core!r}) "
            f"not derivable from the overview dict — the code may be fabricating "
            f"numbers. Allowed: {sorted(expected_digits)}"
        )


# ─── 1b. Structured parse: exactly headline/driver/watch/next_step ───────────


def test_card_returns_all_four_fields_stripped(fake_openai):
    """A valid JSON completion with the four card keys yields exactly those keys,
    whitespace-stripped."""
    fake_openai.to_return = _make_completion(
        '{"headline": "  H  ", "driver": " D ", '
        '"watch": "W", "next_step": "  NS", "extra": "ignored"}'
    )
    result = generate_overview_diagnosis(
        _sample_overview(), _fake_account(),
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )
    assert set(result) == {"headline", "driver", "watch", "next_step"}
    assert result == {"headline": "H", "driver": "D", "watch": "W", "next_step": "NS"}


@pytest.mark.parametrize("missing", ["headline", "driver", "watch", "next_step"])
def test_card_missing_field_raises(fake_openai, missing):
    """A completion omitting any one of the four required fields is incomplete →
    AISummaryError. We never fabricate the missing field (P-4)."""
    fields = {
        "headline": "H", "driver": "D", "watch": "W", "next_step": "NS",
    }
    del fields[missing]
    body = "{" + ", ".join(f'"{k}": "{v}"' for k, v in fields.items()) + "}"
    fake_openai.to_return = _make_completion(body)
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_card_blank_field_raises(fake_openai, blank):
    """A present-but-blank (or null) required field is not a valid diagnosis →
    AISummaryError (P-4)."""
    import json as _json
    fields = {"headline": "H", "driver": "D", "watch": "W", "next_step": "NS"}
    fields["watch"] = blank
    fake_openai.to_return = _make_completion(_json.dumps(fields))
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


# ─── 1c. Fail-loud: any failure → AISummaryError (never fake success) ────────


def test_card_openai_exception_raises(fake_openai):
    """A raised OpenAIError from the client must surface as AISummaryError, not a
    swallowed empty dict (P-4)."""
    fake_openai.to_raise = OpenAIError("upstream 500")
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


def test_card_unexpected_exception_raises(fake_openai):
    """A non-OpenAI exception (timeout, network, SDK edge) must ALSO surface as
    AISummaryError — any failure is distinguishable, never a fake success."""
    fake_openai.to_raise = RuntimeError("connection reset")
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


def test_card_empty_completion_raises(fake_openai):
    """An empty completion body is not a valid diagnosis → AISummaryError."""
    fake_openai.to_return = _make_completion("")
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


def test_card_unparseable_completion_raises(fake_openai):
    """Non-JSON garbage must not be passed off as a diagnosis → AISummaryError."""
    fake_openai.to_return = _make_completion("this is not json {{{")
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


def test_card_non_object_json_raises(fake_openai):
    """Valid JSON that isn't an object (e.g. a list) → AISummaryError."""
    fake_openai.to_return = _make_completion('["headline", "driver"]')
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


def test_card_empty_api_key_raises(monkeypatch):
    """With no API key configured, we fail loud rather than attempt a call — and
    definitely rather than return empty text (P-4). No OpenAI patch here on
    purpose: the empty-key guard must trip BEFORE any client is constructed."""
    monkeypatch.setattr(ai_summary.settings, "OPENAI_API_KEY", "")

    def _should_not_construct(*a, **k):
        raise AssertionError("OpenAI client constructed despite empty API key")

    monkeypatch.setattr(ai_summary, "OpenAI", _should_not_construct)
    with pytest.raises(AISummaryError):
        generate_overview_diagnosis(
            _sample_overview(), _fake_account(),
            campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
        )


# ─── 1d. generate_narrative (PPTX) still honours its contract ────────────────


def test_narrative_all_pptx_sections_returned(fake_openai):
    """sections=["performance","trend","campaigns"] returns all three keys, in
    the shape the PPTX exporter threads into its insight boxes. Campaigns +
    timeseries are now also fed in (grounding) but the output stays strings."""
    fake_openai.to_return = _make_completion(
        '{"performance": "Perf text.", "trend": "Trend text.", '
        '"campaigns": "Campaign text.", "extra": "ignored"}'
    )
    result = generate_narrative(
        _sample_overview(), _fake_account(),
        sections=["performance", "trend", "campaigns"],
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )
    assert set(result) == {"performance", "trend", "campaigns"}
    assert result["performance"] == "Perf text."
    assert result["trend"] == "Trend text."
    assert result["campaigns"] == "Campaign text."


def test_narrative_missing_section_raises(fake_openai):
    """Valid JSON that omits a requested section is incomplete → AISummaryError.
    We never fabricate the missing section (P-4)."""
    fake_openai.to_return = _make_completion('{"performance": "only this one"}')
    with pytest.raises(AISummaryError):
        generate_narrative(
            _sample_overview(), _fake_account(),
            sections=["performance", "trend", "campaigns"],
        )


def test_narrative_no_sections_requested_raises(fake_openai):
    """An empty sections list is a programming error, not a silent empty dict."""
    with pytest.raises(AISummaryError):
        generate_narrative(_sample_overview(), _fake_account(), sections=[])


def test_narrative_grounds_campaigns_and_trajectory(fake_openai):
    """When campaigns + timeseries are supplied, the narrative prompt is grounded
    in the same enriched bundle as the card — campaign objectives and daily
    trajectory lines must reach the model (regression against the pre-rewrite
    narrative that only saw account rollups)."""
    fake_openai.to_return = _make_completion('{"trend": "Momentum built late."}')
    generate_narrative(
        _sample_overview(), _fake_account(), sections=["trend"],
        campaigns=_sample_campaigns(), timeseries=_sample_timeseries(),
    )
    user = next(
        m["content"] for m in fake_openai.captured_messages if m["role"] == "user"
    )
    assert "OUTCOME_SALES" in user
    assert "2026-06-01" in user
    assert "2026-05-01" in user


# ─── 3. P-7 structural: no repository import, no SQL execution ────────────────

_AI_SUMMARY_SRC = Path(ai_summary.__file__)


def _strip_comments_and_docstrings(src: str) -> str:
    """Return only the executable tokens of a Python source string — comments
    and string literals (incl. docstrings) removed. Uses the stdlib tokenizer so
    the structural scan reasons about code, not prose in the module docstring."""
    import io
    import tokenize

    out = []
    tokens = tokenize.generate_tokens(io.StringIO(src).readline)
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_ai_summary_imports_no_repository():
    """P-7: the AI service must never import a repository — it narrates over the
    dicts it's given, it does not fetch. Static source scan so a stray import
    fails here, not at runtime. Matches the static-scan style of
    test_sync_jobs_completeness.py."""
    src = _AI_SUMMARY_SRC.read_text()
    assert not re.search(r"\bimport\s+app\.repository", src)
    assert not re.search(r"\bfrom\s+app\.repository\b", src)


def test_ai_summary_runs_no_sql():
    """P-7: no SQL execution in the AI service. It must not construct
    SQLAlchemy text() queries, call db.execute/session.execute, or take a DB
    session — every number comes from the passed-in dicts. We strip
    comments/docstrings first so prose like "...runs no SQL" doesn't
    false-positive; the scan is non-vacuous because the executable body (imports,
    OpenAI call, formatting) still tokenizes to real tokens."""
    stripped = _strip_comments_and_docstrings(_AI_SUMMARY_SRC.read_text())
    # Sanity: the stripped source is non-empty and still contains the real code
    # seams — proves the scan runs against actual tokens, not an empty string.
    assert "generate_overview_diagnosis" in stripped
    assert "OpenAI" in stripped

    forbidden = [
        r"\btext\(",                # sqlalchemy.text( ... )
        r"\.execute\(",             # db.execute / session.execute
        r"\bfrom\s+sqlalchemy\b",   # any sqlalchemy import
        r"\bimport\s+sqlalchemy\b",
        r"\bget_db\b",
    ]
    hits = [pat for pat in forbidden if re.search(pat, stripped)]
    assert not hits, f"ai_summary.py contains SQL/DB-access seams: {hits}"


def test_generate_overview_diagnosis_takes_no_db_session():
    """P-7 (signature): generate_overview_diagnosis accepts
    (overview, account, *, campaigns, timeseries) — no db/session parameter. If
    a DB param appears, the read path has leaked into the narrator."""
    import inspect

    params = list(inspect.signature(generate_overview_diagnosis).parameters)
    assert params == ["overview", "account", "campaigns", "timeseries"], (
        f"unexpected signature params {params}; a DB session must not be added"
    )


def test_generate_narrative_takes_no_db_session():
    """P-7 (signature): generate_narrative accepts
    (overview, account, *, sections, campaigns=None, timeseries=None) — no
    db/session parameter. If a DB param appears, the read path has leaked in."""
    import inspect

    params = list(inspect.signature(generate_narrative).parameters)
    assert params == ["overview", "account", "sections", "campaigns", "timeseries"], (
        f"unexpected signature params {params}; a DB session must not be added"
    )
