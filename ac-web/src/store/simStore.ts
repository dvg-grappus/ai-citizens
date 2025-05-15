import { create } from 'zustand';
import type { Tables } from '../types/supabase'; // Used import type

export interface DisplayNPC extends Tables<'npc'> {
    x: number; 
    y: number;
    emoji?: string;
}

export type DisplayArea = Tables<'area'>;

export interface SimClock {
    day: number;
    hh: number;
    mm: number;
}

interface SimState {
    npcs: DisplayNPC[];
    areas: DisplayArea[];
    clock: SimClock;
    log: string[];
    actions: {
        setNPCs: (npcs: DisplayNPC[]) => void;
        setAreas: (areas: DisplayArea[]) => void;
        setClock: (clock: SimClock) => void;
        pushLog: (message: string) => void;
    };
}

export const useSimStore = create<SimState>((set) => ({
    npcs: [],
    areas: [],
    clock: { day: 1, hh: 0, mm: 0 },
    log: [],
    actions: {
        setNPCs: (newNpcs) => set({ npcs: newNpcs }),
        setAreas: (newAreas) => set({ areas: newAreas }),
        setClock: (newClock) => set({ clock: newClock }),
        pushLog: (message) => set((state) => ({
            log: [message, ...state.log].slice(0, 100)
        })),
    },
}));

export const useSimActions = () => useSimStore((state) => state.actions);
