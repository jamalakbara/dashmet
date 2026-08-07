import { SyncStatusBadge } from "@/components/shared/sync-status-badge";

/**
 * Section heading (bold title + optional muted subtitle) — the shared typographic
 * lead used at the top of every dashboard section (platform overview + combined
 * summary) so the pages read with one consistent structure.
 *
 * `freshness` opts the heading into a mobile-only sync/freshness badge rendered
 * beneath the subtitle. The badge otherwise lives in the top bar, which hides it
 * below `md`; surfacing it under the page's primary heading keeps every number's
 * freshness visible on phones (P-1) without crowding the narrow top bar.
 */
export function SectionHeading({
  title,
  subtitle,
  freshness = false,
}: {
  title: string;
  subtitle?: string;
  freshness?: boolean;
}) {
  return (
    <div>
      <h2 className="text-lg font-bold tracking-tight">{title}</h2>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      {freshness && (
        <div className="mt-2 md:hidden">
          <SyncStatusBadge />
        </div>
      )}
    </div>
  );
}
