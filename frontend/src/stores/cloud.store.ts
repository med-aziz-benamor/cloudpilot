import { create } from "zustand";

// Client-side UI state shared across cost views (the time-range selector).
interface CloudState {
  timeRange: 7 | 30 | 90;
  setTimeRange: (r: 7 | 30 | 90) => void;
}

export const useCloudStore = create<CloudState>((set) => ({
  timeRange: 90,
  setTimeRange: (r) => set({ timeRange: r }),
}));
