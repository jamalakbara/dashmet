import { Suspense } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { PlatformTabs } from "@/components/layout/platform-tabs";
import { SyncStatusBar } from "@/components/shared/sync-status-bar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Suspense fallback={<div className="h-14 shrink-0 border-b bg-card" />}>
          <Header />
        </Suspense>
        <Suspense fallback={null}>
          <SyncStatusBar />
        </Suspense>
        <Suspense fallback={null}>
          <PlatformTabs />
        </Suspense>
        <main className="flex-1 overflow-y-auto p-6">
          <Suspense fallback={<div className="h-full w-full animate-pulse rounded bg-muted/30" />}>
            {children}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
