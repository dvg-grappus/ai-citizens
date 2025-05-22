import asyncio
import json
from typing import List, Any, Dict, Set, Optional # Added Set and Optional
import re # For parsing plan
from datetime import date # For sim_date
import math # Already there, but good to note for sqrt
import random # For dialogue initiation chance
from postgrest.exceptions import APIError # Import APIError

# Use relative imports for consistency and to avoid issues if backend is run as a module
from .config import get_settings
from .llm import call_llm
from .prompts import (
    PLAN_SYSTEM_PROMPT_TEMPLATE, PLAN_USER_PROMPT_TEMPLATE, 
    REFLECTION_SYSTEM_PROMPT_TEMPLATE, REFLECTION_USER_PROMPT_TEMPLATE, 
    DIALOGUE_SYSTEM_PROMPT_TEMPLATE, DIALOGUE_USER_PROMPT_TEMPLATE, format_traits
)
from .memory_service import retrieve_memories, get_embedding
from .services import supa, execute_supabase_query, get_area_details
from .websocket_utils import register_ws, unregister_ws, broadcast_ws_message
from .planning_and_reflection import run_daily_planning, run_nightly_reflection
from .dialogue_service import (
    process_pending_dialogues as process_dialogues_ext, 
    add_pending_dialogue_request as add_dialogue_request_ext,
    are_npcs_on_cooldown # IMPORTED new function
)

settings = get_settings()
# _ws_clients: List[Any] = [] # Renamed _ws to _ws_clients for clarity # REMOVE THIS LINE
SIM_DAY_MINUTES = 24 * 60
MAX_CONCURRENT_DB_OPS = 5 # Tune this value
db_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_OPS)
# --- End Semaphore ---

NPC_ACTION_LOG_INTERVAL = 10 # Log NPC actions every this many ticks
RANDOM_CHALLENGE_PROBABILITY = 0.05

# Global constants
MOVEMENT_AREA_MARGIN = 20  # NPCs should stay 20 units away from area boundaries
EXPECTED_AREA_WIDTH = 400 # Standard assumed width for an area's local coordinate space
EXPECTED_AREA_HEIGHT = 300 # Standard assumed height for an area's local coordinate space

async def get_current_sim_time_and_day() -> Dict[str, int]:
    """Fetches current sim_min from sim_clock and day from environment."""
    try:
        sim_clock_response = await execute_supabase_query(lambda: supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute())
        environment_response = await execute_supabase_query(lambda: supa.table('environment').select('day').eq('id', 1).maybe_single().execute())
        
        sim_clock_data = sim_clock_response.data
        environment_data = environment_response.data
        
        current_sim_min = sim_clock_data.get('sim_min', 0) if sim_clock_data else 0
        current_day = environment_data.get('day', 1) if environment_data else 1
        
        return {"sim_min": current_sim_min, "day": current_day}
    except Exception as e:
        print(f"Error fetching sim time and day: {e}")
        return {"sim_min": 0, "day": 1} # Fallback

# DELETE run_daily_planning function definition (approx. lines 45-195)
# async def run_daily_planning(current_day: int, current_sim_minutes_total: int, specific_npc_id: Optional[str] = None):
# ... (entire function body) ...
# import traceback; traceback.print_exc()

# DELETE run_nightly_reflection function definition (approx. lines 198-312)
# async def run_nightly_reflection(day_being_reflected: int, current_sim_minutes_total: int):
# ... (entire function body) ...
# await broadcast_ws_message("reflection_event", {"npc_name": npc.get('name', 'UNKNOWN'), "status": "error_reflection", "day": day_being_reflected})

# --- Global list for pending dialogues ---
# pending_dialogue_requests: List[Dict[str, Any]] = [] # Stores {npc_a_id, npc_b_id, tick}
# --- End pending dialogues list ---

# --- Global dict for NPC dialogue cooldowns ---
# npc_dialogue_cooldown_until: Dict[str, int] = {} # npc_id -> sim_min until they can chat again
# DIALOGUE_COOLDOWN_MINUTES = 360 # MODIFIED: Was 20, changed to 6 hours (6 * 60)
# --- End cooldown dict ---

async def update_npc_actions_and_state(all_npcs_data: List[Dict], current_sim_minutes_total: int, actual_current_day: int, new_sim_min_of_day: int, all_areas_data: List[Dict]):
    # No debug logging here
    if not all_npcs_data: return

    action_defs_res = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, emoji').execute())
    action_defs_map = {ad['id']: {'title': ad['title'], 'emoji': ad['emoji']} for ad in (action_defs_res.data or [])}

    for npc_snapshot in all_npcs_data:
        npc_id = npc_snapshot['id']
        npc_name = npc_snapshot.get('name', 'UnknownNPC')

        current_action_instance_id = npc_snapshot.get('current_action_id')
        current_position_data = npc_snapshot.get('spawn', {}) # Ensure spawn is a dict
        action_just_completed = False
        new_action_started_this_tick = False # Flag to track if a new action (not wander) started

        # 1. Check completion of current action
        if current_action_instance_id:
            action_instance_res = await execute_supabase_query(lambda: supa.table('action_instance').select('start_min, duration_min, status, def_id, object_id').eq('id', current_action_instance_id).maybe_single().execute())
            if action_instance_res and action_instance_res.data:
                act_inst = action_instance_res.data
                action_planned_day_start_abs = (actual_current_day - 1) * SIM_DAY_MINUTES
                action_instance_start_abs = action_planned_day_start_abs + act_inst['start_min']

                if act_inst['status'] == 'active' and (current_sim_minutes_total >= action_instance_start_abs + act_inst['duration_min']):
                    await execute_supabase_query(lambda: supa.table('action_instance').update({'status': 'done'}).eq('id', current_action_instance_id).execute())
                    await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).eq('id', npc_id).execute())
                    current_action_instance_id = None 
                    action_just_completed = True
            else: # Action instance not found, clear it from NPC
                await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).eq('id', npc_id).execute())
                current_action_instance_id = None
                action_just_completed = True

        # 2. If no current action OR an action just completed, find and start next scheduled action for *today*
        if not current_action_instance_id:
            plan_response_obj = await execute_supabase_query(lambda: supa.table('plan').select('actions').eq('npc_id', npc_id).eq('sim_day', actual_current_day).maybe_single().execute())
            next_action_to_start = None
            if plan_response_obj and plan_response_obj.data and plan_response_obj.data.get('actions'):
                action_instance_ids_in_plan = plan_response_obj.data['actions']
                if action_instance_ids_in_plan:
                    action_instances_res = await execute_supabase_query(lambda: supa.table('action_instance')
                        .select('id, start_min, status, def_id, object_id')
                        .in_('id', action_instance_ids_in_plan)
                        .order('start_min')
                        .execute())
                    if action_instances_res and action_instances_res.data:
                        for inst in action_instances_res.data:
                            if inst['status'] == 'queued' and new_sim_min_of_day >= inst['start_min']:
                                next_action_to_start = inst
                                break
            
            if next_action_to_start:
                new_action_instance_id = next_action_to_start['id']
                new_action_def_id = next_action_to_start.get('def_id')
                object_id_for_new_action = next_action_to_start.get('object_id')
                action_details = action_defs_map.get(new_action_def_id, {'title': 'Unknown Action', 'emoji': '❓'})
                action_title_log = action_details['title']
                action_emoji_log = action_details['emoji']

                await execute_supabase_query(lambda: supa.table('action_instance').update({'status': 'active'}).eq('id', new_action_instance_id).execute())
                
                npc_update_payload = {'current_action_id': new_action_instance_id}
                action_moved_npc = False

                if object_id_for_new_action:
                    obj_res = await execute_supabase_query(lambda: supa.table('object').select('area_id, name').eq('id', object_id_for_new_action).maybe_single().execute()) # x,y from object not used for random pos
                    if obj_res and obj_res.data and obj_res.data.get('area_id'):
                        obj_data = obj_res.data
                        target_area_id_for_action = obj_data['area_id']
                        
                        # Use EXPECTED_AREA_WIDTH/HEIGHT for random positioning within the target area
                        effective_movable_width = EXPECTED_AREA_WIDTH - 2 * MOVEMENT_AREA_MARGIN
                        effective_movable_height = EXPECTED_AREA_HEIGHT - 2 * MOVEMENT_AREA_MARGIN

                        if effective_movable_width < 1 or effective_movable_height < 1:
                            wander_target_x = EXPECTED_AREA_WIDTH / 2
                            wander_target_y = EXPECTED_AREA_HEIGHT / 2
                        else:
                            wander_target_x = random.uniform(MOVEMENT_AREA_MARGIN, EXPECTED_AREA_WIDTH - MOVEMENT_AREA_MARGIN)
                            wander_target_y = random.uniform(MOVEMENT_AREA_MARGIN, EXPECTED_AREA_HEIGHT - MOVEMENT_AREA_MARGIN)
                        
                        action_position_payload = {
                            'x': wander_target_x, 
                            'y': wander_target_y, 
                            'areaId': target_area_id_for_action # Use areaId from object
                        }
                        npc_update_payload['spawn'] = action_position_payload
                        action_moved_npc = True
                
                await execute_supabase_query(lambda: supa.table('npc').update(npc_update_payload).eq('id', npc_id).execute())
                current_action_instance_id = new_action_instance_id
                new_action_started_this_tick = True

                if action_moved_npc:
                    before_area_id = current_position_data.get('areaId')
                    current_position_data = npc_update_payload['spawn'] # Update local state
                    after_area_id = current_position_data.get('areaId')
                    if before_area_id != after_area_id and before_area_id is not None and after_area_id is not None:
                        await create_area_change_observations(npc_id, npc_name, before_area_id, after_area_id, all_npcs_data, current_sim_minutes_total, actual_current_day)
                
                await broadcast_ws_message("action_start", {"npc_name": npc_name, "action_title": action_title_log, "emoji": action_emoji_log, "sim_time": new_sim_min_of_day, "day": actual_current_day})
            else: # No next action to start
                if npc_snapshot.get('current_action_id'): # Clear if somehow still set (e.g., plan deleted)
                    await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).eq('id', npc_id).execute())
                current_action_instance_id = None

        # 3. Always-on Same-Area Wander
        # This wander happens if no new action started this tick OR if a new action started but didn't move the NPC.
        # If an action DID move the NPC, this wander logic is skipped for this tick to avoid immediate overwrite.
        # The probability controls how often wander occurs even if eligible.
        
        perform_wander_this_tick = False
        
        # Determine NPC-specific wander probability from DB field, with a default
        npc_wander_probability_from_db = npc_snapshot.get('wander_probability')
        if isinstance(npc_wander_probability_from_db, (float, int)) and 0.0 <= float(npc_wander_probability_from_db) <= 1.0:
            npc_specific_wander_probability = float(npc_wander_probability_from_db)
        else:
            # Default if not set, null, or invalid. Log if it's set but invalid.
            if npc_wander_probability_from_db is not None:
                print(f"[Scheduler] NPC {npc_name} has invalid wander_probability '{npc_wander_probability_from_db}'. Defaulting to 0.4.")
            npc_specific_wander_probability = 0.40 

        if not new_action_started_this_tick or (new_action_started_this_tick and not action_moved_npc):
            if random.random() < npc_specific_wander_probability: # Use NPC-specific probability
                 perform_wander_this_tick = True

        if perform_wander_this_tick:
            current_area_id_for_wander = current_position_data.get('areaId')
            if current_area_id_for_wander: # Ensure NPC is in a known area
                # We assume the area uses EXPECTED_AREA_WIDTH/HEIGHT for its local coordinate system
                effective_movable_width = EXPECTED_AREA_WIDTH - 2 * MOVEMENT_AREA_MARGIN
                effective_movable_height = EXPECTED_AREA_HEIGHT - 2 * MOVEMENT_AREA_MARGIN

                if effective_movable_width < 1 or effective_movable_height < 1:
                    wander_target_x = EXPECTED_AREA_WIDTH / 2
                    wander_target_y = EXPECTED_AREA_HEIGHT / 2
                else:
                    wander_target_x = random.uniform(MOVEMENT_AREA_MARGIN, EXPECTED_AREA_WIDTH - MOVEMENT_AREA_MARGIN)
                    wander_target_y = random.uniform(MOVEMENT_AREA_MARGIN, EXPECTED_AREA_HEIGHT - MOVEMENT_AREA_MARGIN)
                
                # Only apply wander if the new position is different from current
                current_x = current_position_data.get('x')
                current_y = current_position_data.get('y')

                if wander_target_x != current_x or wander_target_y != current_y:
                    wander_position_payload = {
                        'x': wander_target_x,
                        'y': wander_target_y,
                        'areaId': current_area_id_for_wander # Keep same areaId
                    }
                    await execute_supabase_query(lambda: supa.table('npc').update({'spawn': wander_position_payload}).eq('id', npc_id).execute())
                    # If wander moves, current_position_data is updated for any subsequent logic in THIS tick (none currently)
                    # current_position_data = wander_position_payload 
                    # print(f"[MOTION_WANDER] NPC {npc_id} ({npc_name}) wandered in area {current_area_id_for_wander} to ({wander_target_x:.2f}, {wander_target_y:.2f})")


# Helper function to generate observations for NPC area changes
async def create_area_change_observations(moving_npc_id, moving_npc_name, from_area_id, to_area_id, all_npcs_data, current_sim_minutes_total, actual_current_day):
    """Create observation memories when NPCs change areas or notice others in their area.
    Also broadcasts WebSocket messages for these social events."""
    try:
        # Get area names for better descriptions
        from_area_name = "an area"
        to_area_name = "an area"
        
        sim_min_of_day = current_sim_minutes_total % SIM_DAY_MINUTES

        area_res_from = await execute_supabase_query(lambda: supa.table('area').select('name').eq('id', from_area_id).maybe_single().execute())
        if area_res_from and area_res_from.data:
            from_area_name = area_res_from.data.get('name', "an area")
            
        area_res_to = await execute_supabase_query(lambda: supa.table('area').select('name').eq('id', to_area_id).maybe_single().execute())
        if area_res_to and area_res_to.data:
            to_area_name = area_res_to.data.get('name', "an area")
        
        # Part 1: Observations related to the NEW area (to_area_id)
        npcs_in_new_area = [
            npc for npc in all_npcs_data 
            if npc.get('spawn', {}).get('areaId') == to_area_id and npc['id'] != moving_npc_id
        ]

        if npcs_in_new_area:
            moving_npc_data_list = [n for n in all_npcs_data if n['id'] == moving_npc_id] # Use list comp for safety
            if moving_npc_data_list: # Ensure moving_npc_data is found
                moving_npc_data = moving_npc_data_list[0]
                for other_npc_in_new_area in npcs_in_new_area:
                    # Create observation for the moving NPC noticing someone already in the new area
                    moving_sees_other_obs = f"[Social] I saw {other_npc_in_new_area['name']} in the {to_area_name}."
                    moving_sees_other_embedding = await get_embedding(moving_sees_other_obs)
                    if moving_sees_other_embedding:
                        mem_payload_mover = {
                            'npc_id': moving_npc_id, 
                            'sim_min': current_sim_minutes_total, 
                            'kind': 'obs', 
                            'content': moving_sees_other_obs, 
                            'importance': 2, 
                            'embedding': moving_sees_other_embedding
                        }
                        db_response_mover = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_mover).execute())
                        if db_response_mover.data:
                            await broadcast_ws_message("social_event", {
                                "observer_npc_id": moving_npc_id,
                                "observer_npc_name": moving_npc_name,
                                "event_type": "saw_other_in_new_area",
                                "target_npc_name": other_npc_in_new_area['name'],
                                "area_name": to_area_name,
                                "description": moving_sees_other_obs,
                                "sim_min_of_day": sim_min_of_day,
                                "day": actual_current_day
                            })
                    
                    # Create observation for the other NPC (already in new area) noticing the moving NPC enter
                    other_sees_moving_enter_obs = f"[Social] I saw {moving_npc_name} enter the {to_area_name}."
                    other_sees_moving_enter_embedding = await get_embedding(other_sees_moving_enter_obs)
                    if other_sees_moving_enter_embedding:
                        mem_payload_other = {
                            'npc_id': other_npc_in_new_area['id'], 
                            'sim_min': current_sim_minutes_total, 
                            'kind': 'obs', 
                            'content': other_sees_moving_enter_obs, 
                            'importance': 2, 
                            'embedding': other_sees_moving_enter_embedding
                        }
                        db_response_other = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_other).execute())
                        if db_response_other.data:
                             await broadcast_ws_message("social_event", {
                                "observer_npc_id": other_npc_in_new_area['id'],
                                "observer_npc_name": other_npc_in_new_area['name'],
                                "event_type": "other_saw_me_enter", # From perspective of observer
                                "target_npc_name": moving_npc_name,
                                "area_name": to_area_name,
                                "description": other_sees_moving_enter_obs,
                                "sim_min_of_day": sim_min_of_day,
                                "day": actual_current_day
                            })

        # Part 2: Observations related to the OLD area (from_area_id)
        npcs_in_old_area = [
            npc for npc in all_npcs_data 
            if npc.get('spawn', {}).get('areaId') == from_area_id and npc['id'] != moving_npc_id
        ]

        for other_npc_in_old_area in npcs_in_old_area:
            # Create observation for the other NPC (in old area) noticing the moving NPC leave
            other_sees_moving_leave_obs = f"[Social] I saw {moving_npc_name} leave the {from_area_name}."
            other_sees_moving_leave_embedding = await get_embedding(other_sees_moving_leave_obs)
            if other_sees_moving_leave_embedding:
                mem_payload = {
                    'npc_id': other_npc_in_old_area['id'], 
                    'sim_min': current_sim_minutes_total, 
                    'kind': 'obs', 
                    'content': other_sees_moving_leave_obs, 
                    'importance': 2, 
                    'embedding': other_sees_moving_leave_embedding
                }
                db_response_leave = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload).execute())
                if db_response_leave.data:
                    await broadcast_ws_message("social_event", {
                        "observer_npc_id": other_npc_in_old_area['id'],
                        "observer_npc_name": other_npc_in_old_area['name'],
                        "event_type": "other_saw_me_leave", # From perspective of observer
                        "target_npc_name": moving_npc_name,
                        "area_name": from_area_name,
                        "description": other_sees_moving_leave_obs,
                        "sim_min_of_day": sim_min_of_day,
                        "day": actual_current_day
                    })
            
            # The moving NPC does not create an observation about NPCs in the area they just left in this context.
            # If desired, a separate "looking back" observation could be made by the mover, but that's new logic.

    except Exception as e:
        print(f"Error creating area change observations or broadcasting: {e}") # Updated log
        # Don't raise the exception further as this is non-critical functionality

# Modify advance_tick to pass all_areas_data to update_npc_actions_and_state
async def advance_tick():
    try:
        # print("DEBUG: advance_tick - Top of tick") # Silenced
        time_data_before_tick_res = await execute_supabase_query(lambda: supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute()) # Fetch sim_min
        env_day_res = await execute_supabase_query(lambda: supa.table('environment').select('day').eq('id', 1).maybe_single().execute()) # Fetch day
        current_sim_min_total_old = time_data_before_tick_res.data.get('sim_min', 0) if time_data_before_tick_res.data else 0
        current_day_old = env_day_res.data.get('day', 1) if env_day_res.data else 1
        # print(f"Tick START: Day {current_day_old}, Min {current_sim_min_total_old}") # REMOVE

        increment_value = settings.TICK_SIM_MIN
        rpc_params = {'increment_value': increment_value}
        time_update_response = await execute_supabase_query(lambda: supa.rpc('increment_sim_min', rpc_params).execute())
        
        if not (time_update_response and time_update_response.data and len(time_update_response.data) > 0):
            print(f"!!!! advance_tick - RPC increment_sim_min FAILED. Cannot proceed with tick.")
            return
        
        new_time_data = time_update_response.data[0]
        new_sim_min_of_day = new_time_data.get('new_sim_min')
        actual_current_day = new_time_data.get('new_day')

        if new_sim_min_of_day is None or actual_current_day is None: return # Should have data from RPC
        # print(f"Tick  END : Day {actual_current_day}, Min {new_sim_min_of_day} (RPC successful)") # REMOVE

        current_sim_minutes_total = ((actual_current_day - 1) * SIM_DAY_MINUTES) + new_sim_min_of_day
        
        # Fetch all NPCs and Areas once for this tick if needed by sub-functions
        # These are used by update_npc_actions_and_state and encounter_detection
        all_npcs_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name, current_action_id, spawn, traits, wander_probability').execute())
        all_npcs_data = all_npcs_res.data or []
        all_areas_res = await execute_supabase_query(lambda: supa.table('area').select('id, bounds').execute())
        all_areas_data_for_tick = all_areas_res.data or []

        await update_npc_actions_and_state(all_npcs_data, current_sim_minutes_total, actual_current_day, new_sim_min_of_day, all_areas_data_for_tick)

        # --- Start Dialogue Encounter Detection & Initiation ---
        # Check for NPC encounters to initiate dialogues
        # Make sure all_npcs_data is current after update_npc_actions_and_state might have changed positions
        # Re-fetch might be too slow, assume all_npcs_data passed to update_npc_actions_and_state is sufficient
        # OR, update_npc_actions_and_state should return the modified all_npcs_data if positions changed.
        # For now, we'll use the all_npcs_data fetched at the start of the tick. This might mean
        # a dialogue is initiated based on positions *before* the wander/action movement of this tick.
        # This is a potential refinement area if dialogues seem to trigger for NPCs that just moved apart.

        if len(all_npcs_data) >= 2:
            # print(f"[DialogueCheck] Tick {current_sim_minutes_total}: Evaluating {len(all_npcs_data)} NPCs for dialogue.") # REMOVED THIS LOG
            # Randomly select two different NPCs
            npc1_data, npc2_data = random.sample(all_npcs_data, 2)

            npc1_id = npc1_data['id']
            npc1_name = npc1_data.get('name', 'NPC1')
            npc1_pos_data = npc1_data.get('spawn', {})
            npc1_area_id = npc1_pos_data.get('areaId')

            npc2_id = npc2_data['id']
            npc2_name = npc2_data.get('name', 'NPC2')
            npc2_pos_data = npc2_data.get('spawn', {})
            npc2_area_id = npc2_pos_data.get('areaId')

            if npc1_area_id == npc2_area_id:
                # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are in the same area: {npc1_area_id}.") # Too verbose
                distance = math.sqrt((npc1_pos_data['x'] - npc2_pos_data['x'])**2 + (npc1_pos_data['y'] - npc2_pos_data['y'])**2)
                
                if distance < 10000: # Effectively same-area check now
                    # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are close enough (dist: {distance:.2f} < 10000).") # Too verbose
                    
                    # ---- START NEW COOLDOWN CHECK from dialogue_service ----
                    if await are_npcs_on_cooldown(npc1_id, npc2_id, current_sim_minutes_total):
                        # print(f"[DialogueCheck] NPCs {npc1_name} & {npc2_name} on cooldown (checked by scheduler). Skipping further checks.") # Optional: verbose log
                        return # Skip to next pair if on cooldown
                    # ---- END NEW COOLDOWN CHECK ----

                    if random.random() < 0.50: 
                        print(f"[DialogueCheck] SUCCESS: Random chance (50%) passed for {npc1_name} and {npc2_name}. Adding dialogue request.")
                        
                        # Prepare additional arguments for add_pending_dialogue_request
                        npc1_traits = npc1_data.get('traits', [])
                        npc2_traits = npc2_data.get('traits', [])
                        area_name_for_trigger = "their current area" # Placeholder, ideally fetch area name
                        if npc1_area_id: # Try to get a more specific area name
                            area_details = await get_area_details(npc1_area_id) # Assuming get_area_details can fetch by ID
                            if area_details and area_details.get('name'):
                                area_name_for_trigger = area_details.get('name')

                        trigger_event = f"saw {npc2_name} in {area_name_for_trigger}" # From NPC1's perspective
                        
                        await add_dialogue_request_ext(
                            npc_a_id=npc1_id, 
                            npc_b_id=npc2_id, 
                            npc_a_name=npc1_name, 
                            npc_b_name=npc2_name,
                            npc_a_traits=npc1_traits,
                            npc_b_traits=npc2_traits,
                            trigger_event=trigger_event,
                            current_tick=current_sim_minutes_total
                        )
                    else:
                        print(f"[DialogueCheck] FAILED: Random chance (50%) for {npc1_name} and {npc2_name}.")
                else:
                    print(f"[DialogueCheck] FAILED: NPCs {npc1_name} and {npc2_name} are too far apart (dist: {distance:.2f}).")
            # else:
                # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are in different areas.")
        # --- End Dialogue Encounter Detection & Initiation ---

        # Process pending dialogues using the external service
        npcs_to_replan_after_dialogue = await process_dialogues_ext(current_sim_minutes_total)
        if npcs_to_replan_after_dialogue:
            print(f"Scheduler: {len(npcs_to_replan_after_dialogue)} NPCs need replanning after dialogues: {npcs_to_replan_after_dialogue}")
            for npc_id_to_replan in npcs_to_replan_after_dialogue:
                # Check if NPC exists in all_npcs_data before attempting to replan
                if any(npc['id'] == npc_id_to_replan for npc in all_npcs_data):
                    print(f"Scheduler: Triggering replan for NPC {npc_id_to_replan} due to dialogue outcome.")
                    await run_daily_planning(actual_current_day, current_sim_minutes_total, specific_npc_id=npc_id_to_replan)
                else:
                    print(f"Scheduler: NPC {npc_id_to_replan} marked for replan not found in current NPC list. Skipping replan.")

        # MODIFIED: Split reflection and planning into separate conditions
        # Run reflections at midnight (start of day)
        if new_sim_min_of_day < settings.TICK_SIM_MIN: # True at start of day (00:00 to 00:14 for TICK_SIM_MIN=15)
            if actual_current_day > 1: # Reflection for previous day
                day_that_just_ended = actual_current_day - 1
                reflection_context_time = ((day_that_just_ended - 1) * SIM_DAY_MINUTES) + (SIM_DAY_MINUTES - 1) # Effective end of day
                print(f"Running nightly reflection at start of Day {actual_current_day}")
                await run_nightly_reflection(day_that_just_ended, reflection_context_time)
        
        # MODIFIED: Run planning at 5 AM (300 minutes into the day)
        # Using a range to ensure it triggers even with different tick intervals
        if 300 <= new_sim_min_of_day < (300 + settings.TICK_SIM_MIN):
            print(f"Running daily planning at 5 AM of Day {actual_current_day}")
            await run_daily_planning(actual_current_day, current_sim_minutes_total)
        
        # Create plan adherence observations at 12:00 and 00:00
        if new_sim_min_of_day == 720 or new_sim_min_of_day == 0:  # 12:00 or 00:00
            await create_plan_adherence_observations(all_npcs_data, current_sim_minutes_total, actual_current_day, new_sim_min_of_day)
            
        await spawn_random_challenge(current_sim_minutes_total, actual_current_day)
        
        # Observation Logging (simplified log for now)
        # print(f"  Observation logging for Day {actual_current_day} - {new_sim_min_of_day // 60:02d}:{new_sim_min_of_day % 60:02d}") # REMOVE

        # 5. WebSocket broadcast
        await broadcast_ws_message("tick_update", {'new_sim_min': new_sim_min_of_day, 'new_day': actual_current_day})
    except Exception as e_adv_tick:
        print(f"CRITICAL ERROR in advance_tick: {e_adv_tick}")
        import traceback; traceback.print_exc()

# Helper function to create plan adherence observations
async def create_plan_adherence_observations(all_npcs_data, current_sim_minutes_total, current_day, current_min_of_day):
    """Create observations about whether NPCs are following their plans or have unexpected deviations."""
    try:
        # Get the time label for the observation
        time_label = "noon" if current_min_of_day == 720 else "midnight"
        
        for npc in all_npcs_data:
            npc_id = npc.get('id')
            npc_name = npc.get('name', 'Unknown')
            current_action_id = npc.get('current_action_id')
            
            # Check current plan for the NPC
            plan_res = await execute_supabase_query(lambda: supa.table('plan').select('actions').eq('npc_id', npc_id).eq('sim_day', current_day).maybe_single().execute())
            
            if not (plan_res and plan_res.data and plan_res.data.get('actions')):
                # No plan for this day
                observation_content = f"[Periodic] At {time_label}, I realized I don't have a plan for today."
                importance = 2
            else:
                plan_action_ids = plan_res.data.get('actions', [])
                
                # Check for action that should be happening now
                current_action_title = "nothing scheduled"
                scheduled_action_found = False
                
                if plan_action_ids:
                    # Look for scheduled actions around this time
                    time_window_start = max(0, current_min_of_day - 60)  # Look at actions starting up to 1 hour ago
                    time_window_end = min(1439, current_min_of_day + 60)  # And up to 1 hour in the future
                    
                    scheduled_actions_res = await execute_supabase_query(lambda: supa.table('action_instance')
                        .select('id, def_id(title), start_min, status')
                        .in_('id', plan_action_ids)
                        .gte('start_min', time_window_start)
                        .lte('start_min', time_window_end)
                        .order('start_min')
                        .execute())
                    
                    if scheduled_actions_res and scheduled_actions_res.data:
                        scheduled_action = None
                        for action in scheduled_actions_res.data:
                            if abs(action.get('start_min', 0) - current_min_of_day) <= 60:  # Within 1 hour
                                scheduled_action = action
                                break
                        
                        if scheduled_action:
                            scheduled_action_found = True
                            current_action_title = scheduled_action.get('def_id', {}).get('title', 'an activity')
                            scheduled_action_id = scheduled_action.get('id')
                            scheduled_action_status = scheduled_action.get('status', 'unknown')
                
                # Determine if the NPC is following their plan
                if not scheduled_action_found:
                    # No action scheduled around this time
                    if current_action_id:
                        # But they're doing something
                        action_res = await execute_supabase_query(lambda: supa.table('action_instance').select('def_id(title)').eq('id', current_action_id).maybe_single().execute())
                        if action_res and action_res.data:
                            actual_action_title = action_res.data.get('def_id', {}).get('title', 'something unplanned')
                            observation_content = f"[Periodic] At {time_label}, I was doing {actual_action_title} which wasn't part of my original plan."
                            importance = 2
                        else:
                            observation_content = f"[Periodic] At {time_label}, I was doing something unplanned."
                            importance = 2
                    else:
                        # And they're not doing anything
                        observation_content = f"[Periodic] At {time_label}, I had nothing scheduled and was idle as expected."
                        importance = 1
                else:
                    # There is an action scheduled
                    if current_action_id and current_action_id == scheduled_action_id:
                        # And they're doing it
                        observation_content = f"[Periodic] At {time_label}, I was following my plan by doing {current_action_title}."
                        importance = 1
                    elif current_action_id:
                        # But they're doing something else
                        action_res = await execute_supabase_query(lambda: supa.table('action_instance').select('def_id(title)').eq('id', current_action_id).maybe_single().execute())
                        if action_res and action_res.data:
                            actual_action_title = action_res.data.get('def_id', {}).get('title', 'something different')
                            observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title} according to my plan, but instead I was doing {actual_action_title}."
                            importance = 3  # Higher importance for deviation
                        else:
                            observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title}, but I was doing something else."
                            importance = 3
                    else:
                        # But they're not doing anything
                        observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title}, but I wasn't doing anything."
                        importance = 3
            
            # Create the observation memory
            observation_embedding = await get_embedding(observation_content)
            if observation_embedding:
                mem_payload = {
                    'npc_id': npc_id,
                    'sim_min': current_sim_minutes_total,
                    'kind': 'obs',
                    'content': observation_content,
                    'importance': importance,
                    'embedding': observation_embedding
                }
                await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload).execute())
    
    except Exception as e:
        print(f"Error creating plan adherence observations: {e}")
        # Don't raise the exception as this is non-critical functionality

# --- Random Challenges Configuration ---
RANDOM_CHALLENGES = [
    {
        "code": "fire_alarm", "label": "Fire alarm rings", 
        "effect_desc": "The fire alarm blares!", 
        "duration": 30, "priority_action": "Evacuate", "metadata": {}
    },
    {
        "code": "pizza_drop", "label": "Free pizza in Lounge", 
        "effect_desc": "A wild pizza appears in the Lounge!", 
        "duration": 60, "priority_action": "Get Pizza", "metadata": {"target_area_name": "Lounge", "npc_trait_filter": "greedy"}
    },
    {
        "code": "wifi_down", "label": "Office Wi-Fi outage", 
        "effect_desc": "The Office Wi-Fi just went down!", 
        "duration": 240, "priority_action": "Complain about Wi-Fi", "metadata": {"target_area_name": "Office", "affected_action_title": "Work"}
    },
]
# Ensure these priority_actions ("Evacuate", "Get Pizza", "Complain about Wi-Fi") exist in action_def table later.
# --- End Random Challenges ---

async def spawn_random_challenge(current_sim_minutes_total: int, current_day: int):
    if random.random() < RANDOM_CHALLENGE_PROBABILITY:
        challenge = random.choice(RANDOM_CHALLENGES)
        print(f"EVENT: Random challenge triggered - {challenge['label']} at Day {current_day}, SimMin {current_sim_minutes_total}")
        
        event_start_min = current_sim_minutes_total
        event_end_min = current_sim_minutes_total + challenge['duration']

        sim_event_payload = {
            'type': challenge['code'],
            'start_min': event_start_min,
            'end_min': event_end_min,
            'metadata': challenge['metadata']
        }
        # Corrected: Remove .select('id'), rely on default return for ID
        event_response_obj = await execute_supabase_query(lambda: supa.table('sim_event').insert(sim_event_payload).execute())
        
        event_id = None
        if event_response_obj and event_response_obj.data and len(event_response_obj.data) > 0:
            event_id = event_response_obj.data[0].get('id')
        
        if event_id:
            print(f"  -> sim_event row inserted, ID: {event_id}. Desc: {challenge['effect_desc']}")
            ws_event_data = {'event_code': challenge['code'], 'description': challenge['effect_desc'], 'tick': current_sim_minutes_total, 'event_id': event_id, 'day': current_day}
            await broadcast_ws_message("sim_event", ws_event_data)
            
            # Create observations for NPCs in the affected area (if area-specific) or all NPCs
            await create_event_observations(challenge, current_sim_minutes_total)
        else:
            # Check if there was a Postgrest error object, otherwise assume no data means failure to get ID
            error_info = "No data returned from insert"
            if hasattr(event_response_obj, 'error') and event_response_obj.error: # Should not happen if APIError is raised
                error_info = event_response_obj.error
            elif not (event_response_obj and event_response_obj.data): # If no data and no explicit error attribute
                error_info = f"Insert call did not return data. Status: {getattr(event_response_obj, 'status_code', 'N/A')}"

            print(f"  !!!! Failed to insert sim_event for {challenge['code']} or get ID. Details: {error_info}")

# Helper function to create observations for environmental events
async def create_event_observations(event_data, current_sim_minutes_total):
    """Create observation memories for NPCs based on environmental events."""
    try:
        # Get all NPCs
        npcs_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name, spawn').execute())
        if not (npcs_res and npcs_res.data):
            return
            
        # Check if this is an area-specific event
        target_area_name = event_data.get('metadata', {}).get('target_area_name')
        target_area_id = None
        
        if target_area_name:
            # Get the area ID from the name
            area_res = await execute_supabase_query(lambda: supa.table('area').select('id').eq('name', target_area_name).maybe_single().execute())
            if area_res and area_res.data:
                target_area_id = area_res.data.get('id')
        
        # Build the observation content
        event_desc = event_data.get('effect_desc', f"Something happened: {event_data.get('label', 'Unknown event')}")
        
        # Process each NPC
        for npc in npcs_res.data:
            npc_id = npc.get('id')
            npc_area_id = npc.get('spawn', {}).get('areaId')
            
            # Skip NPCs not in the target area if this is an area-specific event
            if target_area_id and npc_area_id != target_area_id:
                continue
                
            # Create the observation with appropriate wording based on area
            observation_content = event_desc
            if target_area_name and npc_area_id == target_area_id:
                observation_content = f"[Environment] While in the {target_area_name}, I noticed: {event_desc}"
            else:
                observation_content = f"[Environment] {event_desc}"
            
            # Get embedding and store the memory
            observation_embedding = await get_embedding(observation_content)
            if observation_embedding:
                mem_payload = {
                    'npc_id': npc_id,
                    'sim_min': current_sim_minutes_total,
                    'kind': 'obs',
                    'content': observation_content,
                    'importance': 3,  # Events are more important than regular observations
                    'embedding': observation_embedding
                }
                await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload).execute())
    except Exception as e:
        print(f"Error creating event observations: {e}")
        # Don't raise the exception as this is non-critical functionality

# Modify _loop to call spawn_random_challenge
async def _loop():
    print("Scheduler _loop STARTED") # KEEP
    loop_count = 0
    while True:
        loop_count += 1
        try:
            await asyncio.sleep(settings.TICK_REAL_SEC)
            await advance_tick()
            # if loop_count % NPC_ACTION_LOG_INTERVAL == 0: # Temporarily disable periodic status log to backend console
            #     print(f"--- NPC Status Update (Tick {loop_count}) ---")
            #     # ... (rest of status log logic)
            #     print("-------------------------------------")
        except Exception as e_loop:
            print(f"CRITICAL ERROR IN _loop: {e_loop}") # KEEP
            import traceback; traceback.print_exc() # KEEP
            break # Keep break to stop a runaway error loop

def start_loop():
    print("Scheduler start_loop CALLED")
    asyncio.create_task(_loop())
