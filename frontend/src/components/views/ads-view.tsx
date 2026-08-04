"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { Play, Images, X, ExternalLink, ChevronRight } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SegmentControl } from "@/components/ui/segment-control";
import { StatusBadge } from "@/components/shared/status-badge";
import { SyncAwareEmpty } from "@/components/shared/sync-aware-empty";
import { DeltaPill } from "@/components/metrics/delta-pill";
import { useSyncActive } from "@/hooks/use-sync-jobs";
import { insightsApi, type MetricsPrevious } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useSelectedAccount } from "@/hooks/use-account";
import { usePlatform } from "@/hooks/use-platform";
import { useDateRange } from "@/hooks/use-date-range";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { usePlatformMetrics } from "@/hooks/use-platform-metrics";
import {
  formatCurrency,
  formatMetric,
  formatNumber,
  formatPercent,
  formatRoas,
} from "@/lib/formatters";
import { metricLabel, metricType } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import type { EntityStatus } from "@/types/enums";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CreativePreview {
  title?: string;
  thumbnail_url?: string | null;
  format?: string;
  cta_type?: string;
}

interface Creative extends CreativePreview {
  id?: string;
  platform_creative_id?: string;
  body?: string;
  image_url?: string | null;
  video_id?: string | null;
  destination_url?: string;
  synced_at?: string;
}

/**
 * Ad-level metric bag. The set is dynamic (account-type-dependent — a standard
 * account carries standard keys, a cpas account carries the `*_shared` set), so
 * this is an index signature rather than a fixed shape. The few keys read
 * directly in the card/row summaries are kept explicit for call-site clarity;
 * everything else is looked up by key from the registry. Values are always
 * numeric or null — never `any` (P-1: absence is null, not a forced zero).
 */
interface AdMetrics {
  spend?: number | null;
  ctr?: number | null;
  conversions?: number | null;
  roas?: number | null;
  [key: string]: number | null | undefined;
}

interface Ad {
  id: string;
  name: string;
  status: EntityStatus;
  platform?: string;
  campaign_id?: string;
  campaign_name?: string;
  adgroup_id?: string;
  adgroup_name?: string;
  creative_preview?: CreativePreview | null;
  metrics?: AdMetrics;
  metrics_previous?: MetricsPrevious;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const FORMAT_OPTIONS = [
  { value: "all",      label: "All formats" },
  { value: "image",    label: "Image" },
  { value: "video",    label: "Video" },
  { value: "carousel", label: "Carousel" },
];

const SORT_OPTIONS = [
  { value: "spend",       label: "Spend (high to low)" },
  { value: "ctr",         label: "CTR" },
  { value: "conversions", label: "Conversions" },
  { value: "roas",        label: "ROAS" },
  { value: "impressions", label: "Impressions" },
];

const PER_PAGE = 24;

// ─── Creative thumbnail ───────────────────────────────────────────────────────

function CreativeThumbnail({
  creative,
  className,
  showOverlay = true,
  fit = "cover",
}: {
  creative?: CreativePreview | Creative | null;
  className?: string;
  showOverlay?: boolean;
  fit?: "cover" | "contain";
}) {
  const src = (creative as Creative)?.image_url || creative?.thumbnail_url;

  if (!creative || !src) {
    return (
      <div className={cn("flex items-center justify-center bg-muted", className)}>
        <Images className="size-8 text-muted-foreground/40" />
      </div>
    );
  }

  return (
    <div className={cn("relative overflow-hidden bg-muted", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        className={cn("h-full w-full", fit === "contain" ? "object-contain" : "object-cover")}
      />
      {showOverlay && creative.format === "video" && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30">
          <div className="flex size-10 items-center justify-center rounded-full bg-white/90">
            <Play className="size-4 fill-current text-foreground" />
          </div>
        </div>
      )}
      {showOverlay && creative.format === "carousel" && (
        <div className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-xs text-white">
          Carousel
        </div>
      )}
    </div>
  );
}

// ─── AdCard (grid) ────────────────────────────────────────────────────────────

function AdCard({
  ad,
  onClick,
  currency,
  compare = false,
}: {
  ad: Ad;
  onClick: () => void;
  currency: string;
  compare?: boolean;
}) {
  const cp = ad.creative_preview;
  const m  = ad.metrics;
  const mp = ad.metrics_previous;
  const showDelta = compare && !!mp;

  return (
    <Card
      className="cursor-pointer overflow-hidden shadow-[var(--shadow-soft)] transition-shadow hover:shadow-[var(--shadow-lift)]"
      onClick={onClick}
    >
      {/* Creative thumbnail — 4:5 portrait, zero crop (letterbox on bg) */}
      <CreativeThumbnail
        creative={cp}
        fit="contain"
        className="aspect-[4/5] w-full rounded-none"
      />

      <CardContent className="p-3 space-y-3">
        {/* Title + CTA */}
        <div className="space-y-1">
          <p className="line-clamp-2 text-sm font-medium leading-snug">
            {cp?.title ?? ad.name}
          </p>
          {cp?.cta_type && (
            <span className="inline-block rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary uppercase tracking-wide">
              {cp.cta_type.replace(/_/g, " ")}
            </span>
          )}
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <span className="text-muted-foreground">Spend</span>
          <span className="flex items-center justify-end gap-1 text-right tabular-nums font-medium">
            {formatCurrency(m?.spend, currency)}
            {showDelta && (
              <DeltaPill current={m?.spend} previous={mp?.spend} metricKey="spend" variant="tooltip" currency={currency} />
            )}
          </span>
          <span className="text-muted-foreground">CTR</span>
          <span className="flex items-center justify-end gap-1 text-right tabular-nums">
            {formatPercent(m?.ctr)}
            {showDelta && (
              <DeltaPill current={m?.ctr} previous={mp?.ctr} metricKey="ctr" variant="tooltip" currency={currency} />
            )}
          </span>
          <span className="text-muted-foreground">Conv.</span>
          <span className="flex items-center justify-end gap-1 text-right tabular-nums">
            {formatNumber(m?.conversions)}
            {showDelta && (
              <DeltaPill current={m?.conversions} previous={mp?.conversions} metricKey="conversions" variant="tooltip" currency={currency} />
            )}
          </span>
          <span className="text-muted-foreground">ROAS</span>
          <span className="flex items-center justify-end gap-1 text-right tabular-nums">
            {formatRoas(m?.roas)}
            {showDelta && (
              <DeltaPill current={m?.roas} previous={mp?.roas} metricKey="roas" variant="tooltip" currency={currency} />
            )}
          </span>
        </div>

        {/* Status + Campaign */}
        <div className="flex items-center justify-between gap-2 border-t pt-2">
          <StatusBadge status={ad.status} />
          {ad.campaign_name && (
            <span className="truncate text-xs text-muted-foreground">
              {ad.campaign_name}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── AdRow (list view) ────────────────────────────────────────────────────────

function AdRow({
  ad,
  onClick,
  currency,
  compare = false,
}: {
  ad: Ad;
  onClick: () => void;
  currency: string;
  compare?: boolean;
}) {
  const cp = ad.creative_preview;
  const m  = ad.metrics;
  const mp = ad.metrics_previous;
  const showDelta = compare && !!mp;

  return (
    <div
      className="group flex cursor-pointer items-center gap-3 rounded-lg border bg-card p-3 hover:bg-accent/30 transition-colors"
      onClick={onClick}
    >
      <CreativeThumbnail
        creative={cp}
        className="h-12 w-20 shrink-0 rounded"
        showOverlay={false}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{cp?.title ?? ad.name}</p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <StatusBadge status={ad.status} />
          {ad.campaign_name && (
            <span className="truncate text-xs text-muted-foreground">
              · {ad.campaign_name}
            </span>
          )}
        </div>
      </div>
      <div className="hidden shrink-0 gap-6 text-xs sm:flex">
        <div className="text-right">
          <div className="text-muted-foreground">Spend</div>
          <div className="flex items-center justify-end gap-1 tabular-nums font-medium">
            {formatCurrency(m?.spend, currency)}
            {showDelta && (
              <DeltaPill current={m?.spend} previous={mp?.spend} metricKey="spend" variant="tooltip" currency={currency} />
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-muted-foreground">CTR</div>
          <div className="flex items-center justify-end gap-1 tabular-nums">
            {formatPercent(m?.ctr)}
            {showDelta && (
              <DeltaPill current={m?.ctr} previous={mp?.ctr} metricKey="ctr" variant="tooltip" currency={currency} />
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-muted-foreground">ROAS</div>
          <div className="flex items-center justify-end gap-1 tabular-nums">
            {formatRoas(m?.roas)}
            {showDelta && (
              <DeltaPill current={m?.roas} previous={mp?.roas} metricKey="roas" variant="tooltip" currency={currency} />
            )}
          </div>
        </div>
      </div>
      <AnimatedIcon
        icon={ChevronRight}
        motionPreset="nudgeRight"
        className="shrink-0"
        iconClassName="size-4 text-muted-foreground"
      />
    </div>
  );
}

// ─── AdDetailSheet ────────────────────────────────────────────────────────────

function AdDetailSheet({
  ad,
  onClose,
  currency,
}: {
  ad: Ad | null;
  onClose: () => void;
  currency: string;
}) {
  const { data: creativeRes, isLoading: creativeLoading } = useQuery({
    queryKey: queryKeys.creative(ad?.id ?? ""),
    queryFn:  () => insightsApi.creative(ad!.id),
    enabled:  !!ad,
    refetchInterval: (query) => {
      const meta = (query.state.data as { data?: { meta?: { status?: string } } } | undefined)
        ?.data?.meta;
      return meta?.status === "fetching" ? 3000 : false;
    },
    staleTime: 60 * 60 * 1000,
  });

  const creative: Creative | null =
    (creativeRes?.data?.data?.creative as Creative) ?? null;
  const isFetching =
    (creativeRes?.data as { meta?: { status?: string } } | undefined)?.meta?.status === "fetching";

  const m = ad?.metrics;

  // Registry-driven, account-type-aware metric rows. `tableMetricDefs` is the
  // account-type-filtered ad-level set (standard → standard keys incl.
  // add_to_cart_value / avg_basket_price / post_reactions / post_saves /
  // comments; cpas → the `*_shared` set), so there's no cross-leak by
  // construction. Only render keys actually present (non-null) in this ad's
  // metrics — mirrors overview's presence-filter (P-1/P-2: absence is not a
  // forced zero). Value/currency formatting flows through the shared
  // `formatMetric` + `metricType`, so nothing is hand-formatted per row.
  const { tableMetricDefs } = usePlatformMetrics();
  const metricRows = tableMetricDefs
    .filter((def) => m?.[def.key] != null)
    .map((def) => ({
      key:   def.key,
      label: metricLabel(def.key),
      value: formatMetric(m?.[def.key], metricType(def.key), currency),
    }));

  return (
    <Sheet open={!!ad} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent
        side="right"
        className="flex w-full flex-col overflow-hidden p-0 shadow-xl ring-1 ring-black/5 sm:max-w-2xl !inset-y-3 !right-3 !h-auto !rounded-2xl !border-0"
      >
        <SheetHeader className="shrink-0 border-b px-6 py-4">
          <SheetTitle className="truncate pr-8">
            {creative?.title ?? ad?.name ?? "Ad Detail"}
          </SheetTitle>
          {/* Breadcrumb */}
          {ad?.campaign_name && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <span>{ad.campaign_name}</span>
              {ad.adgroup_name && (
                <>
                  <ChevronRight className="size-3" />
                  <span>{ad.adgroup_name}</span>
                </>
              )}
              <ChevronRight className="size-3" />
              <span className="text-foreground">{ad?.name}</span>
            </div>
          )}
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6">
          {/* Creative */}
          <div className="space-y-4">
            {/* Thumbnail */}
            {creativeLoading || isFetching ? (
              <div className="aspect-[4/5] w-full max-w-[220px] animate-pulse rounded-lg bg-muted" />
            ) : (
              <CreativeThumbnail
                creative={creative}
                fit="contain"
                className="aspect-[4/5] w-full max-w-[220px] rounded-lg"
              />
            )}

            {/* Creative text */}
            <div className="space-y-2 text-sm">
              {creative?.title && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Headline
                  </span>
                  <p className="mt-0.5 font-medium">{creative.title}</p>
                </div>
              )}
              {creative?.body && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Body
                  </span>
                  <p className="mt-0.5 text-muted-foreground">{creative.body}</p>
                </div>
              )}
              {creative?.cta_type && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    CTA
                  </span>
                  <p className="mt-0.5 uppercase tracking-wide">
                    {creative.cta_type.replace(/_/g, " ")}
                  </p>
                </div>
              )}
              {creative?.destination_url && (
                <a
                  href={creative.destination_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <AnimatedIcon icon={ExternalLink} motionPreset="draw" iconClassName="size-3" />
                  <span className="truncate">{creative.destination_url}</span>
                </a>
              )}
              {(creative?.format || ad?.platform) && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {creative?.format && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                      {creative.format}
                    </span>
                  )}
                  {ad?.platform && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                      {ad.platform}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Performance metrics */}
          <div className="w-full space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Performance
            </p>
            <div className="overflow-hidden rounded-xl border bg-card/50">
              {metricRows.map(({ key, label, value }, i) => (
                <div
                  key={key}
                  className={cn(
                    "flex items-start justify-between gap-3 px-3 py-2 text-sm",
                    i > 0 && "border-t"
                  )}
                >
                  <span className="text-muted-foreground">{label}</span>
                  <span className="shrink-0 whitespace-nowrap text-right tabular-nums font-medium">
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── View ─────────────────────────────────────────────────────────────────────

export function AdsView({ preview = false }: { preview?: boolean } = {}) {
  const { accountId, currency } = useSelectedAccount();
  const dateRange = useDateRange();
  const platform  = usePlatform() ?? "meta";
  const withQuery = useSharedFilterQuery();
  const syncActive = useSyncActive();

  const [format,  setFormat]  = useQueryState("format",  { defaultValue: "all" });
  const [adSort,  setAdSort]  = useQueryState("ad_sort", { defaultValue: "spend" });
  const [search,  setSearch]  = useQueryState("search");
  const [compareStr] = useQueryState("compare");
  const compare = compareStr === "true";

  const [searchInput, setSearchInput] = useState(search ?? "");
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput || null), 300);
    return () => clearTimeout(t);
  }, [searchInput, setSearch]);
  useEffect(() => { setSearchInput(search ?? ""); }, [search]);

  const [viewMode,    setViewMode]    = useState<"grid" | "list">("grid");
  const [selectedAd,  setSelectedAd]  = useState<Ad | null>(null);

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: [
      ...queryKeys.table(accountId ?? "", dateRange, "ad", {
        sort_by:    adSort,
        sort_order: "desc",
        search:     search ?? undefined,
        compare_previous: compare || undefined,
      }),
      "infinite",
    ],
    queryFn: ({ pageParam }) =>
      insightsApi.table({
        account_id: accountId!,
        ...dateRange,
        level:      "ad",
        sort_by:    adSort,
        sort_order: "desc",
        search:     search ?? undefined,
        page:       pageParam as number,
        per_page:   PER_PAGE,
        compare_previous: compare || undefined,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const pag = lastPage.data?.pagination;
      if (!pag) return undefined;
      return pag.page < pag.total_pages ? pag.page + 1 : undefined;
    },
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    refetchInterval: (query) => {
      // Poll while a sync is landing (ad rows may not exist yet), and while any
      // row is still missing its lazily-fetched creative preview.
      if (syncActive) return 5000;
      const pages = query.state.data?.pages ?? [];
      const hasEmpty = pages.some((p) =>
        (p.data?.data ?? []).some((ad: Ad) => !ad.creative_preview)
      );
      return hasEmpty ? 5000 : false;
    },
  });

  const allRows: Ad[] = data?.pages.flatMap((p) => p.data?.data ?? []) ?? [];

  // Client-side format filter
  const filtered =
    format === "all"
      ? allRows
      : allRows.filter((ad) => ad.creative_preview?.format === format);

  const total = data?.pages[0]?.data?.pagination?.total ?? 0;

  if (!accountId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No account selected.
      </div>
    );
  }

  // ── Preview mode: top creatives grid + "See All" (no toolbar / load-more) ──
  if (preview) {
    const previewAds = filtered.slice(0, 3);
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-base font-semibold">Ads</p>
            <p className="text-sm text-muted-foreground">Top creatives by spend</p>
          </div>
          <Link
            href={withQuery(`/${platform}/ads`)}
            className="group inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            See All <AnimatedIcon icon={ChevronRight} motionPreset="nudgeRight" iconClassName="size-4" />
          </Link>
        </div>
        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="aspect-[4/5] animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : previewAds.length === 0 ? (
          <SyncAwareEmpty
            jobType="insights_daily"
            emptyLabel="No ads for this period"
            syncingLabel="Syncing ads…"
            height={160}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {previewAds.map((ad) => (
              <AdCard key={ad.id} ad={ad} currency={currency} compare={compare} onClick={() => setSelectedAd(ad)} />
            ))}
          </div>
        )}
        <AdDetailSheet ad={selectedAd} currency={currency} onClose={() => setSelectedAd(null)} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Format */}
        <Select items={FORMAT_OPTIONS} value={format} onValueChange={(v) => setFormat(v)}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FORMAT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select items={SORT_OPTIONS} value={adSort} onValueChange={(v) => setAdSort(v)}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Search */}
        <div className="relative flex-1 min-w-40 max-w-56">
          <Input
            placeholder="Search ads…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="h-8"
          />
          {searchInput && (
            <button
              className="group absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => { setSearchInput(""); setSearch(null); }}
            >
              <AnimatedIcon icon={X} motionPreset="wiggle" iconClassName="size-3.5" />
            </button>
          )}
        </div>

        {/* View toggle */}
        <SegmentControl
          className="ml-auto"
          items={[
            { value: "grid", label: "Grid" },
            { value: "list", label: "List" },
          ]}
          value={viewMode}
          onValueChange={setViewMode}
          ariaLabel="Ad layout"
        />
      </div>

      {/* Count */}
      {!isLoading && (
        <p className="text-xs text-muted-foreground">
          Showing {filtered.length} of {total} ads
        </p>
      )}

      {/* Grid / List */}
      {isLoading ? (
        <div
          className={cn(
            viewMode === "grid"
              ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
              : "space-y-2"
          )}
        >
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="aspect-[4/5] animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <SyncAwareEmpty
          jobType="insights_daily"
          emptyLabel="No ads for this period"
          syncingLabel="Syncing ads…"
          height={256}
        />
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((ad) => (
            <AdCard key={ad.id} ad={ad} currency={currency} compare={compare} onClick={() => setSelectedAd(ad)} />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((ad) => (
            <AdRow key={ad.id} ad={ad} currency={currency} compare={compare} onClick={() => setSelectedAd(ad)} />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasNextPage && (
        <div className="flex justify-center pt-2">
          <Button
            variant="outline"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
          >
            {isFetchingNextPage ? "Loading…" : "Load 25 more"}
          </Button>
        </div>
      )}

      {/* Detail sheet */}
      <AdDetailSheet ad={selectedAd} currency={currency} onClose={() => setSelectedAd(null)} />
    </div>
  );
}
