"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// ─── Simple pagination ──────────────────────────────────────────────────────

export function PaginationBar({
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
      {/* Full "Showing X–Y of Z" on wider screens; just the total on mobile. */}
      <span className="hidden sm:block">Showing {from}–{to} of {total}</span>
      <span className="shrink-0 sm:hidden">{total} total</span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft className="size-4" />
        </Button>
        {/* Numbered pages on `sm`+; a compact "page / total" on mobile. */}
        <div className="hidden items-center gap-1 sm:flex">
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
        </div>
        <span className="px-2 tabular-nums sm:hidden">
          {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          aria-label="Next page"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
