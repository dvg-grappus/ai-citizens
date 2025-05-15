import { createClient } from '@supabase/supabase-js';

// Ensure that SUPABASE_URL and SUPABASE_SERVICE_KEY are available in the environment
// when this script is run. For example, by loading them from the .env file.
// The playbook implies these will be available via process.env,
// which ts-node can handle if a .env loader is used or if they are globally set.
// For simplicity and directness, as this script will be run by the user,
// we'll assume they are loaded by the execution environment (e.g. ts-node-dev with --require dotenv/config)
// or that the user will ensure they are present.

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error("Supabase URL or Service Key is not defined. Make sure .env file is loaded or variables are set.");
}

const supabase = createClient(supabaseUrl, supabaseServiceKey);

async function main() {
    console.log("Starting to seed data...");

    // Insert Areas
    console.log("Inserting areas...");
    const { data: areas, error: areaError } = await supabase.from('area').insert([
        { name: 'Bedroom', bounds: { x: 0, y: 0, w: 200, h: 200 } },
        { name: 'Office', bounds: { x: 210, y: 0, w: 200, h: 200 } },
        { name: 'Bathroom', bounds: { x: 0, y: 210, w: 200, h: 200 } },
        { name: 'Lounge', bounds: { x: 210, y: 210, w: 200, h: 200 } }
    ]).select();

    if (areaError) {
        console.error('Error inserting areas:', areaError);
        return;
    }
    if (!areas || areas.length === 0) {
        console.error('No areas were inserted or returned. Please check your Supabase setup and permissions.');
        return;
    }
    console.log(`Inserted ${areas.length} areas successfully.`);

    // Helper getId
    const id = (name: string): string | undefined => {
        const foundArea = areas?.find(a => a.name === name);
        if (!foundArea) {
            console.warn(`Area with name "${name}" not found after insert.`);
        }
        return foundArea?.id;
    };

    const bedroomId = id('Bedroom');
    const officeId = id('Office');
    const bathroomId = id('Bathroom');
    // const loungeId = id('Lounge'); // Not used in playbook's object seeding

    if (!bedroomId || !officeId || !bathroomId) {
        console.error("One or more area IDs could not be retrieved. Aborting object/NPC seed.");
        return;
    }

    // Insert Objects
    console.log("Inserting objects...");
    const { error: objectError } = await supabase.from('object').insert([
        { area_id: bedroomId, name: 'Bed', state: 'free', pos: { x: 50, y: 50 } },
        { area_id: bathroomId, name: 'Toothbrush', state: 'free', pos: { x: 30, y: 60 } }
    ]);
    if (objectError) {
        console.error('Error inserting objects:', objectError);
        return;
    }
    console.log("Inserted objects successfully.");


    // Insert ActionDefs
    console.log("Inserting action definitions...");
    const { error: actionDefError } = await supabase.from('action_def').insert([
        { title: 'Sleep', emoji: '💤', base_minutes: 480 },
        { title: 'Brush Teeth', emoji: '🪥', base_minutes: 5 },
        { title: 'Work', emoji: '💻', base_minutes: 480 }
    ]);
    if (actionDefError) {
        console.error('Error inserting action definitions:', actionDefError);
        return;
    }
    console.log("Inserted action definitions successfully.");

    // Insert two sample NPCs
    console.log("Inserting NPCs...");
    const { error: npcError } = await supabase.from('npc').insert([
        { name: 'Alice', traits: ['friendly', 'curious'], backstory: 'Likes coffee.', relationships: {}, spawn: { x: 20, y: 20, areaId: bedroomId } },
        { name: 'Bob', traits: ['lazy', 'grumpy'], backstory: 'Hates Mondays.', relationships: {}, spawn: { x: 240, y: 30, areaId: officeId } }
    ]);

    if (npcError) {
        console.error('Error inserting NPCs:', npcError);
        return;
    }
    console.log("Inserted NPCs successfully.");
    console.log("Seeding complete!");
}

main().catch(e => console.error(e)); 