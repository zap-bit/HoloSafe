import { create } from 'zustand'
import type { Snapshot } from './types'

export type Link = 'connecting' | 'live' | 'lost'

interface UIState {
  snap: Snapshot | null
  link: Link
  fromCache: boolean
  pulses: { edge_id: string; at: number }[]
  syncing: number // count of items being synced (for animation)
  setSnap: (s: Snapshot, fromCache?: boolean) => void
  setLink: (l: Link) => void
  pulse: (edge_id: string) => void
  setSyncing: (n: number) => void
}

export const useStore = create<UIState>((set) => ({
  snap: null,
  link: 'connecting',
  fromCache: false,
  pulses: [],
  syncing: 0,
  setSnap: (snap, fromCache = false) => set({ snap, fromCache }),
  setLink: (link) => set({ link }),
  pulse: (edge_id) => set((s) => ({ pulses: [...s.pulses.filter((p) => Date.now() - p.at < 6000), { edge_id, at: Date.now() }] })),
  setSyncing: (syncing) => set({ syncing }),
}))
