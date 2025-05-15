print("DEBUG_IMPORT: Starting main.py") # DEBUG
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware # Import CORS middleware
from typing import List, Optional # Added for type hinting if needed, though not in playbook snippet
import json
import subprocess
import os # To get project root
import logging # For configuring logging

# Configure logging - set FastAPI and uvicorn loggers to WARNING level to reduce verbosity
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL) # Higher level to silence completely

print("DEBUG_IMPORT: main.py - About to import from .models, .services, .scheduler") # DEBUG
try:
    from .models import SeedPayload, NPCUIDetailData # Relative import
    from .services import (
        insert_npcs, get_state, get_npc_ui_details,
        supa, execute_supabase_query # Make sure these are available from services
    )
    from . import scheduler # For scheduler.start_loop()
    # from . import scheduler # Keep if scheduler itself is needed, but not for execute_supabase_query
    print("DEBUG_IMPORT: main.py - Successfully imported from .models, .services, .scheduler") # DEBUG
except ImportError as e:
    print(f"DEBUG_IMPORT: main.py - IMPORT ERROR: {e}") # DEBUG
    raise

app = FastAPI(title='Artificial Citizens API')

# Add CORS middleware
origins = [
    "http://localhost:5173", # Default Vite port
    "http://localhost:5174", # In case Vite uses this one
    "http://localhost:5175", # Add a few more common Vite ports
    # Add any other origins your frontend might run on
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

@app.post('/seed')
async def seed(payload: SeedPayload):
    # Pydantic V2 .model_dump() instead of .dict()
    # For now, sticking to playbook .dict(), but this might need to change
    npcs_to_insert = [npc.dict() for npc in payload.npcs]
    insert_npcs(npcs_to_insert)
    return {'status': 'seeded', 'count': len(payload.npcs)}

@app.get('/state')
async def state():
    # The playbook does get_state().data, implying get_state() returns an object with a .data attribute
    # My services.get_state() returns the data list directly or an empty list on error.
    # Adjusting to match my services.get_state() return type.
    data = await get_state()
    return data # Return the list of NPCs directly

@app.post('/tick')
async def manual_tick():
    await scheduler.advance_tick()
    return {'status': 'ticked'}

@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    # Connection setup - no logging
    await ws.accept()
    scheduler.register_ws(ws)
    try:
        while True:
            # Wait for messages (not expected in this app but handling anyway)
            await ws.receive_text()
    except Exception as e:
        # Only log critical WebSocket errors
        if not isinstance(e, (WebSocketDisconnect := type('WebSocketDisconnect', (), {}), ConnectionClosed := type('ConnectionClosed', (), {}))):
            print(f"CRITICAL WebSocket error: {type(e).__name__} - {e}")
    finally:
        scheduler.unregister_ws(ws)

@app.get("/test_planning")
async def test_planning_endpoint():
    print("TEST ENDPOINT: /test_planning called")
    # We need current sim time and day. Let's fetch it.
    # Or for a test, we can use a fixed value, e.g., start of Day 2.
    current_time_data = await scheduler.get_current_sim_time_and_day()
    day_to_plan_for = current_time_data.get('day', 1) # Plan for current day
    sim_time_for_planning_memory = current_time_data.get('sim_min', 0) # Time of planning
    
    # If we want to force planning for next day, we can adjust:
    # day_to_plan_for = current_time_data.get('day', 1) + 1
    # sim_time_for_planning_memory = 0 # Assuming planning happens at midnight

    print(f"Triggering run_daily_planning for Day {day_to_plan_for} at sim_min {sim_time_for_planning_memory}")
    await scheduler.run_daily_planning(day_to_plan_for, sim_time_for_planning_memory)
    return {"status": "daily planning test triggered", "day": day_to_plan_for}

@app.get("/test_reflection")
async def test_reflection_endpoint():
    print("TEST ENDPOINT: /test_reflection called")
    # Reflect on the current day, using current time as effective end-of-day for memory retrieval context
    current_time_data = await scheduler.get_current_sim_time_and_day()
    day_to_reflect_on = current_time_data.get('day', 1)
    sim_time_for_reflection_context = current_time_data.get('sim_min', 1439) # Use current time as context

    print(f"Triggering run_nightly_reflection for Day {day_to_reflect_on} using context time {sim_time_for_reflection_context}")
    await scheduler.run_nightly_reflection(day_to_reflect_on, sim_time_for_reflection_context)
    return {"status": "nightly reflection test triggered", "day": day_to_reflect_on}

@app.get('/npc_details/{npc_id}')
async def get_npc_details(npc_id: str):
    """Endpoint to get extended details about a specific NPC."""
    # Need to get the current day as a context for the details
    environment_res = await execute_supabase_query(lambda: supa.table('environment').select('day').eq('id', 1).maybe_single().execute())
    environment_data = environment_res.data if environment_res else None
    current_day = environment_data.get('day', 1) if environment_data else 1
    
    # Fetch extended details for the NPC
    npc_details = await get_npc_ui_details(npc_id, current_day)
    if not npc_details:
        raise HTTPException(status_code=404, detail=f"NPC with ID {npc_id} not found or details unavailable")
    return npc_details

@app.post("/reset_simulation_to_end_of_day1") # Changed to POST as it modifies state
async def reset_sim_day1_end():
    print("Endpoint /reset_simulation_to_end_of_day1 called")
    try:
        day_to_set = 1
        sim_min_to_set = 1425 # 23:45 on Day 1 (next tick will be 23:59 if TICK_SIM_MIN=15, then rollover)
        
        # Use the execute_supabase_query from services
        await execute_supabase_query(lambda: supa.table('sim_clock').update({'sim_min': sim_min_to_set}).eq('id', 1).execute())
        await execute_supabase_query(lambda: supa.table('environment').update({'day': day_to_set}).eq('id', 1).execute())
        
        # Clear future plans and non-observation memories for a clean test of next day's planning/reflection
        await execute_supabase_query(lambda: supa.table('plan').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute())
        await execute_supabase_query(lambda: supa.table('action_instance').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute())
        await execute_supabase_query(lambda: supa.table('memory').delete().in_('kind', ['reflect', 'plan']).execute())
        # Optionally clear dialogue, sim_event, encounter tables too if a full reset is desired

        print(f"Simulation reset: Day set to {day_to_set}, SimMin set to {sim_min_to_set}")
        # Optional: Force an immediate state broadcast or rely on next tick
        if scheduler._ws_clients: # Accessing scheduler's client list
             payload = {"type": "tick_update", "data": {'new_sim_min': sim_min_to_set, 'new_day': day_to_set}}
             for ws in scheduler._ws_clients:
                try: await ws.send_text(json.dumps(payload))
                except: pass # Ignore send error on reset

        return {"status": "success", "message": f"Simulation time reset to Day {day_to_set}, 23:45. Planning/reflection will trigger soon."}
    except Exception as e:
        print(f"Error in /reset_simulation_to_end_of_day1: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_seed_script")
async def trigger_seed_script():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) # Get project root from backend/main.py location
    seed_script_path = os.path.join(project_root, "ac-web", "scripts", "seed.ts")
    dotenv_path = os.path.join(project_root, "ac-web", ".env") # For -r dotenv/config
    # Command to execute. Ensure node, ts-node are in PATH or use absolute paths.
    # Using npx for ts-node is often more portable if ts-node isn't globally installed in the right context for the backend.
    # command = ["node", "--loader", "ts-node/esm", "-r", "dotenv/config", seed_script_path]
    # Simpler: use npx ts-node directly if pnpm set it up in node_modules/.bin for ac-web, or if ts-node is global for the user.
    # Let's try with npx which often works well.
    # The -r dotenv/config needs to resolve .env relative to where the script is run or where dotenv is told to look.
    # Running from project_root, so dotenv/config should pick up ac-web/.env if we cd into ac-web first.
    
    command_to_run = f"cd {os.path.join(project_root, 'ac-web')} && npx ts-node -r dotenv/config scripts/seed.ts"
    
    print(f"Attempting to run seed script with command: {command_to_run}")
    try:
        # Using shell=True can be a security risk if command components are from untrusted input, but here it's fixed.
        # It helps with complex commands like cd && ...
        process = subprocess.Popen(command_to_run, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=project_root)
        stdout, stderr = process.communicate(timeout=60) # Add a timeout
        
        if process.returncode == 0:
            print("Seed script executed successfully.")
            print("Stdout:\n", stdout)
            return {"status": "success", "message": "Seed script executed.", "output": stdout}
        else:
            print(f"Seed script failed. Return code: {process.returncode}")
            print("Stderr:\n", stderr)
            print("Stdout:\n", stdout)
            raise HTTPException(status_code=500, detail=f"Seed script execution failed: {stderr} {stdout}")

    except subprocess.TimeoutExpired:
        print("Seed script timed out.")
        raise HTTPException(status_code=500, detail="Seed script execution timed out.")
    except Exception as e:
        print(f"Error running seed script: {e}")
        raise HTTPException(status_code=500, detail=f"Error running seed script: {str(e)}")

# Ensure scheduler loop is started when the app starts
@app.on_event("startup")
async def startup_event():
    scheduler.start_loop()
