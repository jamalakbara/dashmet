import { Suspense } from "react";
import { Sidebar, MobileSidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { SettingsNav } from "@/components/shared/settings-nav";
import { SettingsReadonlyBanner } from "@/components/shared/settings-readonly-banner";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Suspense fallback={<div className="m-3 hidden w-60 shrink-0 rounded-2xl bg-sidebar md:block" />}>
        <Sidebar />
      </Suspense>
      <MobileSidebar />
      <div className="m-3 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl shadow-xl ring-1 ring-black/5 md:my-3 md:ml-0 md:mr-3">
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
              <SettingsReadonlyBanner />
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
