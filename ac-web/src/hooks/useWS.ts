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
    const { setNPCs, setAreas, setClock, pushLog } = useSimStore((state) => state.actions);
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
            console.log("CLIENT WS: Connection opened!");
            pushLog('Connected to simulation server.');
            fetchState("onOpen");
        };

        socket.onclose = (event) => {
            console.log("CLIENT WS: Connection closed.", event.code, event.reason);
            pushLog(`Disconnected: Code ${event.code}`);
        };

        socket.onerror = (event) => {
            console.error("CLIENT WS: Error observed.", event);
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
                        if (eventData.event_code === 'fire_alarm') emoji = "🔥";
                        if (eventData.event_code === 'pizza_drop') emoji = "🍕";
                        if (eventData.event_code === 'wifi_down') emoji = "📉";
                        pushLog(`${emoji} DAY ${eventData.day || '-'} EVENT: ${eventData.description}`);
                    }
                }
                else if (messageWrapper.type === 'planning_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    pushLog(`📋 PLAN D${eventData.day || '-'}: ${eventData.npc_name} ${eventData.status}${eventData.num_actions ? ' ('+eventData.num_actions+' actions)' : ''}.`);
                }
                else if (messageWrapper.type === 'reflection_event' && messageWrapper.data) {
                    const eventData = messageWrapper.data;
                    pushLog(`🤔 REFLECT D${eventData.day || '-'}: ${eventData.npc_name} ${eventData.status}.`);
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
                }
            } catch (e) {
                console.error('CLIENT WS: Error parsing/handling WebSocket message:', e);
                pushLog('Received malformed data from server.');
            }
        };

        const fetchState = async (context: string) => {
            if (!apiUrl) { console.error("CLIENT WS: fetchState - No API URL"); return; }
            try {
                const response = await fetch(`${apiUrl}/state`);
                if (!response.ok) throw new Error(`Fetch /state failed: ${response.status}`);
                const stateData = await response.json() as BackendState;

                if (stateData.npcs) setNPCs(stateData.npcs);
                if (stateData.areas) setAreas(stateData.areas);

                if (stateData.sim_clock && stateData.environment) {
                    const totalSimMinutesInDay = stateData.sim_clock.sim_min;
                    const currentDay = stateData.environment.day;
                    const d = dayjs.duration(totalSimMinutesInDay, 'minutes');
                    const hh = d.hours();
                    const mm = d.minutes();
                    setClock({ day: currentDay, hh, mm });
                    pushLog(`Tick: Day ${currentDay} - ${hh.toString().padStart(2,'0')}:${mm.toString().padStart(2,'0')}`);
                } else {
                    console.warn("CLIENT WS: fetchState - Clock data incomplete in /state response.");
                    pushLog('Clock data incomplete in /state.');
                }
            } catch (error: any) {
                console.error('CLIENT WS: Error in fetchState:', error);
                pushLog(`Error fetching/processing state: ${error.message}`);
            }
        };

        return () => {
            console.log("CLIENT WS: useEffect cleanup - Closing WebSocket.");
            if (socketRef.current) {
                socketRef.current.close(); 
                socketRef.current = null;
            }
        };
    }, [apiUrl, wsUrl, pushLog, setNPCs, setAreas, setClock]);
};
