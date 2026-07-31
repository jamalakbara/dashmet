import { Suspense } from "react";
import { TopNav } from "@/components/layout/top-nav";
import { ControlStrip } from "@/components/layout/control-strip";
import { SyncStatusBar } from "@/components/shared/sync-status-bar";

/**
 * OS-window shell: the whole app is framed as a rounded "window" floating on a
 * pure-black desk. Chrome bar (brand · centered pill nav · user) on top, a
 * control strip (sub-tabs · account/date/sync) below, then the bento canvas.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen overflow-hidden bg-[oklch(0.09_0_0)] p-2 sm:p-3">
      <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-[0_24px_80px_-20px_rgba(0,0,0,0.8)]">
        <TopNav />
        <Suspense fallback={<div className="h-12 shrink-0 border-b border-border" />}>
          <ControlStrip />
        </Suspense>
        <Suspense fallback={null}>
          <SyncStatusBar />
        </Suspense>
        <main className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-5">
          <Suspense
            fallback={
              <div className="h-full w-full animate-pulse rounded-2xl bg-muted/30" />
            }
          >
            {children}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
