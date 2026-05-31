import { Suspense } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { SettingsNav } from "@/components/shared/settings-nav";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Suspense fallback={<div className="h-14 shrink-0 border-b bg-card" />}>
          <Header />
        </Suspense>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl">
            <div className="px-6 pt-6">
              <h1 className="text-xl font-semibold">Settings</h1>
            </div>
            <div className="mt-4 px-6">
              <SettingsNav />
            </div>
            <div className="px-6 py-6">
              <Suspense>
                {children}
              </Suspense>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
