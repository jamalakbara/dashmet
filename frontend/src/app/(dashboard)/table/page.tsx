"use client";

import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useQueryState, parseAsInteger } from "nuqs";
import { useRouter } from "next/navigation";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  Download,
  ChevronRight,
  ChevronDown,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/shared/status-badge";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { useUIStore } from "@/stores/ui-store";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatRoas,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { EntityStatus } from "@/types/enums";

// ─── Types ────────────────────────────────────────────────────────────────────

type CellType =
  | "name" | "status" | "text" | "currency" | "number"
  | "percent" | "roas" | "creative";

interface ColDef {
  key: string;
  label: string;
  cell: CellType;
  sortable: boolean;
  defaultVisible: boolean;
  align: "left" | "right";
  metricKey?: string; // resolves from row.metrics[metricKey] if set
}

interface Metrics {
  spend?: number;
  impressions?: number;
  reach?: number;
  frequency?: number;
  clicks?: number;
  inline_link_clicks?: number;
  ctr?: number;
  cpm?: number;
  cpc?: number;
  cpp?: number;
  conversions?: number;
  conversion_value?: number;
  roas?: number;
  cpa?: number;
}

interface CreativePreview {
  title?: string;
  thumbnail_url?: string | null;
  format?: string;
  cta_type?: string;
}

interface TableRow {
  id: string;
  name: string;
  status: EntityStatus;
  effective_status?: EntityStatus;
  objective?: string;
  platform?: string;
  daily_budget?: number;
  campaign_name?: string;
  campaign_id?: string;
  adgroup_name?: string;
  adgroup_id?: string;
  optimization_goal?: string;
  bid_amount?: number;
  has_creative?: boolean;
  creative_preview?: CreativePreview;
  metrics?: Metrics;
}

// ─── Column definitions ───────────────────────────────────────────────────────

const METRIC_COLS: ColDef[] = [
  { key: "spend",            label: "Spend",       cell: "currency", sortable: true, defaultVisible: true,  align: "right", metricKey: "spend" },
  { key: "impressions",      label: "Impressions", cell: "number",   sortable: true, defaultVisible: true,  align: "right", metricKey: "impressions" },
  { key: "reach",            label: "Reach",       cell: "number",   sortable: true, defaultVisible: false, align: "right", metricKey: "reach" },
  { key: "clicks",           label: "Clicks",      cell: "number",   sortable: true, defaultVisible: true,  align: "right", metricKey: "clicks" },
  { key: "ctr",              label: "CTR",         cell: "percent",  sortable: true, defaultVisible: true,  align: "right", metricKey: "ctr" },
  { key: "cpm",              label: "CPM",         cell: "currency", sortable: true, defaultVisible: false, align: "right", metricKey: "cpm" },
  { key: "cpc",              label: "CPC",         cell: "currency", sortable: true, defaultVisible: false, align: "right", metricKey: "cpc" },
  { key: "conversions",      label: "Conv.",       cell: "number",   sortable: true, defaultVisible: true,  align: "right", metricKey: "conversions" },
  { key: "conversion_value", label: "Conv. Value", cell: "currency", sortable: true, defaultVisible: false, align: "right", metricKey: "conversion_value" },
  { key: "roas",             label: "ROAS",        cell: "roas",     sortable: true, defaultVisible: true,  align: "right", metricKey: "roas" },
  { key: "cpa",              label: "CPA",         cell: "currency", sortable: true, defaultVisible: false, align: "right", metricKey: "cpa" },
];

const COLUMNS: Record<string, ColDef[]> = {
  campaign: [
    { key: "name",         label: "Campaign",     cell: "name",     sortable: true,  defaultVisible: true, align: "left" },
    { key: "status",       label: "Status",       cell: "status",   sortable: true,  defaultVisible: true, align: "left" },
    { key: "objective",    label: "Objective",    cell: "text",     sortable: false, defaultVisible: true, align: "left" },
    { key: "daily_budget", label: "Daily Budget", cell: "currency", sortable: true,  defaultVisible: true, align: "right" },
    ...METRIC_COLS,
  ],
  adgroup: [
    { key: "name",              label: "Ad Group",  cell: "name",     sortable: true,  defaultVisible: true,  align: "left" },
    { key: "campaign_name",     label: "Campaign",  cell: "text",     sortable: false, defaultVisible: true,  align: "left" },
    { key: "status",            label: "Status",    cell: "status",   sortable: true,  defaultVisible: true,  align: "left" },
    { key: "optimization_goal", label: "Opt. Goal", cell: "text",     sortable: false, defaultVisible: true,  align: "left" },
    { key: "bid_amount",        label: "Bid",       cell: "currency", sortable: true,  defaultVisible: false, align: "right" },
    ...METRIC_COLS,
  ],
  ad: [
    { key: "creative_preview", label: "Creative", cell: "creative", sortable: false, defaultVisible: true, align: "left" },
    { key: "name",             label: "Ad",       cell: "name",     sortable: true,  defaultVisible: true, align: "left" },
    { key: "status",           label: "Status",   cell: "status",   sortable: true,  defaultVisible: true, align: "left" },
    ...METRIC_COLS,
  ],
};

const LEVEL_TABS = [
  { value: "campaign", label: "Campaigns" },
  { value: "adgroup",  label: "Ad Groups" },
  { value: "ad",       label: "Ads" },
];

const STATUS_OPTIONS = [
  { value: "all",      label: "All statuses" },
  { value: "active",   label: "Active" },
  { value: "paused",   label: "Paused" },
  { value: "archived", label: "Archived" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getCellValue(row: TableRow, col: ColDef): unknown {
  if (col.metricKey) return (row.metrics as Record<string, unknown>)?.[col.metricKey] ?? null;
  return (row as unknown as Record<string, unknown>)[col.key] ?? null;
}

function renderCell(row: TableRow, col: ColDef, onDrillDown: () => void): React.ReactNode {
  const v = getCellValue(row, col);

  switch (col.cell) {
    case "name":
      return (
        <button
          onClick={(e) => { e.stopPropagation(); onDrillDown(); }}
          className="max-w-[280px] truncate text-left font-medium text-primary hover:underline"
        >
          {row.name}
        </button>
      );
    case "status":
      return <StatusBadge status={v as EntityStatus} />;
    case "creative": {
      const cp = row.creative_preview;
      if (!cp) return <div className="h-8 w-12 animate-pulse rounded bg-muted" />;
      return (
        <div className="flex items-center gap-2">
          {cp.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={cp.thumbnail_url} alt="" className="h-8 w-12 rounded object-cover" />
          ) : (
            <div className="h-8 w-12 rounded bg-muted" />
          )}
          <span className="max-w-[180px] truncate text-xs text-muted-foreground">
            {cp.title ?? "—"}
          </span>
        </div>
      );
    }
    case "text":
      return <span className="text-sm">{v != null ? String(v) : "—"}</span>;
    case "currency":
      return <span className="tabular-nums">{formatCurrency(v as number)}</span>;
    case "number":
      return <span className="tabular-nums">{formatNumber(v as number)}</span>;
    case "percent":
      return <span className="tabular-nums">{formatPercent(v as number)}</span>;
    case "roas":
      return <span className="tabular-nums">{formatRoas(v as number)}</span>;
    default:
      return "—";
  }
}

function exportCSV(rows: TableRow[], cols: ColDef[]) {
  const headers = cols.map((c) => c.label).join(",");
  const body = rows.map((row) =>
    cols.map((col) => {
      const v = getCellValue(row, col);
      const s = v == null ? "" : String(v);
      return s.includes(",") ? `"${s}"` : s;
    }).join(",")
  ).join("\n");
  const blob = new Blob([`${headers}\n${body}`], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "dashmet-export.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Sort header ──────────────────────────────────────────────────────────────

function SortIcon({ col, sortBy, sortOrder }: {
  col: ColDef;
  sortBy: string;
  sortOrder: string;
}) {
  if (!col.sortable) return null;
  if (sortBy !== col.key) return <ArrowUpDown className="ml-1 inline size-3 opacity-40" />;
  return sortOrder === "asc"
    ? <ArrowUp className="ml-1 inline size-3" />
    : <ArrowDown className="ml-1 inline size-3" />;
}

// ─── Simple pagination ────────────────────────────────────────────────────────

function TablePagination({
  page,
  totalPages,
  total,
  perPage,
  onPage,
}: {
  page: number;
  totalPages: number;
  total: number;
  perPage: number;
  onPage: (p: number) => void;
}) {
  const from = (page - 1) * perPage + 1;
  const to   = Math.min(page * perPage, total);

  const pages: (number | "…")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("…");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
    if (page < totalPages - 2) pages.push("…");
    pages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 text-sm text-muted-foreground">
      <span>Showing {from}–{to} of {total}</span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          ←
        </Button>
        {pages.map((p, i) =>
          p === "…" ? (
            <span key={`ellipsis-${i}`} className="px-1">…</span>
          ) : (
            <Button
              key={p}
              variant={p === page ? "default" : "ghost"}
              size="sm"
              onClick={() => onPage(p as number)}
            >
              {p}
            </Button>
          )
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          →
        </Button>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TablePage() {
  const router     = useRouter();
  const accountId  = useAccountId();
  const dateRange  = useDateRange();
  const { visibleColumns, setVisibleColumns } = useUIStore();

  // URL state
  const [level,      setLevel]      = useQueryState("level",      { defaultValue: "campaign" });
  const [status,     setStatus]     = useQueryState("status",     { defaultValue: "all" });
  const [sortBy,     setSortBy]     = useQueryState("sort_by",    { defaultValue: "spend" });
  const [sortOrder,  setSortOrder]  = useQueryState("sort_order", { defaultValue: "desc" });
  const [page,       setPage]       = useQueryState("page",       parseAsInteger.withDefault(1));
  const [campaignId, setCampaignId] = useQueryState("campaign_id");
  const [adgroupId,  setAdgroupId]  = useQueryState("adgroup_id");
  const [search,     setSearch]     = useQueryState("search");

  // Local search input — debounce → URL
  const [searchInput, setSearchInput] = useState(search ?? "");
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput || null), 300);
    return () => clearTimeout(t);
  }, [searchInput, setSearch]);

  // Keep search input in sync when URL changes externally
  useEffect(() => { setSearchInput(search ?? ""); }, [search]);

  // Expanded row (local)
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const cols    = COLUMNS[level] ?? COLUMNS.campaign;
  const stored  = visibleColumns[level];
  const visible = new Set<string>(
    stored ?? cols.filter((c) => c.defaultVisible).map((c) => c.key)
  );
  const visibleCols = cols.filter((c) => visible.has(c.key));

  const PER_PAGE = 25;

  const { data: res, isLoading } = useQuery({
    queryKey: queryKeys.table(accountId ?? "", dateRange, level, {
      status:   status !== "all" ? status : undefined,
      search:   search ?? undefined,
      sort_by:  sortBy,
      sort_order: sortOrder,
      page,
      campaign_id: campaignId ?? undefined,
      adgroup_id:  adgroupId ?? undefined,
    }),
    queryFn: () =>
      insightsApi.table({
        account_id:  accountId!,
        ...dateRange,
        level,
        status:      status !== "all" ? status : undefined,
        search:      search ?? undefined,
        sort_by:     sortBy,
        sort_order:  sortOrder,
        page,
        per_page:    PER_PAGE,
        campaign_id: campaignId ?? undefined,
        adgroup_id:  adgroupId ?? undefined,
      }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
  });

  const rows: TableRow[]  = res?.data?.data ?? [];
  const pagination        = res?.data?.pagination;
  const total: number     = pagination?.total ?? 0;
  const totalPages        = pagination?.total_pages ?? (Math.ceil(total / PER_PAGE) || 1);

  function handleSort(col: ColDef) {
    if (!col.sortable) return;
    if (sortBy === col.key) {
      setSortOrder(sortOrder === "desc" ? "asc" : "desc");
    } else {
      setSortBy(col.key);
      setSortOrder("desc");
    }
    setPage(1);
  }

  function switchLevel(newLevel: string) {
    setLevel(newLevel);
    setPage(1);
    setCampaignId(null);
    setAdgroupId(null);
    setExpandedId(null);
  }

  function drillDown(row: TableRow) {
    if (level === "campaign") {
      setLevel("adgroup");
      setCampaignId(row.id);
      setAdgroupId(null);
      setPage(1);
      setExpandedId(null);
    } else if (level === "adgroup") {
      setLevel("ad");
      setAdgroupId(row.id);
      setPage(1);
      setExpandedId(null);
    }
  }

  function toggleColumn(key: string) {
    const next = visible.has(key)
      ? cols.filter((c) => visible.has(c.key) && c.key !== key).map((c) => c.key)
      : [...visible, key];
    setVisibleColumns(level, next);
  }

  if (!accountId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No account selected.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Level tabs */}
      <Tabs value={level} onValueChange={switchLevel}>
        <TabsList>
          {LEVEL_TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Drill-down breadcrumb */}
      {(campaignId || adgroupId) && (
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <button
            onClick={() => switchLevel("campaign")}
            className="hover:text-foreground hover:underline"
          >
            Campaigns
          </button>
          {campaignId && (
            <>
              <ChevronRight className="size-3.5" />
              <span className="text-foreground">
                {adgroupId ? (
                  <button
                    onClick={() => {
                      setLevel("adgroup");
                      setAdgroupId(null);
                      setPage(1);
                    }}
                    className="hover:underline"
                  >
                    Ad Groups
                  </button>
                ) : "Ad Groups"}
              </span>
            </>
          )}
          {adgroupId && (
            <>
              <ChevronRight className="size-3.5" />
              <span className="text-foreground">Ads</span>
            </>
          )}
        </div>
      )}

      <Card>
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          {/* Search */}
          <div className="relative flex-1 min-w-48 max-w-64">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search…"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value);
                setPage(1);
              }}
              className="pl-8 h-8"
            />
          </div>

          {/* Status filter */}
          <Select
            value={status}
            onValueChange={(v) => { setStatus(v); setPage(1); }}
          >
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Columns visibility */}
          <Popover>
            <PopoverTrigger className="flex h-8 items-center gap-1.5 rounded-lg border border-input bg-transparent px-2.5 text-sm whitespace-nowrap hover:bg-accent">
              Columns
            </PopoverTrigger>
            <PopoverContent align="end" className="w-44 p-3">
              <p className="mb-2 text-xs text-muted-foreground">Toggle columns</p>
              <div className="space-y-1.5">
                {cols.map((col) => (
                  <label key={col.key} className="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox
                      checked={visible.has(col.key)}
                      onCheckedChange={() => toggleColumn(col.key)}
                    />
                    {col.label}
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          {/* Export */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCSV(rows, visibleCols)}
            disabled={rows.length === 0}
          >
            <Download className="size-3.5" />
            Export
          </Button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                {visibleCols.map((col) => (
                  <TableHead
                    key={col.key}
                    className={cn(
                      col.sortable && "cursor-pointer select-none hover:text-foreground",
                      col.align === "right" && "text-right"
                    )}
                    onClick={() => handleSort(col)}
                  >
                    {col.label}
                    <SortIcon col={col} sortBy={sortBy} sortOrder={sortOrder} />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 10 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell />
                      {visibleCols.map((col) => (
                        <TableCell key={col.key}>
                          <div className="h-4 animate-pulse rounded bg-muted" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : rows.length === 0
                ? (
                    <TableRow>
                      <TableCell colSpan={visibleCols.length + 1} className="py-12 text-center text-muted-foreground">
                        No results
                      </TableCell>
                    </TableRow>
                  )
                : rows.map((row) => (
                    <React.Fragment key={row.id}>
                      <TableRow
                        className="cursor-pointer"
                        onClick={() =>
                          setExpandedId(expandedId === row.id ? null : row.id)
                        }
                      >
                        {/* Expand chevron */}
                        <TableCell className="w-8 text-muted-foreground">
                          {expandedId === row.id
                            ? <ChevronDown className="size-3.5" />
                            : <ChevronRight className="size-3.5" />}
                        </TableCell>

                        {visibleCols.map((col) => (
                          <TableCell
                            key={col.key}
                            className={cn(
                              col.align === "right" && "text-right",
                              col.key === "name" && "sticky left-0 bg-card"
                            )}
                          >
                            {renderCell(row, col, () => drillDown(row))}
                          </TableCell>
                        ))}
                      </TableRow>

                      {/* Expanded detail row */}
                      {expandedId === row.id && (
                        <TableRow key={`${row.id}-expanded`} className="bg-muted/30">
                          <TableCell />
                          <TableCell colSpan={visibleCols.length} className="py-3">
                            <div className="flex items-center gap-4 text-sm">
                              {level === "campaign" && (
                                <button
                                  onClick={() => drillDown(row)}
                                  className="flex items-center gap-1 text-primary hover:underline"
                                >
                                  View ad groups <ChevronRight className="size-3.5" />
                                </button>
                              )}
                              {level === "adgroup" && (
                                <button
                                  onClick={() => drillDown(row)}
                                  className="flex items-center gap-1 text-primary hover:underline"
                                >
                                  View ads <ChevronRight className="size-3.5" />
                                </button>
                              )}
                              {level === "ad" && row.creative_preview && (
                                <div className="flex items-center gap-3">
                                  {row.creative_preview.thumbnail_url && (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img
                                      src={row.creative_preview.thumbnail_url}
                                      alt=""
                                      className="h-16 w-24 rounded object-cover"
                                    />
                                  )}
                                  <div className="space-y-0.5 text-muted-foreground">
                                    <p className="font-medium text-foreground">
                                      {row.creative_preview.title ?? "—"}
                                    </p>
                                    <p className="text-xs">
                                      Format: {row.creative_preview.format ?? "—"} ·
                                      CTA: {row.creative_preview.cta_type ?? "—"}
                                    </p>
                                  </div>
                                </div>
                              )}
                              {level === "ad" && !row.creative_preview && (
                                <span className="text-muted-foreground text-xs">No creative available</span>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        {!isLoading && total > 0 && (
          <TablePagination
            page={page}
            totalPages={totalPages}
            total={total}
            perPage={PER_PAGE}
            onPage={(p) => { setPage(p); setExpandedId(null); }}
          />
        )}
      </Card>
    </div>
  );
}
