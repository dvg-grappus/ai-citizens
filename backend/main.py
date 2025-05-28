from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware # Import CORS middleware
from typing import List, Optional # Added for type hinting if needed, though not in playbook snippet
import json
import subprocess
import os # To get project root
import logging # For configuring logging
from pydantic import BaseModel

# Configure logging - set FastAPI and uvicorn loggers to WARNING level to reduce verbosity
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL) # Higher level to silence completely

from .models import SeedPayload, NPCUIDetailData, DialogueTranscriptResponse # ADD DialogueTranscriptResponse
from .services import (
    insert_npcs, get_state, get_npc_ui_details,
    get_dialogue_transcript, # ADD THIS IMPORT
    supa, execute_supabase_query # Make sure these are available from services
)
from . import scheduler # For scheduler.start_loop()
from backend.websocket_utils import broadcast_ws_message # ADD THIS IMPORT

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

@app.get("/api/v1/dialogues/{dialogue_id}/transcript", response_model=DialogueTranscriptResponse)
async def get_full_dialogue_transcript(dialogue_id: str):
    """Endpoint to get the full transcript of a specific dialogue session."""
    transcript_turns = await get_dialogue_transcript(dialogue_id)
    if transcript_turns is None: # Check for None, which indicates an error in service layer
        raise HTTPException(status_code=500, detail=f"Error fetching transcript for dialogue ID {dialogue_id}")
    if not transcript_turns: # Empty list means dialogue found but no turns, or dialogue not found
        # Distinguish between dialogue not found vs dialogue with no turns based on service layer logic if needed
        # For now, if service returns empty list, assume it means no content to show.
        # To be more precise, get_dialogue_transcript could raise specific errors.
        pass # Allow returning empty list of turns if dialogue existed but had no turns processed for some reason

    return DialogueTranscriptResponse(dialogue_id=dialogue_id, turns=transcript_turns)

@app.post("/reset_simulation_to_end_of_day1") # Changed to POST as it modifies state
async def reset_sim_day1_end():
    print("Endpoint /reset_simulation_to_end_of_day1 called")
    try:
        day_to_set = 1
        sim_min_to_set = 1425 # 23:45 on Day 1 (next tick will be 23:59 if TICK_SIM_MIN=15, then rollover)
        
        # Use the execute_supabase_query from services
        await execute_supabase_query(lambda: supa.table('sim_clock').update({'sim_min': sim_min_to_set}).eq('id', 1).execute())
        await execute_supabase_query(lambda: supa.table('environment').update({'day': day_to_set}).eq('id', 1).execute())
        
        # Clear future plans for a clean test of next day's planning
        await execute_supabase_query(lambda: supa.table('plan').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute())
        
        # MODIFIED: Only delete queued and active actions, preserve completed (done) actions
        # This retains action history while still allowing new planning
        await execute_supabase_query(lambda: supa.table('action_instance')
            .delete()
            .in_('status', ['queued', 'active'])
            .execute())
        
        # Delete plan and reflection memories, but keep observations
        await execute_supabase_query(lambda: supa.table('memory').delete().in_('kind', ['reflect', 'plan']).execute())
        
        # Clear current_action_id for all NPCs to prevent stale references after reset
        await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).neq('id', '00000000-0000-0000-0000-000000000000').execute())
        
        # Log what we're preserving for clarity
        print(f"Simulation reset: Day set to {day_to_set}, SimMin set to {sim_min_to_set}")
        print("Note: Completed actions (status='done') are preserved for history")
        
        # Optional: Force an immediate state broadcast
        await broadcast_ws_message("tick_update", {'new_sim_min': sim_min_to_set, 'new_day': day_to_set})

        return {"status": "success", "message": f"Simulation time reset to Day {day_to_set}, 23:45. Completed actions are preserved for history."}
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

class UserEventRequest(BaseModel):
    message: str
    enhance: bool = True
    # Add event_type as an optional field to the request model for future use if desired
    # event_type: Optional[str] = "custom" 

@app.post("/trigger_user_event")
async def trigger_user_event(request: UserEventRequest):
    """
    Create a simulation event from user-provided text.
    The request should contain a 'message' field with the user's text.
    Optionally, it can also include an 'enhance' boolean flag to use OpenAI to format the message.
    """
    user_message = request.message
    enhance_with_ai = request.enhance
    
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    try:
        # Get current simulation state for context
        time_data = await scheduler.get_current_sim_time_and_day()
        current_day = time_data["day"]
        current_sim_minutes_total = ((current_day - 1) * scheduler.SIM_DAY_MINUTES) + time_data["sim_min"]
        
        # Process the message with OpenAI if requested
        final_message = user_message
        if enhance_with_ai:
            from .llm import call_llm
            system_prompt = """You are a creative AI assistant helping to enhance user messages into vivid environmental events for a simulation.
Transform the user's message into a concise, engaging environmental announcement.
Keep it under 80 characters. Focus on what's happening rather than who caused it.
Add appropriate emoji if relevant."""
            user_prompt = f"Transform this message into a vivid environmental event: {user_message}"
            enhanced_message = call_llm(system_prompt, user_prompt, max_tokens=100)
            if enhanced_message:
                final_message = enhanced_message.strip()
        
        # Create a custom event code and metadata
        event_code = "user_event"
        event_duration = 30  # Default duration in minutes
        
        # Insert into sim_event table
        sim_event_payload = {
            'type': event_code,
            'start_min': current_sim_minutes_total,
            'end_min': current_sim_minutes_total + event_duration,
            'metadata': {
                'original_message': user_message,
                'enhanced': enhance_with_ai
            }
        }
        
        event_response = await execute_supabase_query(lambda: supa.table('sim_event').insert(sim_event_payload).execute())
        
        event_id = None
        if event_response and event_response.data and len(event_response.data) > 0:
            event_id = event_response.data[0].get('id')
            
            # Broadcast via WebSocket
            ws_event_data = {
                'event_code': event_code,
                'description': final_message,
                'tick': current_sim_minutes_total,
                'event_id': event_id,
                'day': current_day,
                'user_generated': True
            }
            await scheduler.broadcast_ws_message("sim_event", ws_event_data)
            
            # Create observations for NPCs
            # Create a simplified event object similar to the challenges used in scheduler
            event_data = {
                'code': event_code,
                'label': 'User Event',
                'effect_desc': final_message,
                'metadata': {}  # No area restriction for user events, all NPCs should observe
            }
            
            # Create observations for all NPCs
            from .memory_service import get_embedding
            # Get all NPCs
            npcs_res = await execute_supabase_query(lambda: supa.table('npc').select('id').execute())
            affected_npcs = []
            if npcs_res and npcs_res.data:
                for npc in npcs_res.data:
                    npc_id = npc.get('id')
                    if npc_id:
                        observation_content = f"[Environment] I noticed: {final_message}"
                        observation_embedding = await get_embedding(observation_content)
                        if observation_embedding:
                            mem_payload = {
                                'npc_id': npc_id,
                                'sim_min': current_sim_minutes_total,
                                'kind': 'obs',
                                'content': observation_content,
                                'importance': 3,
                                'embedding': observation_embedding
                            }
                            await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload).execute())
                            affected_npcs.append(npc_id)

            from .planning_and_reflection import run_replanning
            for npc_id in affected_npcs:
                event_info = {
                    "source": "user_event",
                    # Since UserEventRequest doesn't have event_type, we provide a default.
                    # The run_replanning function will default to "custom" if this is missing,
                    # but being explicit here is also fine.
                    "user_event_type": "general_user_event", 
                    "original_description": final_message 
                }
                await run_replanning(npc_id, event_info, current_sim_minutes_total)
            
            return {
                "status": "success",
                "event_id": event_id,
                "message": final_message,
                "day": current_day,
                "sim_min": time_data["sim_min"]
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create event")
    except Exception as e:
        print(f"Error processing user event: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing event: {str(e)}")

class SpeedPayload(BaseModel):
    speed: int  # 1 for normal speed, 2 for double speed, etc.
    
@app.post('/set_speed')
async def set_simulation_speed(payload: SpeedPayload):
    """Set the simulation speed (1 = normal, 2 = 2x, etc.)"""
    from .config import get_settings
    
    settings = get_settings()
    
    # Base tick is 15 minutes of simulation time
    # Instead of changing the real-time interval, modify how much simulation time passes per tick
    base_sim_min = 15  # Default simulation minutes per tick
    
    if payload.speed == 1:
        # Normal speed - 15 minutes per tick
        new_sim_min = 15
    elif payload.speed == 2:
        # 2x speed - 30 minutes per tick
        new_sim_min = 30
    elif payload.speed == 4:
        # 4x speed - 60 minutes (1 hour) per tick
        new_sim_min = 60
    else:
        # Default to normal speed
        new_sim_min = 15
    
    # Update the scheduler's tick simulation minutes
    settings.TICK_SIM_MIN = new_sim_min
    
    return {
        'status': 'speed_updated', 
        'speed': payload.speed, 
        'tick_sim_min': new_sim_min,
        'description': f"Each tick now advances {new_sim_min} simulation minutes"
    }

# Ensure scheduler loop is started when the app starts
@app.on_event("startup")
async def startup_event():
    scheduler.start_loop()

@app.get('/debug_memory_types/{npc_id}')
async def debug_memory_types(npc_id: str):
    """Debugging endpoint to check if reflect and plan memories exist in the database."""
    try:
        # Check for reflect memories
        reflect_res = await execute_supabase_query(lambda: supa.table('memory')
            .select('id, sim_min')
            .eq('npc_id', npc_id)
            .eq('kind', 'reflect')
            .order('sim_min', desc=True)
            .limit(10)
            .execute())
            
        # Check for plan memories
        plan_res = await execute_supabase_query(lambda: supa.table('memory')
            .select('id, sim_min')
            .eq('npc_id', npc_id)
            .eq('kind', 'plan')
            .order('sim_min', desc=True)
            .limit(10)
            .execute())
            
        # Check for observation memories for comparison
        obs_res = await execute_supabase_query(lambda: supa.table('memory')
            .select('id, sim_min')
            .eq('npc_id', npc_id)
            .eq('kind', 'obs')
            .order('sim_min', desc=True)
            .limit(10)
            .execute())
            
        # Get the NPC's name for reference
        npc_res = await execute_supabase_query(lambda: supa.table('npc')
            .select('name')
            .eq('id', npc_id)
            .maybe_single()
            .execute())
            
        npc_name = npc_res.data.get('name', 'Unknown') if npc_res and npc_res.data else 'Unknown'
            
        return {
            'npc_id': npc_id,
            'npc_name': npc_name,
            'reflect_count': len(reflect_res.data) if reflect_res and reflect_res.data else 0,
            'plan_count': len(plan_res.data) if plan_res and plan_res.data else 0,
            'obs_count': len(obs_res.data) if obs_res and obs_res.data else 0,
            'reflect_memories': reflect_res.data if reflect_res and reflect_res.data else [],
            'plan_memories': plan_res.data if plan_res and plan_res.data else [],
            'has_obs': bool(obs_res and obs_res.data),
            'has_reflect': bool(reflect_res and reflect_res.data),
            'has_plan': bool(plan_res and plan_res.data)
        }
    except Exception as e:
        print(f"Error in debug_memory_types: {e}")
        import traceback; traceback.print_exc()
        return {"error": str(e)}
