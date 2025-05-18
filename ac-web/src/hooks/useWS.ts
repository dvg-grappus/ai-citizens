import { useEffect, useRef } from 'react';
// import { io, Socket } from 'socket.io-client'; // Remove socket.io-client import
import { useSimStore } from '../store/simStore';
import type { SimClock, DisplayNPC, DisplayArea } from '../store/simStore'; // Import types
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';

dayjs.extend(duration);

interface BackendState {
    npcs: DisplayNPC[];
    areas: DisplayArea[];
    sim_clock: {
        sim_min: number;
    };
    environment: {
        day: number;
    };
}

export const useWS = () => {
    const { setNPCs, setAreas, setClock, pushLog, closeNPCDetailModal, refreshNPCDetailModal } = useSimStore((state) => state.actions);
    const socketRef = useRef<WebSocket | null>(null); // Changed type to native WebSocket

    const apiUrl = import.meta.env.VITE_API_URL;
    let wsUrl = '';
    if (apiUrl) {
        wsUrl = apiUrl.replace('http', 'ws') + '/ws';
    } else {
        console.error('VITE_API_URL is not defined! Check your .env file in the ac-web directory.');
    }

    useEffect(() => {
        if (!wsUrl) return;

        // const socket = io(wsUrl); // Remove socket.io-client usage
        const socket = new WebSocket(wsUrl); // Use native WebSocket
        socketRef.current = socket;

        socket.onopen = (event) => {
            // Remove verbose console log
            pushLog('Connected to simulation server.');
            fetchState("onOpen");
        };

        socket.onclose = (event) => {
            // Remove verbose console log
            pushLog(`Disconnected: Code ${event.code}`);
        };

        socket.onerror = (event) => {
            console.error("WebSocket error occurred");
            pushLog(`WebSocket error occurred.`);
        };

        socket.onmessage = (event) => {
            const rawData = event.data;
            try {
                const messageWrapper = typeof rawData === 'string' ? JSON.parse(rawData) : rawData;

                if (messageWrapper.type === 'tick_update' && messageWrapper.data) {
                    fetchState("onTick");
                }
                else if (messageWrapper.type === 'sim_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    if (eventData && eventData.description) {
                        let emoji = "⚠️"; 
                        
                        // Handle built-in event types
                        if (eventData.event_code === 'fire_alarm') emoji = "🔥";
                        if (eventData.event_code === 'pizza_drop') emoji = "🍕";
                        if (eventData.event_code === 'wifi_down') emoji = "📉";
                        
                        // Handle user-generated events
                        if (eventData.event_code === 'user_event') {
                            // If the message already has an emoji at the start, use it
                            const messageHasEmoji = /^\p{Emoji}/u.test(eventData.description);
                            emoji = messageHasEmoji ? "" : "🌐"; // Use globe emoji for user events if none present
                        }
                        
                        // Add user indicator if this is a user-generated event
                        const userPrefix = eventData.user_generated ? "USER EVENT: " : "EVENT: ";
                        pushLog(`${emoji} DAY ${eventData.day || '-'} ${userPrefix}${eventData.description}`);
                    }
                }
                else if (messageWrapper.type === 'planning_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    pushLog(`📋 PLAN D${eventData.day || '-'}: ${eventData.npc_name} ${eventData.status}${eventData.num_actions ? ' ('+eventData.num_actions+' actions)' : ''}.`);
                    
                    // Refresh NPC detail modal for the NPC whose plan changed
                    if (apiUrl && useSimStore.getState().isNPCDetailModalOpen) {
                        const selectedNPC = useSimStore.getState().selectedNPCDetails;
                        if (selectedNPC && selectedNPC.npc_name === eventData.npc_name) {
                            setTimeout(() => {
                                refreshNPCDetailModal(apiUrl);
                            }, 500);
                        }
                    }
                }
                else if (messageWrapper.type === 'reflection_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    pushLog(`🤔 REFLECT D${eventData.day || '-'}: ${eventData.npc_name} ${eventData.status}.`);
                    
                    // Refresh NPC detail modal for the NPC with new reflections
                    if (apiUrl && useSimStore.getState().isNPCDetailModalOpen) {
                        const selectedNPC = useSimStore.getState().selectedNPCDetails;
                        if (selectedNPC && selectedNPC.npc_name === eventData.npc_name) {
                            setTimeout(() => {
                                refreshNPCDetailModal(apiUrl);
                            }, 500);
                        }
                    }
                }
                else if (messageWrapper.type === 'action_start' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    let timeStr = "";
                    if (eventData.sim_time !== undefined) {
                        const hours = Math.floor(eventData.sim_time / 60).toString().padStart(2, '0');
                        const minutes = (eventData.sim_time % 60).toString().padStart(2, '0');
                        timeStr = `${hours}:${minutes}`;
                    }
                    pushLog(`${eventData.emoji || '🎬'} D${eventData.day || '-'} ${timeStr} ${eventData.npc_name}: ${eventData.action_title}`);
                    
                    // Refresh NPC detail modal if open - action updates likely affect completed actions
                    if (apiUrl && useSimStore.getState().isNPCDetailModalOpen) {
                        const selectedNPC = useSimStore.getState().selectedNPCDetails;
                        if (selectedNPC) {
                            // Refresh with a slight delay to allow database updates to complete
                            setTimeout(() => {
                                refreshNPCDetailModal(apiUrl);
                            }, 500);
                        }
                    }
                }
                // START - New handler for social_event
                else if (messageWrapper.type === 'social_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    let timeStr = "";
                    if (eventData.sim_min_of_day !== undefined) {
                        const hours = Math.floor(eventData.sim_min_of_day / 60).toString().padStart(2, '0');
                        const minutes = (eventData.sim_min_of_day % 60).toString().padStart(2, '0');
                        timeStr = `${hours}:${minutes}`;
                    }
                    // Example: 👀 D2 05:15 Alice: Saw Bob in the Lounge.
                    pushLog(`👀 D${eventData.day || '-'} ${timeStr} ${eventData.observer_npc_name}: ${eventData.description}`);
                }
                // END - New handler for social_event

                // START - New handler for dialogue_event
                else if (messageWrapper.type === 'dialogue_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    let timeStr = "";
                    if (eventData.sim_min_of_day !== undefined) {
                        const hours = Math.floor(eventData.sim_min_of_day / 60).toString().padStart(2, '0');
                        const minutes = (eventData.sim_min_of_day % 60).toString().padStart(2, '0');
                        timeStr = `${hours}:${minutes}`;
                    }
                    // Example: 💬 D2 05:15 Alice (re Bob): I talked with Bob about watching shows.
                    pushLog(`💬 D${eventData.day || '-'} ${timeStr} ${eventData.npc_name} (re ${eventData.other_participant_name}): ${eventData.summary}`);
                }
                // END - New handler for dialogue_event

            } catch (e) {
                console.error('Error handling WebSocket message');
                pushLog('Received malformed data from server.');
            }
        };

        const fetchState = async (context: string) => {
            if (!apiUrl) { console.error("No API URL available"); return; }
            try {
                const response = await fetch(`${apiUrl}/state`);
                if (!response.ok) throw new Error(`Fetch /state failed: ${response.status}`);
                const stateData = await response.json() as BackendState;

                if (stateData.npcs) {
                    // Remove NPC logging completely
                    
                    // Check if the current selected NPC still exists in the updated NPC list
                    const selectedNPCDetails = useSimStore.getState().selectedNPCDetails;
                    if (selectedNPCDetails) {
                        const selectedNpcId = selectedNPCDetails.npc_id;
                        // Close the modal only if the selected NPC no longer exists
                        const npcExists = stateData.npcs.some(npc => npc.id === selectedNpcId);
                        if (!npcExists) {
                            closeNPCDetailModal();
                        }
                    }
                    
                    // Update NPCs in the store
                    setNPCs(stateData.npcs);
                }
                
                if (stateData.areas) {
                    // Only log area data once at startup
                    setAreas(stateData.areas);
                }

                if (stateData.sim_clock && stateData.environment) {
                    const totalSimMinutesInDay = stateData.sim_clock.sim_min;
                    const currentDay = stateData.environment.day;
                    const d = dayjs.duration(totalSimMinutesInDay, 'minutes');
                    const hh = d.hours();
                    const mm = d.minutes();
                    setClock({ day: currentDay, hh, mm });
                    pushLog(`Tick: Day ${currentDay} - ${hh.toString().padStart(2,'0')}:${mm.toString().padStart(2,'0')}`);
                } else {
                    console.warn("Clock data incomplete in response");
                    pushLog('Clock data incomplete in /state.');
                }

                // After fetching state, refresh NPC details if modal is open
                if (apiUrl && useSimStore.getState().isNPCDetailModalOpen) {
                    const selectedNPC = useSimStore.getState().selectedNPCDetails;
                    if (selectedNPC) {
                        // Refresh with a slight delay to allow database updates to complete
                        setTimeout(() => {
                            refreshNPCDetailModal(apiUrl);
                        }, 500);
                    }
                }
            } catch (error: any) {
                console.error('Error fetching state');
                pushLog(`Error fetching/processing state: ${error.message}`);
            }
        };

        return () => {
            if (socketRef.current) {
                socketRef.current.close(); 
                socketRef.current = null;
            }
        };
    }, [apiUrl, wsUrl, pushLog, setNPCs, setAreas, setClock, closeNPCDetailModal, refreshNPCDetailModal]);
};
