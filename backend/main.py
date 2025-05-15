from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware # Import CORS middleware
from typing import List # Added for type hinting if needed, though not in playbook snippet

from .models import SeedPayload # Relative import
from .services import insert_npcs, get_state # Relative import
from . import scheduler # Relative import

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
    data = get_state() 
    return data # Return the list of NPCs directly

@app.post('/tick')
async def manual_tick():
    await scheduler.advance_tick()
    return {'status': 'ticked'}

@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    print("DEBUG: ws_endpoint - Connection attempt received.") # DEBUG
    await ws.accept()
    print(f"DEBUG: ws_endpoint - WebSocket accepted: {ws.client}") # DEBUG
    scheduler.register_ws(ws)
    try:
        while True:
            data = await ws.receive_text()
            print(f"DEBUG: ws_endpoint - Received text from client: {data}") # DEBUG
            # Server currently doesn't expect messages from client for this app
    except Exception as e:
        # This will catch WebSocketDisconnect, ConnectionClosed, etc.
        print(f"DEBUG: ws_endpoint - Exception/Disconnect: {type(e).__name__} - {e}") # DEBUG
    finally:
        print(f"DEBUG: ws_endpoint - Connection closing for: {ws.client}") # DEBUG
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

# Ensure scheduler loop is started when the app starts
@app.on_event("startup")
async def startup_event():
    scheduler.start_loop()
