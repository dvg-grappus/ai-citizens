import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error("Supabase URL or Service Key is not defined in .env. Make sure .env file is in ac-web directory and loaded, or variables are globally set.");
}

const supabase = createClient(supabaseUrl, supabaseServiceKey);

async function main() {
    console.log("Starting to seed data (v2 with PC and Idle action)...");

    // Delete existing data to avoid conflicts if re-running
    console.log("Deleting existing data from tables...");
    await supabase.from('plan').delete().neq('id', '00000000-0000-0000-0000-000000000000'); // Non-existent ID to delete all
    await supabase.from('action_instance').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    await supabase.from('memory').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    // Be careful with deleting npcs, objects, areas if you have custom ones you want to keep
    // For a clean test, we often want to reset these.
    await supabase.from('npc').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    await supabase.from('object').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    await supabase.from('action_def').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    await supabase.from('area').delete().neq('id', '00000000-0000-0000-0000-000000000000');
    console.log("Finished deleting old data.");

    // Insert Areas
    console.log("Inserting areas...");
    const { data: areas, error: areaError } = await supabase.from('area').insert([
        { name: 'Bedroom', bounds: { x: 0, y: 0, w: 200, h: 200 } },
        { name: 'Office', bounds: { x: 210, y: 0, w: 200, h: 200 } },
        { name: 'Bathroom', bounds: { x: 0, y: 210, w: 200, h: 200 } },
        { name: 'Lounge', bounds: { x: 210, y: 210, w: 200, h: 200 } }
    ]).select();
    if (areaError) { console.error('Error inserting areas:', areaError); return; }
    if (!areas || areas.length === 0) { console.error('No areas inserted.'); return; }
    console.log(`Inserted ${areas.length} areas.`);

    const getAreaId = (name: string): string => areas.find(a => a.name === name)!.id;
    const bedroomId = getAreaId('Bedroom');
    const officeId = getAreaId('Office');
    const bathroomId = getAreaId('Bathroom');
    // const loungeId = getAreaId('Lounge');

    // Insert Objects
    console.log("Inserting objects...");
    const { data: objects, error: objectError } = await supabase.from('object').insert([
        { area_id: bedroomId, name: 'Bed', state: 'free', pos: { x: 50, y: 50 } },
        { area_id: bathroomId, name: 'Toothbrush', state: 'free', pos: { x: 30, y: 350 } },
        { area_id: officeId, name: 'PC', state: 'free', pos: { x: 450, y: 50 } }
    ]).select('id, name');
    if (objectError) { console.error('Error inserting objects:', objectError); return; }
    console.log(`Inserted ${objects?.length || 0} objects.`);
    // Store object IDs if needed for linking in action_instance creation logic
    // const bedId = objects?.find(o => o.name === 'Bed')?.id;
    // const pcId = objects?.find(o => o.name === 'PC')?.id;
    // const toothbrushId = objects?.find(o => o.name === 'Toothbrush')?.id;

    // Insert ActionDefs (includes previous ones + new ones from Phase 4/5 + Idle)
    console.log("Inserting action definitions...");
    const actionDefPayloads = [
        { title: 'Sleep', emoji: '💤', base_minutes: 480 },
        { title: 'Brush Teeth', emoji: '🪥', base_minutes: 5 },
        { title: 'Work', emoji: '💻', base_minutes: 120 }, // Was 240, shortened for testing variety
        { title: 'Eat', emoji: '🍔', base_minutes: 30 },
        { title: 'Walk', emoji: '🚶', base_minutes: 60 },
        { title: 'Chat', emoji: '💬', base_minutes: 30 },
        { title: 'Relax', emoji: '😌', base_minutes: 60 },
        { title: 'Read', emoji: '📚', base_minutes: 60 },
        { title: 'Nap', emoji: '😴', base_minutes: 90 },
        { title: 'Explore', emoji: '🗺️', base_minutes: 120 },
        { title: 'Evacuate', emoji: '🏃', base_minutes: 15 },         // Note: changed emoji from playbook to one more likely to render
        { title: 'Get Pizza', emoji: '🍕', base_minutes: 20 },
        { title: 'Complain about Wi-Fi', emoji: '😠', base_minutes: 10 },
        { title: 'Idle', emoji: '🧍', base_minutes: 15 } // New Idle action
    ];
    const { error: actionDefError } = await supabase.from('action_def').insert(actionDefPayloads);
    if (actionDefError) { console.error('Error inserting action definitions:', actionDefError); return; }
    console.log(`Inserted ${actionDefPayloads.length} action definitions.`);

    // Insert two sample NPCs
    console.log("Inserting NPCs...");
    const { error: npcError } = await supabase.from('npc').insert([
        { name: 'Alice', traits: ['friendly', 'curious'], backstory: 'Likes coffee.', relationships: {}, spawn: { x: 20, y: 20, areaId: bedroomId } },
        { name: 'Bob', traits: ['lazy', 'grumpy'], backstory: 'Hates Mondays.', relationships: {}, spawn: { x: 240, y: 30, areaId: officeId } }
    ]);
    if (npcError) { console.error('Error inserting NPCs:', npcError); return; }
    console.log("Inserted NPCs successfully.");

    console.log("Seeding complete (v2)!");
}

main().catch(e => console.error("Error in main seeding function:", e)); 