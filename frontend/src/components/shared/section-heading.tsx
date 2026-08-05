/**
 * Section heading (bold title + optional muted subtitle) — the shared typographic
 * lead used at the top of every dashboard section (platform overview + combined
 * summary) so the pages read with one consistent structure.
 */
export function SectionHeading({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div>
      <h2 className="text-lg font-bold tracking-tight">{title}</h2>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  );
}
