import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { useSimStore, SimClock, DisplayNPC, DisplayArea } from '../store/simStore';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';

dayjs.extend(duration);

// Define expected structure from the /state endpoint
interface BackendState {
    npcs: DisplayNPC[];       // Assuming backend provides NPCs ready for display
    areas: DisplayArea[];     // Assuming backend provides Areas
    sim_clock: {              // Assuming backend provides sim_clock data
        sim_min: number;
        // day: number; // The clock also has a day, can come from here or environment table
    };
    environment: {
        day: number;
        // speed: number;
    }
    // Potentially other state parts like active events, etc.
}

export const useWS = () => {
    const { setNPCs, setAreas, setClock, pushLog } = useSimStore((state) => state.actions);
    const socketRef = useRef<Socket | null>(null);

    // Vite exposes env variables on import.meta.env
    const apiUrl = import.meta.env.VITE_API_URL;
    let wsUrl = '';
    if (apiUrl) {
        wsUrl = apiUrl.replace('http', 'ws') + '/ws';
    } else {
        console.error('VITE_API_URL is not defined! Check your .env file in the ac-web directory.');
    }

    useEffect(() => {
        if (!wsUrl) return; // Don't connect if wsUrl is not set

        const socket = io(wsUrl);
        socketRef.current = socket;

        socket.on('connect', () => {
            console.log('WebSocket connected:', socket.id);
            pushLog('Connected to simulation server.');
            fetchState();
        });

        socket.on('disconnect', (reason) => {
            console.log('WebSocket disconnected:', reason);
            pushLog('Disconnected from simulation server.');
        });

        socket.on('error', (error) => {
            console.error('WebSocket error:', error);
            pushLog(`WebSocket error: ${error.message || 'Unknown error'}`);
        });

        socket.on('message', (data) => {
            try {
                const message = typeof data === 'string' ? JSON.parse(data) : data;
                if (message.tick === 'update') {
                    fetchState();
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
                pushLog('Received malformed tick from server.');
            }
        });

        const fetchState = async () => {
            if (!apiUrl) return;
            try {
                const response = await fetch(`${apiUrl}/state`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch state: ${response.status} ${response.statusText}`);
                }
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
                    pushLog(`Tick processed: Day ${currentDay} - ${hh.toString().padStart(2,'0')}:${mm.toString().padStart(2,'0')}`);
                } else {
                    pushLog('Clock data incomplete in /state response.');
                }
            } catch (error: any) {
                console.error('Error fetching state:', error);
                pushLog(`Error fetching state: ${error.message}`);
            }
        };

        return () => {
            console.log('Cleaning up WebSocket connection.');
            if (socketRef.current) {
                socketRef.current.disconnect();
                socketRef.current = null;
            }
        };
    }, [apiUrl, wsUrl, pushLog, setNPCs, setAreas, setClock]);

    // Function to manually send messages if needed (not in playbook for this phase)
    // const sendMessage = (message: string) => {\n    //     if (socketRef.current) {\n    //         socketRef.current.send(message);\n    //     }\n    // };\n\n    // return { sendMessage }; // Expose if needed\n}; 
} 