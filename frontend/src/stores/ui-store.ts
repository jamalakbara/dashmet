import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIStore {
  // Sidebar
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;

  // Column visibility per table level (persisted to localStorage)
  visibleColumns: Record<string, string[]>;
  setVisibleColumns: (level: string, columns: string[]) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      visibleColumns: {},
      setVisibleColumns: (level, columns) =>
        set((state) => ({
          visibleColumns: { ...state.visibleColumns, [level]: columns },
        })),
    }),
    {
      name: "dashmet-ui",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        visibleColumns:   state.visibleColumns,
      }),
    }
  )
);
