import { Suspense } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { ControlStrip } from "@/components/layout/control-strip";

/**
 * Base Data shell: fixed indigo sidebar rail on the left, then a column with the
 * light top chrome bar, an action strip, and the scrollable content canvas.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Suspense fallback={<div className="w-60 shrink-0 bg-sidebar" />}>
        <Sidebar />
      </Suspense>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Suspense fallback={<div className="h-16 shrink-0 border-b border-border bg-card" />}>
          <TopBar />
        </Suspense>
        <Suspense fallback={<div className="h-14 shrink-0 border-b border-border bg-card" />}>
          <ControlStrip />
        </Suspense>
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
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
