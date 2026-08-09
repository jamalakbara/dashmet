import { Suspense } from "react";
import { Sidebar, MobileSidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { ControlStrip } from "@/components/layout/control-strip";

/**
 * DashMet shell: fixed indigo sidebar rail on the left, then a column with the
 * light top chrome bar, an action strip, and the scrollable content canvas.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex h-screen overflow-hidden bg-background">
      <Suspense fallback={<div className="m-3 hidden w-60 shrink-0 rounded-2xl bg-sidebar md:block" />}>
        <Sidebar />
      </Suspense>
      <MobileSidebar />

      <div className="m-3 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl shadow-xl ring-1 ring-black/5 [contain:layout_paint] md:my-3 md:ml-0 md:mr-3">
        <Suspense fallback={<div className="h-16 shrink-0 border-b border-border bg-card" />}>
          <TopBar />
        </Suspense>
        <Suspense fallback={<div className="h-14 shrink-0 border-b border-border bg-card" />}>
          <ControlStrip />
        </Suspense>
        <main className="flex-1 overflow-y-auto p-4 [contain:layout_paint] md:p-6">
          <Suspense
            fallback={
              <div className="h-full w-full animate-pulse rounded-2xl bg-muted/40" />
            }
          >
            {children}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
