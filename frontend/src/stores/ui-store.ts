import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Denormalized account row, stored so pinned/recent + the trigger label can
 *  render without the account being present in the current search results. */
export interface AccountSnapshot {
  id: string;
  name: string;
  platform: string;
  currency: string;
  external_id?: string;
  account_type?: string;
}

const RECENT_CAP = 8;

interface UIStore {
  // Sidebar (desktop rail collapse — persisted)
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;

  // Mobile nav drawer (ephemeral — never persisted)
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;

  // Column visibility per table level (persisted to localStorage)
  visibleColumns: Record<string, string[]>;
  setVisibleColumns: (level: string, columns: string[]) => void;

  // Account picker — snapshots + recent + pinned (persisted)
  accountSnapshots: Record<string, AccountSnapshot>;
  recentAccountIds: string[];
  pinnedAccountIds: string[];
  recordAccount: (snapshot: AccountSnapshot) => void;
  togglePin: (id: string) => void;
  clearPlatformSnapshots: (platform: string) => void;
  removeStaleSnapshots: (ids: string[]) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      mobileNavOpen: false,
      setMobileNavOpen: (open) => set({ mobileNavOpen: open }),

      visibleColumns: {},
      setVisibleColumns: (level, columns) =>
        set((state) => ({
          visibleColumns: { ...state.visibleColumns, [level]: columns },
        })),

      accountSnapshots: {},
      recentAccountIds: [],
      pinnedAccountIds: [],
      recordAccount: (snapshot) =>
        set((state) => ({
          accountSnapshots: { ...state.accountSnapshots, [snapshot.id]: snapshot },
          recentAccountIds: [
            snapshot.id,
            ...state.recentAccountIds.filter((id) => id !== snapshot.id),
          ].slice(0, RECENT_CAP),
        })),
      togglePin: (id) =>
        set((state) => ({
          pinnedAccountIds: state.pinnedAccountIds.includes(id)
            ? state.pinnedAccountIds.filter((p) => p !== id)
            : [...state.pinnedAccountIds, id],
        })),
      clearPlatformSnapshots: (platform) =>
        set((state) => {
          const removed = new Set(
            Object.values(state.accountSnapshots)
              .filter((s) => s.platform === platform)
              .map((s) => s.id)
          );
          const nextSnapshots = { ...state.accountSnapshots };
          removed.forEach((id) => delete nextSnapshots[id]);
          return {
            accountSnapshots: nextSnapshots,
            recentAccountIds: state.recentAccountIds.filter((id) => !removed.has(id)),
            pinnedAccountIds: state.pinnedAccountIds.filter((id) => !removed.has(id)),
          };
        }),
      removeStaleSnapshots: (ids) =>
        set((state) => {
          const removed = new Set(ids);
          const nextSnapshots = { ...state.accountSnapshots };
          removed.forEach((id) => delete nextSnapshots[id]);
          return {
            accountSnapshots: nextSnapshots,
            recentAccountIds: state.recentAccountIds.filter((id) => !removed.has(id)),
            pinnedAccountIds: state.pinnedAccountIds.filter((id) => !removed.has(id)),
          };
        }),
    }),
    {
      name: "dashmet-ui",
      partialize: (state) => ({
        sidebarCollapsed:  state.sidebarCollapsed,
        visibleColumns:    state.visibleColumns,
        accountSnapshots:  state.accountSnapshots,
        recentAccountIds:  state.recentAccountIds,
        pinnedAccountIds:  state.pinnedAccountIds,
      }),
    }
  )
);
