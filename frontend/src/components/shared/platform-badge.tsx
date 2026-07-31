import { cn } from "@/lib/utils";

interface PlatformBadgeProps {
  platform: string;
  size?: "sm" | "md";
}

const PLATFORM_CONFIG: Record<string, { icon: string; color: string }> = {
  meta:       { icon: "M", color: "bg-blue-600" },
  tiktok:     { icon: "T", color: "bg-black" },
  google_ads: { icon: "G", color: "bg-red-500" },
};

export function PlatformBadge({ platform, size = "sm" }: PlatformBadgeProps) {
  const cfg = PLATFORM_CONFIG[platform] ?? { icon: "?", color: "bg-gray-400" };
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded font-bold text-white",
        size === "sm" ? "size-5 text-[10px]" : "size-7 text-xs",
        cfg.color,
      )}
    >
      {cfg.icon}
    </span>
  );
}
