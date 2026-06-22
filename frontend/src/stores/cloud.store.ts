import { create } from "zustand";

import type { CloudProvider } from "@/types";

// Client-side UI state for cloud/cost views (selected filters, sync indicator).
interface CloudState {
  selectedProviders: CloudProvider[];
  timeRange: 7 | 30 | 90;
  lastSyncAt: number;
  toggleProvider: (p: CloudProvider) => void;
  setTimeRange: (r: 7 | 30 | 90) => void;
  markSynced: () => void;
}

export const useCloudStore = create<CloudState>((set) => ({
  selectedProviders: ["azure", "aws", "gcp"],
  timeRange: 90,
  lastSyncAt: Date.now(),

  toggleProvider: (p) =>
    set((s) => ({
      selectedProviders: s.selectedProviders.includes(p)
        ? s.selectedProviders.filter((x) => x !== p)
        : [...s.selectedProviders, p],
    })),
  setTimeRange: (r) => set({ timeRange: r }),
  markSynced: () => set({ lastSyncAt: Date.now() }),
}));
