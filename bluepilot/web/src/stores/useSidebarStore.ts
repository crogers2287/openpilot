import { create } from 'zustand'

interface SidebarState {
  // Only meaningful on narrow viewports, where the sidebar is an off-canvas
  // drawer. On desktop the rail is always visible and this is ignored.
  isOpen: boolean
  open: () => void
  close: () => void
  toggle: () => void
}

export const useSidebarStore = create<SidebarState>((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set((state) => ({ isOpen: !state.isOpen })),
}))
