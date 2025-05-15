import { create } from 'zustand';
import type { Tables } from '../types/supabase'; // Used import type

// --- Mirrored types from backend/models.py for NPC Detail Modal ---
export interface ActionInfo {
    time?: string | null; // e.g., "08:00" or sim_min
    title: string;
    status?: string | null; // e.g., done, queued, active
}

export interface NPCUIDetailData {
    npc_id: string;
    npc_name: string;
    last_completed_action?: ActionInfo | null;
    queued_actions: ActionInfo[];
    latest_reflection?: string | null; // Just the content string
    current_plan_summary: string[]; // List of action titles for current day
}
// --- End Mirrored types ---

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
    selectedNPCDetails: NPCUIDetailData | null;
    isNPCDetailModalOpen: boolean;
    actions: {
        setNPCs: (npcs: DisplayNPC[]) => void;
        setAreas: (areas: DisplayArea[]) => void;
        setClock: (clock: SimClock) => void;
        pushLog: (message: string) => void;
        openNPCDetailModal: (npcId: string, apiUrl: string) => Promise<void>;
        closeNPCDetailModal: () => void;
    };
}

export const useSimStore = create<SimState>((set, get) => ({
    npcs: [],
    areas: [],
    clock: { day: 1, hh: 0, mm: 0 },
    log: [],
    selectedNPCDetails: null,
    isNPCDetailModalOpen: false,
    actions: {
        setNPCs: (newNpcs) => set({ npcs: newNpcs }),
        setAreas: (newAreas) => set({ areas: newAreas }),
        setClock: (newClock) => set({ clock: newClock }),
        pushLog: (message) => set((state) => ({
            log: [message, ...state.log].slice(0, 100)
        })),
        openNPCDetailModal: async (npcId, apiUrl) => {
            if (!apiUrl) {
                console.error("API URL not available for fetching NPC details.");
                get().actions.pushLog("Error: API URL missing, cannot fetch NPC details.");
                return;
            }
            get().actions.pushLog(`Fetching details for NPC: ${npcId}...`);
            try {
                const response = await fetch(`${apiUrl}/npc_details/${npcId}`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch NPC details: ${response.status} ${response.statusText}`);
                }
                const details: NPCUIDetailData = await response.json();
                set({ selectedNPCDetails: details, isNPCDetailModalOpen: true });
                get().actions.pushLog(`Details loaded for ${details.npc_name}.`);
            } catch (error: any) {
                console.error("Error fetching NPC details:", error);
                set({ selectedNPCDetails: null, isNPCDetailModalOpen: false });
                get().actions.pushLog(`Error loading details for NPC ${npcId}: ${error.message}`);
            }
        },
        closeNPCDetailModal: () => set({ isNPCDetailModalOpen: false, selectedNPCDetails: null }),
    },
}));

export const useSimActions = () => useSimStore((state) => state.actions);
