import { create } from 'zustand';
import { Tables } from '../types/supabase'; // Path relative to src

// Define more specific types for frontend state if needed, extending or mapping from Supabase types
export interface DisplayNPC extends Tables<'npc'> { // Or a more specific mapping
    // NPC as defined in supabase.ts might have fields like 'id', 'name', 'traits', 'backstory', 'spawn', 'energy', 'current_action_id'
    // We need x, y for position and an emoji for the dot representation.
    // The spawn field in Tables<'npc'> is likely { x: number; y: number; areaId: string; }
    // For simplicity in Phase 3, let's assume the backend will provide x, y directly or we map it.
    x: number; 
    y: number;
    emoji?: string; // From current action
}

// Area as defined in supabase.ts might be Tables<'area'>: { id, name, bounds: {x,y,w,h} }
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
        setAreas: (areas: DisplayArea[]) => void; // Added for completeness if areas are fetched
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
            log: [message, ...state.log].slice(0, 100) // Add to top, limit to 100
        })),
    },
}));

// Optional: Export actions directly for easier use in components
export const useSimActions = () => useSimStore((state) => state.actions); 