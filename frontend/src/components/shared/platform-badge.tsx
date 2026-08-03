import { cn } from "@/lib/utils";

interface PlatformBadgeProps {
  platform: string;
  size?: "sm" | "md";
}

// Platforms with a real logo asset in /public render the SVG; others fall back
// to a colored letter tile.
const PLATFORM_LOGO: Record<string, string> = {
  meta:   "/meta-logo.svg",
  tiktok: "/tiktok-logo.svg",
};

const PLATFORM_CONFIG: Record<string, { icon: string; color: string }> = {
  meta:       { icon: "M", color: "bg-blue-600" },
  tiktok:     { icon: "T", color: "bg-black" },
  google_ads: { icon: "G", color: "bg-red-500" },
};

export function PlatformBadge({ platform, size = "sm" }: PlatformBadgeProps) {
  const logo = PLATFORM_LOGO[platform];
  const sizeCls = size === "sm" ? "size-5" : "size-7";

  if (logo) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logo}
        alt={platform}
        className={cn("shrink-0 rounded-full", sizeCls)}
      />
    );
  }

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
