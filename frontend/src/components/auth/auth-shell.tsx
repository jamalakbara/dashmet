import { TrendingUp, ShieldCheck, Sparkles } from "lucide-react";

const HIGHLIGHTS = [
  {
    icon: TrendingUp,
    title: "Every platform, one view",
    body: "Meta, TikTok and Google Ads side by side.",
  },
  {
    icon: ShieldCheck,
    title: "Numbers you can trust",
    body: "Freshness, coverage and reconciliation on every metric.",
  },
  {
    icon: Sparkles,
    title: "Report-ready in a click",
    body: "Export the exact numbers you see to PPTX.",
  },
];

/**
 * Shared chrome for every auth page (login / signup / forgot / reset …).
 *
 * Mirrors the dashboard's figure/ground: a single floating rounded card on the
 * light-gray canvas. The left half unfolds the indigo rail — same `bg-sidebar`
 * surface, logo treatment and iris signature gradient — and is hidden below
 * `lg`, where a compact brand lockup shows above the form instead.
 *
 * Consumers render only their form content as `children`; the card, brand
 * panel and responsive brand header live here so all auth pages stay coherent.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-6">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl bg-card shadow-[var(--shadow-lift)] ring-1 ring-black/5 lg:grid-cols-2">
        {/* Brand panel — the dashboard's indigo rail, unfolded. Hidden below lg. */}
        <aside className="relative hidden flex-col overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex">
          {/* Iris glow blobs — soft, blurred, low-opacity signature color wash */}
          <div
            aria-hidden
            className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full opacity-30 blur-3xl"
            style={{ backgroundImage: "var(--gradient-iris)" }}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-32 -left-16 size-80 rounded-full opacity-20 blur-3xl"
            style={{ backgroundImage: "var(--gradient-iris)" }}
          />

          {/* Brand lockup — same logo + wordmark as the rail */}
          <div className="relative flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt="DashMet"
              className="size-9 shrink-0 rounded-xl shadow-lg ring-1 ring-white/15"
            />
            <span className="text-[15px] font-bold tracking-tight">DashMet</span>
          </div>

          {/* Hero copy */}
          <div className="relative mt-12 space-y-3">
            <h2 className="text-[1.6rem] font-bold leading-[1.2] tracking-tight">
              Marketing analytics you can actually trust.
            </h2>
            <p className="max-w-xs text-[13px] leading-relaxed text-sidebar-foreground/70">
              Spend, ROAS and results across every ad platform — with the
              freshness and reconciliation to back every number.
            </p>
          </div>

          {/* Value highlights */}
          <ul className="relative mt-10 space-y-5">
            {HIGHLIGHTS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15">
                  <Icon className="size-4" />
                </span>
                <div className="space-y-0.5">
                  <p className="text-[13px] font-semibold leading-tight">
                    {title}
                  </p>
                  <p className="text-xs leading-relaxed text-sidebar-foreground/60">
                    {body}
                  </p>
                </div>
              </li>
            ))}
          </ul>

          {/* Iris signature bar + footer — pinned to the bottom */}
          <div className="relative mt-auto space-y-3 pt-10">
            <div
              aria-hidden
              className="h-1 w-32 rounded-full"
              style={{ backgroundImage: "var(--gradient-iris)" }}
            />
            <p className="text-xs text-sidebar-foreground/45">
              © {new Date().getFullYear()} DashMet — Marketing analytics
              dashboard.
            </p>
          </div>
        </aside>

        {/* Form panel */}
        <main className="flex items-center justify-center p-8 sm:p-10 lg:p-12">
          <div className="w-full max-w-sm space-y-7">
            {/* Compact brand — only shows where the left panel is hidden */}
            <div className="flex items-center gap-3 lg:hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.svg"
                alt="DashMet"
                className="size-10 shrink-0 rounded-xl"
              />
              <span className="text-base font-bold tracking-tight">DashMet</span>
            </div>

            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
