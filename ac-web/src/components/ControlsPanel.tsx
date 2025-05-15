import React, { useState } from 'react';
import { useSimStore } from '../store/simStore';
import { createClient } from '@supabase/supabase-js';
import type { Database } from '../types/supabase';

const ControlsPanel: React.FC = () => {
    const [isPaused, setIsPaused] = useState(false);
    const apiUrl = import.meta.env.VITE_API_URL;
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
    const { pushLog } = useSimStore(state => state.actions);

    const handlePauseToggle = async () => {
        // This would need backend support for pause/resume 
        setIsPaused(!isPaused);
        console.log(`Simulation ${!isPaused ? 'paused' : 'resumed'}`);
    };

    const handleManualTick = async () => {
        if (!apiUrl) { console.error('API URL not defined for manual tick'); return; }
        console.log("Sending manual tick...");
        try {
            const response = await fetch(`${apiUrl}/tick`, { method: 'POST' });
            if (!response.ok) {
                throw new Error(`Failed to send manual tick: ${response.status}`);
            }
            console.log("Manual tick sent.");
        } catch (error) {
            console.error('Error sending manual tick:', error);
        }
    };

    const handleSetSpeed = async (speed: number) => {
        console.log(`Setting simulation speed to x${speed}`);
        // This would need backend support for speed changes
    };

    const handleResetDay1End = async () => {
        if (!apiUrl) { console.error('API URL not defined for day reset'); return; }
        console.log("Resetting to end of Day 1...");
        try {
            const response = await fetch(`${apiUrl}/reset_simulation_to_end_of_day1`, { method: 'POST' });
            if (!response.ok) {
                throw new Error(`Failed to reset: ${response.status}`);
            }
            console.log("Reset to end of Day 1 successful.");
        } catch (error) {
            console.error('Error in day reset:', error);
        }
    };

    const handleDirectReseedDatabase = async () => {
        // Check for required Supabase credentials
        if (!supabaseUrl || !supabaseKey) {
            const errorMsg = "Supabase URL or Key is not defined in environment variables.";
            console.error(errorMsg);
            pushLog(`🚫 Error: ${errorMsg}`);
            alert(errorMsg);
            return;
        }

        pushLog("🔄 Starting direct database re-seed...");
        console.log("Starting direct database re-seed...");

        try {
            // Create Supabase client
            const supabase = createClient<Database>(supabaseUrl, supabaseKey);
            
            // Delete existing data
            pushLog("Cleaning existing data...");
            await supabase.from('plan').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('action_instance').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('memory').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('dialogue_turn').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('dialogue').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('sim_event').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('npc').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('object').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('action_def').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            await supabase.from('area').delete().neq('id', '00000000-0000-0000-0000-000000000000');
            pushLog("✅ Existing data cleared.");
            
            // Insert Areas
            pushLog("Inserting areas...");
            const { data: areas, error: areaError } = await supabase.from('area').insert([
                { name: 'Bedroom', bounds: { x: 0, y: 0, w: 200, h: 200 } },
                { name: 'Office', bounds: { x: 210, y: 0, w: 200, h: 200 } },
                { name: 'Bathroom', bounds: { x: 0, y: 210, w: 200, h: 200 } },
                { name: 'Lounge', bounds: { x: 210, y: 210, w: 200, h: 200 } }
            ]).select();
            
            if (areaError) throw new Error(`Error inserting areas: ${areaError.message}`);
            if (!areas || areas.length === 0) throw new Error('No areas inserted.');
            
            // Get Area IDs
            const getAreaId = (name: string): string => {
                const area = areas.find(a => a.name === name);
                if (!area) throw new Error(`Area ${name} not found after insertion`);
                return area.id;
            };
            
            const bedroomId = getAreaId('Bedroom');
            const officeId = getAreaId('Office');
            const bathroomId = getAreaId('Bathroom');
            const loungeId = getAreaId('Lounge');
            
            // Insert Objects
            pushLog("Inserting objects...");
            const { error: objectError } = await supabase.from('object').insert([
                { area_id: bedroomId, name: 'Bed', state: 'free', pos: { x: 50, y: 50 } },
                { area_id: bathroomId, name: 'Toothbrush', state: 'free', pos: { x: 30, y: 350 } },
                { area_id: officeId, name: 'PC', state: 'free', pos: { x: 450, y: 50 } }
            ]);
            
            if (objectError) throw new Error(`Error inserting objects: ${objectError.message}`);
            
            // Insert Action Definitions
            pushLog("Inserting action definitions...");
            const actionDefPayloads = [
                { title: 'Sleep', emoji: '💤', base_minutes: 480 },
                { title: 'Brush Teeth', emoji: '🪥', base_minutes: 5 },
                { title: 'Work', emoji: '💻', base_minutes: 120 },
                { title: 'Eat', emoji: '🍔', base_minutes: 30 },
                { title: 'Walk', emoji: '🚶', base_minutes: 60 },
                { title: 'Chat', emoji: '💬', base_minutes: 30 },
                { title: 'Relax', emoji: '😌', base_minutes: 60 },
                { title: 'Read', emoji: '📚', base_minutes: 60 },
                { title: 'Nap', emoji: '😴', base_minutes: 90 },
                { title: 'Explore', emoji: '🗺️', base_minutes: 120 },
                { title: 'Evacuate', emoji: '🏃', base_minutes: 15 },
                { title: 'Get Pizza', emoji: '🍕', base_minutes: 20 },
                { title: 'Complain about Wi-Fi', emoji: '😠', base_minutes: 10 },
                { title: 'Idle', emoji: '🧍', base_minutes: 15 }
            ];
            
            const { error: actionDefError } = await supabase.from('action_def').insert(actionDefPayloads);
            if (actionDefError) throw new Error(`Error inserting action definitions: ${actionDefError.message}`);
            
            // Insert NPCs
            pushLog("Inserting NPCs...");
            const { error: npcError } = await supabase.from('npc').insert([
                { 
                    name: 'Alice', 
                    traits: ['friendly', 'curious'], 
                    backstory: 'Likes coffee.', 
                    relationships: {}, 
                    spawn: { x: 20, y: 20, areaId: bedroomId } 
                },
                { 
                    name: 'Bob', 
                    traits: ['lazy', 'grumpy'], 
                    backstory: 'Hates Mondays.', 
                    relationships: {}, 
                    spawn: { x: 240, y: 30, areaId: officeId } 
                }
            ]);
            
            if (npcError) throw new Error(`Error inserting NPCs: ${npcError.message}`);
            
            // Reset sim_clock to beginning
            pushLog("Resetting simulation clock...");
            const { error: clockError } = await supabase
                .from('sim_clock')
                .update({ sim_min: 0 })
                .eq('id', 1);
                
            if (clockError) throw new Error(`Error resetting clock: ${clockError.message}`);
            
            // Reset environment day
            const { error: envError } = await supabase
                .from('environment')
                .update({ day: 1 })
                .eq('id', 1);
                
            if (envError) throw new Error(`Error resetting environment: ${envError.message}`);
            
            pushLog("✅ Database re-seed completed successfully!");
            alert("Database re-seeded successfully! Please refresh the page to see changes.");
            
        } catch (error: any) {
            const errorMsg = `Error re-seeding database: ${error.message || error}`;
            console.error(errorMsg);
            pushLog(`❌ ${errorMsg}`);
            alert(errorMsg);
        }
    };

    const handleReseedDatabase = async () => {
        if (!apiUrl) { console.error('API URL not defined for reseed'); return; }
        console.log("Attempting to re-seed database...");
        // Optionally, add a confirmation dialog here for the user
        // if (!confirm("Are you sure you want to re-seed the database? This will delete existing data.")) return;
        
        try {
            // It's good to push a log to the store here so user sees it in the UI log panel
            // useSimStore.getState().actions.pushLog("🔄 Attempting to re-seed database...");
            const response = await fetch(`${apiUrl}/run_seed_script`, { method: 'POST' });
            const resultText = await response.text(); // Get text first for better error display
            if (!response.ok) {
                throw new Error(`Failed to re-seed database: ${response.status} - ${resultText}`);
            }
            const result = JSON.parse(resultText); // Now try to parse JSON
            console.log("Database re-seed response:", result);
            // useSimStore.getState().actions.pushLog(result.message || "Database re-seeded!");
            // useSimStore.getState().actions.pushLog("Please REFRESH your browser to see changes if NPCs/Areas were redefined.");
            alert(result.message || "Database re-seeded successfully! Consider refreshing the page."); // Simple alert for now
        } catch (error) {
            console.error('Error re-seeding database:', error);
            // useSimStore.getState().actions.pushLog(`Error re-seeding: ${error}`);
            alert(`Error re-seeding database: ${error}`);
        }
    };

    const styles: React.CSSProperties = {
        position: 'fixed',
        top: '8px',
        left: '8px',
        backgroundColor: 'rgba(50,50,50,0.8)',
        padding: '5px',
        borderRadius: '3px',
        zIndex: 1000,
        display: 'flex',
        gap: '5px'
    };

    const buttonStyles: React.CSSProperties = {
        padding: '3px 6px',
        fontSize: '10px',
        cursor: 'pointer'
    };

    return (
        <div style={styles}>
            <button style={buttonStyles} onClick={handlePauseToggle}>
                {isPaused ? 'Resume' : 'Pause'}
            </button>
            <button style={buttonStyles} onClick={handleManualTick} disabled={!isPaused}>
                Step Tick
            </button>
            <button style={buttonStyles} onClick={() => handleSetSpeed(1)}>
                x1 Speed
            </button>
            <button style={buttonStyles} onClick={() => handleSetSpeed(2)}>
                x2 Speed
            </button>
            <button style={buttonStyles} onClick={handleResetDay1End}>
                Test Day Rollover
            </button>
            <button style={{...buttonStyles, backgroundColor: '#c0392b', color: 'white'}} onClick={handleDirectReseedDatabase}>
                Re-Seed DB
            </button>
        </div>
    );
};

export default ControlsPanel;
