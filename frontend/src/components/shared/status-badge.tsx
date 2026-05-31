import { cn } from "@/lib/utils";
import type { EntityStatus } from "@/types/enums";

const STATUS_CONFIG: Record<EntityStatus, { label: string; dot: string }> = {
  active:   { label: "Active",   dot: "bg-green-500" },
  paused:   { label: "Paused",   dot: "bg-yellow-500" },
  archived: { label: "Archived", dot: "bg-muted-foreground" },
  deleted:  { label: "Deleted",  dot: "bg-red-500" },
};

export function StatusBadge({ status }: { status: EntityStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.archived;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={cn("inline-block size-1.5 rounded-full", config.dot)} />
      {config.label}
    </span>
  );
}
