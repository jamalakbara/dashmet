import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface CardChipHeaderProps {
  icon: LucideIcon;
  title: string;
  /** Tailwind bg color for the round icon chip (e.g. "bg-orange-500"). */
  accent?: string;
  /** Right-aligned slot (e.g. a "See Detail" link or delta pill). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * The shared card header used across every dashboard card — a colored round icon
 * chip + a bold title, with an optional right-aligned action. Matches the
 * platform overview `MetricGroupCard` header 1:1 so platform and combined-summary
 * cards read identically.
 */
export function CardChipHeader({
  icon: Icon,
  title,
  accent = "bg-primary",
  action,
  className,
}: CardChipHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-3", className)}>
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex size-8 items-center justify-center rounded-full text-white",
            accent,
          )}
        >
          <Icon className="size-[18px]" />
        </span>
        <span className="text-base font-semibold">{title}</span>
      </div>
      {action}
    </div>
  );
}
