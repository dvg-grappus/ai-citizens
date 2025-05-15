import asyncio
import json
from typing import List, Any, Dict, Set # Added Set
import re # For parsing plan
from datetime import date # For sim_date
import math # Already there, but good to note for sqrt
import random # For dialogue initiation chance
from postgrest.exceptions import APIError # Import APIError

# Use relative imports for consistency and to avoid issues if backend is run as a module
from .services import supa 
from .config import get_settings
from .llm import call_llm # Added
from .prompts import PLAN_SYSTEM_PROMPT_TEMPLATE, PLAN_USER_PROMPT_TEMPLATE, format_traits, REFLECTION_SYSTEM_PROMPT_TEMPLATE, REFLECTION_USER_PROMPT_TEMPLATE, DIALOGUE_SYSTEM_PROMPT_TEMPLATE, DIALOGUE_USER_PROMPT_TEMPLATE # Added
from .memory_service import retrieve_memories, get_embedding # Added retrieve_memories and get_embedding for plan memory

settings = get_settings()
_ws_clients: List[Any] = [] # Renamed _ws to _ws_clients for clarity
SIM_DAY_MINUTES = 24 * 60
MAX_CONCURRENT_DB_OPS = 5 # Tune this value
db_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_OPS)
# --- End Semaphore ---

NPC_ACTION_LOG_INTERVAL = 10 # Log NPC actions every this many ticks
RANDOM_CHALLENGE_PROBABILITY = 0.05

async def execute_supabase_query(query_executable_lambda):
    """Helper to run a Supabase query method (passed as a lambda) with the semaphore."""
    async with db_semaphore:
        try:
            response = await asyncio.to_thread(query_executable_lambda)
            return response
        except APIError as e:
            if e.code == "204" and "maybe_single()" in str(query_executable_lambda):
                # print(f"DEBUG: execute_supabase_query - Caught 204 No Content for maybe_single") # Silenced for now
                class EmptyResponse:
                    def __init__(self): self.data = None; self.error = None; self.status_code = 204; self.count = 0
                return EmptyResponse()
            else: print(f"Supabase APIError: {e.code} - {e.message}"); raise
        except Exception as e_generic: print(f"Supabase Generic Exception: {e_generic}"); raise

async def get_current_sim_time_and_day() -> Dict[str, int]:
    """Fetches current sim_min from sim_clock and day from environment."""
    try:
        sim_clock_response = await execute_supabase_query(supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute)
        environment_response = await execute_supabase_query(supa.table('environment').select('day').eq('id', 1).maybe_single().execute)
        
        sim_clock_data = sim_clock_response.data
        environment_data = environment_response.data
        
        current_sim_min = sim_clock_data.get('sim_min', 0) if sim_clock_data else 0
        current_day = environment_data.get('day', 1) if environment_data else 1
        
        return {"sim_min": current_sim_min, "day": current_day}
    except Exception as e:
        print(f"Error fetching sim time and day: {e}")
        return {"sim_min": 0, "day": 1} # Fallback

async def run_daily_planning(current_day: int, current_sim_minutes_total: int):
    print(f"**** run_daily_planning CALLED for Day {current_day}, SimTotalMin {current_sim_minutes_total} ****") # PROMINENT LOG
    print(f"PLANNING: Day {current_day} (SimTimeTotal: {current_sim_minutes_total})...")
    try:
        npcs_response_obj = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits, backstory').execute())
        if not (npcs_response_obj and npcs_response_obj.data):
            print("PLANNING: No NPCs found.")
            return
        npcs_data = npcs_response_obj.data
        sim_date_str = f"Day {current_day}"
        
        all_action_defs_response = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, base_minutes').execute())
        action_defs_data = all_action_defs_response.data or []
        action_defs_map_title_to_id = {ad['title']: ad['id'] for ad in action_defs_data if ad.get('title')}
        action_defs_map_id_to_duration = {ad['id']: ad.get('base_minutes', 30) for ad in action_defs_data if ad.get('id')}
        print(f"  [ACTION DEF LOAD FULL] Maps created. Titles: {len(action_defs_map_title_to_id)}, Durations: {len(action_defs_map_id_to_duration)}")

        # Fetch all available objects once to link actions to them
        all_objects_response = await execute_supabase_query(lambda: supa.table('object').select('id, name, area_id').execute())
        all_objects_data = all_objects_response.data or []
        # Create a map for quick lookup, e.g., by object name or type if we had types
        # For now, a simple list to iterate and find first match

        for npc in npcs_data:
            npc_id = npc['id']; npc_name = npc['name']
            await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "started_planning", "day": current_day})
            npc_traits_summary = format_traits(npc.get('traits', []))
            print(f"  PLANNING for {npc_name} (ID: {npc_id})...")

            planning_query_text = f"What are important considerations for {npc_name} for planning {sim_date_str}?"
            retrieved_memories_str = await retrieve_memories(npc_id, planning_query_text, "planning", current_sim_minutes_total)
            
            system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.format(name=npc_name, sim_date=sim_date_str, traits_summary=npc_traits_summary)
            user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(retrieved_memories=retrieved_memories_str)
            raw_plan_text = call_llm(system_prompt, user_prompt, max_tokens=400)

            if not raw_plan_text:
                print(f"    PLANNING - LLM failed to generate a plan for {npc_name}.")
                await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "failed_planning", "day": current_day})
                continue
            print(f"    PLANNING - Raw plan for {npc_name}:\n{raw_plan_text}")

            plan_action_instance_ids = []
            parsed_actions_for_log = []
            for line in raw_plan_text.strip().split('\n'):
                match = re.fullmatch(r"(?:\d+\.\s*)?(\d{2}):(\d{2})\s*[-—–]\s*(.+)", line.strip())
                if match:
                    hh, mm, action_title_raw = match.groups(); action_title = action_title_raw.strip()
                    action_start_sim_min_of_day = int(hh) * 60 + int(mm)
                    action_def_id = action_defs_map_title_to_id.get(action_title)

                    if not action_def_id:
                        print(f"      Warning: Action title '{action_title}' not found in action_def. Skipping.")
                        continue
                    
                    duration_min = action_defs_map_id_to_duration.get(action_def_id, 30)
                    print(f"      [PLAN PARSING {npc_name}] Parsed: {action_title}, ID: {action_def_id}, Start: {action_start_sim_min_of_day}, Dur: {duration_min}")

                    # --- Try to find an object_id for the action ---
                    object_id_for_action = None
                    # Simplistic object association logic for MVP
                    if action_title == "Work":
                        pc_objects = [obj for obj in all_objects_data if obj.get('name') == "PC"]
                        if pc_objects: object_id_for_action = pc_objects[0]['id'] # Take the first PC
                    elif action_title == "Sleep":
                        bed_objects = [obj for obj in all_objects_data if obj.get('name') == "Bed"]
                        if bed_objects: object_id_for_action = bed_objects[0]['id'] # Take the first Bed
                    elif action_title == "Brush Teeth":
                        toothbrush_objects = [obj for obj in all_objects_data if obj.get('name') == "Toothbrush"]
                        if toothbrush_objects: object_id_for_action = toothbrush_objects[0]['id']
                    # Add more specific object associations here if needed for other actions

                    action_instance_data = {
                        'npc_id': npc_id,
                        'def_id': action_def_id,
                        'object_id': object_id_for_action, # NEWLY ADDED
                        'start_min': action_start_sim_min_of_day,
                        'duration_min': duration_min,
                        'status': 'queued'
                    }
                    action_instance_data_list = [action_instance_data]
                    print(f"      [PLAN DB {npc_name}] Inserting action_instance for: {action_title}")
                    
                    # Using the simplified insert first, assuming ID is returned in .data by default
                    def _insert_action_sync(data_list):
                        return supa.table('action_instance').insert(data_list).execute()
                    insert_response_obj = await execute_supabase_query(lambda: _insert_action_sync(action_instance_data_list))

                    action_instance_id = None
                    if insert_response_obj.data and len(insert_response_obj.data) > 0:
                        action_instance_id = insert_response_obj.data[0].get('id')
                        if action_instance_id:
                            plan_action_instance_ids.append(action_instance_id)
                            parsed_actions_for_log.append(f"{hh}:{mm} - {action_title}")
                            print(f"        -> Inserted action_instance ID: {action_instance_id}")
                        else:
                            print(f"        !!!! Inserted '{action_title}' but ID not in response: {insert_response_obj.data}")
                    else:
                        db_error = getattr(insert_response_obj, 'error', None)
                        print(f"        !!!! Failed to insert '{action_title}'. Error: {db_error}. Data: {insert_response_obj.data}")
            
            if plan_action_instance_ids:
                print(f"    [PLAN COMMIT {npc_name}] Inserting plan with {len(plan_action_instance_ids)} action IDs.")
                plan_data = {'npc_id': npc_id, 'sim_day': current_day, 'actions': plan_action_instance_ids}
                await execute_supabase_query(lambda: supa.table('plan').insert(plan_data).execute())
                print(f"    PLANNING - Successfully created plan for {npc_name}.")
                
                plan_memory_content = f"Planned for {sim_date_str}: {len(parsed_actions_for_log)} actions. Details: {'; '.join(parsed_actions_for_log)}"
                plan_memory_embedding = await get_embedding(plan_memory_content)
                if plan_memory_embedding:
                    plan_memory_payload = {'npc_id': npc_id, 'sim_min': current_sim_minutes_total, 'kind': 'plan','content': plan_memory_content, 'importance': 3, 'embedding': plan_memory_embedding}
                    await execute_supabase_query(lambda: supa.table('memory').insert(plan_memory_payload).execute())
                    print(f"      -> PLANNING - Plan memory inserted for {npc_name}.")

                await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "completed_planning", "day": current_day, "num_actions": len(parsed_actions_for_log)})
            else:
                await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "failed_planning", "day": current_day})

    except Exception as e:
        print(f"ERROR in run_daily_planning: {e}")
        import traceback; traceback.print_exc()

async def run_nightly_reflection(day_being_reflected: int, current_sim_minutes_total: int):
    print(f"REFLECTION: Day {day_being_reflected} (ContextTime: {current_sim_minutes_total})...")
    try:
        npcs_response_obj = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits').execute())
        if not (npcs_response_obj and npcs_response_obj.data): 
            print("REFLECTION: No NPCs found.")
            return
        
        sim_date_str = f"Day {day_being_reflected}"
        for npc in npcs_response_obj.data:
            npc_id = npc['id']; npc_name = npc['name']
            await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "started_reflection", "day": day_being_reflected})
            npc_traits_summary = format_traits(npc.get('traits', []))
            print(f"  REFLECTING for {npc_name} (ID: {npc_id})...")
            reflection_query_text = f"Key events and main thoughts for {npc_name} on {sim_date_str}?"
            retrieved_memories_str = await retrieve_memories(npc_id, reflection_query_text, "reflection", current_sim_minutes_total)
            system_prompt = REFLECTION_SYSTEM_PROMPT_TEMPLATE.format(name=npc_name, sim_date=sim_date_str)
            user_prompt = REFLECTION_USER_PROMPT_TEMPLATE.format(traits_summary=npc_traits_summary, retrieved_memories=retrieved_memories_str)
            raw_reflection_text = call_llm(system_prompt, user_prompt, max_tokens=300)
            if not raw_reflection_text: continue
            print(f"    Raw reflection for {npc_name}:\n{raw_reflection_text}")

            for line in raw_reflection_text.strip().split('\n'):
                line = line.strip(); content = line; importance = 1
                if not line.startswith('•'): continue
                match = re.search(r"\[Importance:\s*(\d+)\]$", line, re.IGNORECASE)
                if match: 
                    try: importance = max(1, min(5, int(match.group(1)))); content = re.sub(r"\s*\[Importance:\s*\d+\]$", "", line, flags=re.IGNORECASE).strip()
                    except ValueError: pass # Keep default importance if parsing fails
                content = content.lstrip('• ').strip()
                if not content: continue
                reflection_embedding = await get_embedding(content)
                if reflection_embedding:
                    payload = {'npc_id': npc_id, 'sim_min': current_sim_minutes_total, 'kind': 'reflect','content': content, 'importance': importance, 'embedding': reflection_embedding}
                    print(f"    [REFLECTION DB] About to insert reflection memory: {payload}")
                    reflection_insert_response = await execute_supabase_query(lambda: supa.table('memory').insert(payload).execute())
                    if reflection_insert_response.data and len(reflection_insert_response.data) > 0:
                        print(f"    Stored reflection: '{content}' (Importance: {importance}). Data: {reflection_insert_response.data}")
                    else:
                        print(f"        !!!! Failed to store reflection for '{content}'. No data. Status: {getattr(reflection_insert_response, 'status_code', 'N/A')}")

            await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "completed_reflection", "day": day_being_reflected})
    except Exception as e:
        print(f"ERROR in run_nightly_reflection: {e}")
        import traceback; traceback.print_exc()

# --- Global list for pending dialogues ---
pending_dialogue_requests: List[Dict[str, Any]] = [] # Stores {npc_a_id, npc_b_id, tick}
# --- End pending dialogues list ---

# --- Global dict for NPC dialogue cooldowns ---
npc_dialogue_cooldown_until: Dict[str, int] = {} # npc_id -> sim_min until they can chat again
DIALOGUE_COOLDOWN_MINUTES = 20
# --- End cooldown dict ---

async def process_pending_dialogues(current_sim_minutes_total: int):
    global pending_dialogue_requests # To modify it
    if not pending_dialogue_requests:
        return

    print(f"DEBUG: Processing {len(pending_dialogue_requests)} pending dialogue requests at tick {current_sim_minutes_total}.")
    processed_indices = [] # Store indices of requests that are fully processed (dialogue or not)

    for i, request in enumerate(pending_dialogue_requests):
        npc_a_id = request['npc_a_id']
        npc_b_id = request['npc_b_id']
        npc_a_name = request['npc_a_name']
        npc_b_name = request['npc_b_name']
        npc_a_traits = request['npc_a_traits']
        npc_b_traits = request['npc_b_traits']
        trigger_event = request['trigger_event']
        request_tick = request['tick']

        # Check cooldowns (only proceed if request is recent enough to still be relevant & NPCs are not on cooldown)
        if current_sim_minutes_total > request_tick + DIALOGUE_COOLDOWN_MINUTES: # Stale request
            processed_indices.append(i)
            continue

        if npc_dialogue_cooldown_until.get(npc_a_id, 0) > current_sim_minutes_total or \
           npc_dialogue_cooldown_until.get(npc_b_id, 0) > current_sim_minutes_total:
            # One or both NPCs on cooldown from a *recent previous* dialogue, but this specific encounter might still proceed if it just happened.
            # The playbook says "After a dialogue ends, both NPCs ignore further dialogues for ... 20 sim-minutes"
            # This implies the check should be more about *initiating a new one* if they just finished one.
            # The active dialogue check in encounter detection should prevent simultaneous ones.
            # Let's assume for now if they are on cooldown, they don't initiate a *new* dialogue based on this *pending request*.
            # If they were put on cooldown AFTER this request was added, this check is valid.
            processed_indices.append(i) # Mark as processed as we won't act on it now
            continue

        # Dialogue Initiation Chance (Step 5.2.1 of playbook v2)
        initiation_chance = 0.60 # Base 60%
        if 'friendly' in npc_a_traits or 'friendly' in npc_b_traits: initiation_chance += 0.15
        if 'grumpy' in npc_a_traits or 'grumpy' in npc_b_traits: initiation_chance -= 0.15
        initiation_chance = max(0.1, min(0.9, initiation_chance)) # Clamp between 10% and 90%

        if random.random() < initiation_chance:
            print(f"  Dialogue initiated between {npc_a_name} and {npc_b_name} (Chance: {initiation_chance:.2f})")
            dialogue_turns = 3 # Fixed at 3 exchanges (6 lines total) as per playbook

            # Insert dialogue row (Step 5.2.1)
            dialogue_insert_payload = {'npc_a': npc_a_id, 'npc_b': npc_b_id, 'start_min': current_sim_minutes_total}
            dialogue_response = await execute_supabase_query(lambda: supa.table('dialogue').insert(dialogue_insert_payload).select('id').execute())
            
            if not (dialogue_response and dialogue_response.data and len(dialogue_response.data) > 0):
                print(f"    !!!! Failed to insert dialogue row for {npc_a_name} & {npc_b_name}. Error: {getattr(dialogue_response, 'error', 'N/A')}")
                processed_indices.append(i)
                continue
            dialogue_id = dialogue_response.data[0]['id']
            print(f"    Dialogue row inserted, ID: {dialogue_id}")

            # Retrieve memories for dialogue context (Step 5.3.1)
            # For simplicity, get memories for both and combine, or focus on one if too complex for prompt
            mem_a = await retrieve_memories(npc_a_id, trigger_event, "dialogue", current_sim_minutes_total)
            mem_b = await retrieve_memories(npc_b_id, trigger_event, "dialogue", current_sim_minutes_total)
            combined_memories = f"Memories for {npc_a_name}:\n{mem_a}\n\nMemories for {npc_b_name}:\n{mem_b}"

            # Call LLM for dialogue (Step 5.3.2)
            dialogue_system_prompt = DIALOGUE_SYSTEM_PROMPT_TEMPLATE.format(num_turns=dialogue_turns * 2) # num_turns is total lines
            dialogue_user_prompt = DIALOGUE_USER_PROMPT_TEMPLATE.format(
                npc_a_name=npc_a_name, npc_a_traits=format_traits(npc_a_traits),
                npc_b_name=npc_b_name, npc_b_traits=format_traits(npc_b_traits),
                trigger_event=trigger_event, retrieved_memories=combined_memories
            )
            raw_dialogue_text = call_llm(dialogue_system_prompt, dialogue_user_prompt, max_tokens=400) # Max tokens for dialogue

            if raw_dialogue_text:
                print(f"    Raw dialogue:\n{raw_dialogue_text}")
                # Parse and store turns/memories (Step 5.3.3, 5.3.4)
                lines = raw_dialogue_text.strip().split('\n')
                current_speaker_id = npc_a_id # Playbook: dialogue starts with npc_a_name
                current_speaker_name = npc_a_name
                other_speaker_id = npc_b_id

                for turn_text in lines:
                    speaker_match_a = re.match(f"^{re.escape(npc_a_name)}:\s*(.+)", turn_text, re.IGNORECASE)
                    speaker_match_b = re.match(f"^{re.escape(npc_b_name)}:\s*(.+)", turn_text, re.IGNORECASE)
                    
                    parsed_utterance = None
                    if speaker_match_a:
                        current_speaker_id = npc_a_id
                        parsed_utterance = speaker_match_a.group(1).strip()
                    elif speaker_match_b:
                        current_speaker_id = npc_b_id
                        parsed_utterance = speaker_match_b.group(1).strip()
                    else: # Line doesn't match expected format, try to assign based on alternation or skip
                        # For simplicity, if format is wrong, we might just log and skip this line
                        print(f"      Warning: Could not parse speaker from dialogue line: '{turn_text}'")
                        parsed_utterance = turn_text # Or skip this turn by `continue`
                        # If we use parsed_utterance, need to decide who spoke it if not clear.
                        # Let's assume it continues the current_speaker_id for this turn for simplicity if unparsed
                        if not parsed_utterance.strip(): continue

                    if not parsed_utterance: continue

                    # Insert DialogueTurn
                    turn_payload = {'dialogue_id': dialogue_id, 'speaker_id': current_speaker_id, 'sim_min': current_sim_minutes_total, 'text': parsed_utterance}
                    await execute_supabase_query(lambda: supa.table('dialogue_turn').insert(turn_payload).execute())
                    
                    # Insert Memory for this utterance
                    mem_content = f"{npc_a_name if current_speaker_id == npc_a_id else npc_b_name} said: \"{parsed_utterance}\" during encounter about {trigger_event[:30]}..."
                    utterance_embedding = await get_embedding(mem_content)
                    if utterance_embedding:
                        mem_payload = {'npc_id': current_speaker_id, 'sim_min': current_sim_minutes_total, 'kind': 'obs', 'content': mem_content, 'importance': 2, 'embedding': utterance_embedding}
                        await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload).execute())
                        # Also log for the other participant as an observation
                        other_participant_id = npc_b_id if current_speaker_id == npc_a_id else npc_a_id
                        mem_payload_other = {'npc_id': other_participant_id, 'sim_min': current_sim_minutes_total, 'kind': 'obs', 'content': mem_content, 'importance': 2, 'embedding': utterance_embedding} # Re-use embedding
                        await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_other).execute())
                    
                    # Simple alternation for next speaker (if LLM doesn't provide clear speaker tags always)
                    # current_speaker_id = other_speaker_id 
                    # current_speaker_name = npc_b_name if current_speaker_id == npc_b_id else npc_a_name
                    # other_speaker_id = npc_a_id if current_speaker_id == npc_b_id else npc_b_id
                
                # Update dialogue.end_min (Step 5.2.5)
                await execute_supabase_query(lambda: supa.table('dialogue').update({'end_min': current_sim_minutes_total}).eq('id', dialogue_id).execute())
                print(f"    Dialogue ID {dialogue_id} ended and recorded.")

                # Set cooldowns for both NPCs
                npc_dialogue_cooldown_until[npc_a_id] = current_sim_minutes_total + DIALOGUE_COOLDOWN_MINUTES
                npc_dialogue_cooldown_until[npc_b_id] = current_sim_minutes_total + DIALOGUE_COOLDOWN_MINUTES
                print(f"    NPCs {npc_a_name} & {npc_b_name} on dialogue cooldown until sim_min {npc_dialogue_cooldown_until[npc_a_id]}.")

                # Step 5.4 Post-Dialogue Behaviour (30% chance to replan)
                # Replan for NPC A
                if random.random() < 0.30:
                    print(f"    {npc_a_name} is replanning their day after dialogue.")
                    # We need the current day number. fetch it or pass it into process_pending_dialogues.
                    # Let's assume current_day is available or fetched if needed by run_daily_planning.
                    # run_daily_planning expects (day_number, current_total_sim_minutes_for_context)
                    # The current_day needs to be the *actual current day* of the simulation.
                    time_data = await get_current_sim_time_and_day() # Refetch to be sure
                    day_for_replan = time_data["day"]
                    await run_daily_planning(day_for_replan, current_sim_minutes_total) 
                
                # Replan for NPC B
                if random.random() < 0.30:
                    print(f"    {npc_b_name} is replanning their day after dialogue.")
                    time_data = await get_current_sim_time_and_day() # Refetch to be sure
                    day_for_replan = time_data["day"]
                    await run_daily_planning(day_for_replan, current_sim_minutes_total)

            else:
                print(f"  Dialogue NOT initiated between {npc_a_name} and {npc_b_name} (Chance: {initiation_chance:.2f}, Rolled: {1.0 - initiation_chance:.2f})")
        
        processed_indices.append(i) # Mark as processed whether dialogue happened or not
    
    # Remove processed requests from pending_dialogue_requests (in reverse order of index to avoid shifting issues)
    for index in sorted(processed_indices, reverse=True):
        pending_dialogue_requests.pop(index)

async def update_npc_actions_and_state(all_npcs_current_data: List[Dict], current_sim_minutes_total: int, actual_current_day: int, new_sim_min_of_day: int, all_areas_data: List[Dict]):
    print(f"DEBUG: update_npc_actions_and_state for Day {actual_current_day}, Time {new_sim_min_of_day // 60:02d}:{new_sim_min_of_day % 60:02d} (Total: {current_sim_minutes_total})")
    if not all_npcs_current_data: return

    # Get all active action definitions once for emoji/title lookup
    action_defs_res = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, emoji').execute())
    action_defs_map = {ad['id']: {'title': ad['title'], 'emoji': ad['emoji']} for ad in (action_defs_res.data or [])}

    for npc_snapshot in all_npcs_current_data: # Use the snapshot passed in, avoid re-fetching npc table repeatedly here
        npc_id = npc_snapshot['id']
        npc_name = npc_snapshot.get('name', 'UnknownNPC')
        current_action_instance_id = npc_snapshot.get('current_action_id')
        current_position_data = npc_snapshot.get('spawn') # spawn field holds current position

        action_just_completed = False

        # 1. Check completion of current action
        if current_action_instance_id:
            action_instance_res = await execute_supabase_query(lambda: supa.table('action_instance').select('start_min, duration_min, status, def_id, object_id').eq('id', current_action_instance_id).maybe_single().execute())
            if action_instance_res and action_instance_res.data:
                act_inst = action_instance_res.data
                # action_start_min_of_day is from 0-1439. current_sim_minutes_total is absolute.
                # If an action spans midnight, this simple check might be insufficient.
                # For now, assume actions are within a single day for start_min comparison.
                # A robust way: store absolute start time in action_instance, or calculate it carefully.
                # For this iteration: let's assume start_min in DB is relative to the day the action was planned for.
                # We need the day the action instance BELONGS to if it can span days.
                # Simpler: assume current_sim_minutes_total compared to start_min + duration if start_min was absolute.
                # If start_min is relative to its planned day, and action is for *today* (actual_current_day):
                action_planned_day_start_abs = (actual_current_day - 1) * SIM_DAY_MINUTES
                action_instance_start_abs = action_planned_day_start_abs + act_inst['start_min']

                if act_inst['status'] == 'active' and (current_sim_minutes_total >= action_instance_start_abs + act_inst['duration_min']):
                    print(f"    ACTION COMPLETED: {npc_name} finished action {current_action_instance_id}.")
                    await execute_supabase_query(lambda: supa.table('action_instance').update({'status': 'done'}).eq('id', current_action_instance_id).execute())
                    await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).eq('id', npc_id).execute())
                    current_action_instance_id = None 
                    action_just_completed = True
            else:
                print(f"    WARNING: NPC {npc_name} had current_action_id {current_action_instance_id} but instance not found. Clearing.")
                await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': None}).eq('id', npc_id).execute())
                current_action_instance_id = None
                action_just_completed = True # Treat as if an action just finished

        # 2. If no current action OR an action just completed, find and start next scheduled action for *today*
        if not current_action_instance_id:
            print(f"    Seeking next action for {npc_name} for Day {actual_current_day} at time {new_sim_min_of_day}.")
            plan_response_obj = await execute_supabase_query(lambda: supa.table('plan').select('actions').eq('npc_id', npc_id).eq('sim_day', actual_current_day).maybe_single().execute())
            
            if plan_response_obj and plan_response_obj.data and plan_response_obj.data.get('actions'):
                action_instance_ids_in_plan = plan_response_obj.data['actions']
                next_action_to_start = None
                if action_instance_ids_in_plan:
                    # Fetch all action instances for this plan, order by start_min ascending
                    action_instances_res = await execute_supabase_query(
                        lambda: supa.table('action_instance')
                        .select('id, start_min, status, def_id, object_id')
                        .in_('id', action_instance_ids_in_plan)
                        .order('start_min') # Defaults to ascending, remove asc=True
                        .execute()
                    )
                    print(f"        [UPDATE_NPC] {npc_name}: Fetched action instances: {action_instances_res.data}")
                    if action_instances_res and action_instances_res.data:
                        for inst in action_instances_res.data:
                            print(f"          [UPDATE_NPC] {npc_name}: Checking instance {inst['id']} (status: {inst['status']}, start_min: {inst['start_min']}) against current day_min: {new_sim_min_of_day}")
                            if inst['status'] == 'queued' and new_sim_min_of_day >= inst['start_min']:
                                next_action_to_start = inst
                                print(f"            [UPDATE_NPC] {npc_name}: MATCH! Will start: {inst['id']}")
                                break 
                
                if next_action_to_start:
                    new_action_instance_id = next_action_to_start['id']
                    new_action_def_id = next_action_to_start.get('def_id')
                    object_id_for_new_action = next_action_to_start.get('object_id')
                    action_details = action_defs_map.get(new_action_def_id, {'title': 'Unknown Action', 'emoji': '❓'})
                    action_title_log = action_details['title']
                    action_emoji_log = action_details['emoji']

                    print(f"    ACTION START: {npc_name} starting '{action_title_log}' ({new_action_instance_id}). Obj: {object_id_for_new_action}")
                    await execute_supabase_query(lambda: supa.table('action_instance').update({'status': 'active'}).eq('id', new_action_instance_id).execute())
                    
                    new_position_payload = None
                    if object_id_for_new_action:
                        obj_res = await execute_supabase_query(lambda: supa.table('object').select('pos, area_id').eq('id', object_id_for_new_action).maybe_single().execute())
                        if obj_res and obj_res.data and obj_res.data.get('pos') and obj_res.data.get('area_id'):
                            new_position_payload = {'x': obj_res.data['pos'].get('x'), 'y': obj_res.data['pos'].get('y'), 'areaId': obj_res.data['area_id']}
                            print(f"      -> Moving {npc_name} to object {object_id_for_new_action} at {new_position_payload}")
                    
                    npc_update_payload = {'current_action_id': new_action_instance_id}
                    if new_position_payload: npc_update_payload['spawn'] = new_position_payload
                    await execute_supabase_query(lambda: supa.table('npc').update(npc_update_payload).eq('id', npc_id).execute())
                    
                    await broadcast_ws_message("action_start", {"npc_name": npc_name, "action_title": action_title_log, "emoji": action_emoji_log, "sim_time": new_sim_min_of_day, "day": actual_current_day})
                    current_action_instance_id = new_action_instance_id # Ensure this is updated for the current tick
                    is_idle = False # No longer idle for this tick if an action started
            # else: # No plan for today
            #     is_idle = True # Continue to idle wander if no plan

        # 3. If still effectively idle, consider random movement
        if (not current_action_instance_id or (action_defs_map.get( (await execute_supabase_query(lambda: supa.table('action_instance').select('def_id').eq('id', current_action_instance_id).maybe_single().execute())).data.get('def_id') if current_action_instance_id and (await execute_supabase_query(lambda: supa.table('action_instance').select('def_id').eq('id', current_action_instance_id).maybe_single().execute())).data else None, {}).get('title') == 'Idle')) \
            and current_position_data and current_position_data.get('areaId') and all_areas_data:
            if random.random() < 0.25: # Chance for idle wander
                current_area_id = current_position_data['areaId']
                new_target_area_id = current_area_id
                
                # 10% chance to pick a new area for wandering, otherwise stay in current area
                if random.random() < 0.10 and len(all_areas_data) > 1:
                    possible_new_areas = [area for area in all_areas_data if area['id'] != current_area_id]
                    if possible_new_areas:
                        new_target_area_id = random.choice(possible_new_areas)['id']
                        print(f"      -> IDLE WANDER (Area Change): {npc_name} decided to wander from {current_area_id} to {new_target_area_id}")

                target_area_data = next((area for area in all_areas_data if area['id'] == new_target_area_id), None)
                
                if target_area_data and target_area_data.get('bounds'):
                    bounds = target_area_data['bounds'] 
                    padding = 10 
                    target_x = random.randint(bounds['x'] + padding, bounds['x'] + bounds['w'] - padding)
                    target_y = random.randint(bounds['y'] + padding, bounds['y'] + bounds['h'] - padding)

                    new_idle_pos_payload = {'x': target_x, 'y': target_y, 'areaId': new_target_area_id}
                    print(f"      -> IDLE WANDER: {npc_name} in {current_area_id if new_target_area_id == current_area_id else new_target_area_id} targeting {new_idle_pos_payload}")
                    await execute_supabase_query(lambda: supa.table('npc').update({'spawn': new_idle_pos_payload}).eq('id', npc_id).execute())
            # else: NPC remains at current idle position

# Modify advance_tick to pass all_areas_data to update_npc_actions_and_state
async def advance_tick():
    try:
        # print("DEBUG: advance_tick - Top of tick") # Silenced
        time_data_before_tick_res = await execute_supabase_query(lambda: supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute()) # Fetch sim_min
        env_day_res = await execute_supabase_query(lambda: supa.table('environment').select('day').eq('id', 1).maybe_single().execute()) # Fetch day
        current_sim_min_total_old = time_data_before_tick_res.data.get('sim_min', 0) if time_data_before_tick_res.data else 0
        current_day_old = env_day_res.data.get('day', 1) if env_day_res.data else 1
        print(f"Tick START: Day {current_day_old}, Min {current_sim_min_total_old}")

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
        print(f"Tick  END : Day {actual_current_day}, Min {new_sim_min_of_day} (RPC successful)")

        current_sim_minutes_total = ((actual_current_day - 1) * SIM_DAY_MINUTES) + new_sim_min_of_day
        
        # Fetch all NPCs and Areas once for this tick if needed by sub-functions
        # These are used by update_npc_actions_and_state and encounter_detection
        all_npcs_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name, current_action_id, spawn, traits').execute())
        all_npcs_data = all_npcs_res.data or []
        all_areas_res = await execute_supabase_query(lambda: supa.table('area').select('id, bounds').execute())
        all_areas_data_for_tick = all_areas_res.data or []

        await update_npc_actions_and_state(all_npcs_data, current_sim_minutes_total, actual_current_day, new_sim_min_of_day, all_areas_data_for_tick)

        if new_sim_min_of_day < settings.TICK_SIM_MIN: # True at start of day (00:00 to 00:14 for TICK_SIM_MIN=15)
            if actual_current_day > 1: # Reflection for previous day
                day_that_just_ended = actual_current_day - 1
                reflection_context_time = ((day_that_just_ended - 1) * SIM_DAY_MINUTES) + (SIM_DAY_MINUTES - 1) # Effective end of day
                await run_nightly_reflection(day_that_just_ended, reflection_context_time)
            # Planning for current new day
            await run_daily_planning(actual_current_day, current_sim_minutes_total) 
        
        await process_pending_dialogues(current_sim_minutes_total)
        await spawn_random_challenge(current_sim_minutes_total, actual_current_day)
        
        # Observation Logging (simplified log for now)
        # print(f"  Observation logging for Day {actual_current_day} - {new_sim_min_of_day // 60:02d}:{new_sim_min_of_day % 60:02d}")

        # 5. WebSocket broadcast
        await broadcast_ws_message("tick_update", {'new_sim_min': new_sim_min_of_day, 'new_day': actual_current_day})
    except Exception as e_adv_tick:
        print(f"CRITICAL ERROR in advance_tick: {e_adv_tick}")
        import traceback; traceback.print_exc()

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
        else:
            # Check if there was a Postgrest error object, otherwise assume no data means failure to get ID
            error_info = "No data returned from insert"
            if hasattr(event_response_obj, 'error') and event_response_obj.error: # Should not happen if APIError is raised
                error_info = event_response_obj.error
            elif not (event_response_obj and event_response_obj.data): # If no data and no explicit error attribute
                error_info = f"Insert call did not return data. Status: {getattr(event_response_obj, 'status_code', 'N/A')}"

            print(f"  !!!! Failed to insert sim_event for {challenge['code']} or get ID. Details: {error_info}")

# Modify _loop to call spawn_random_challenge
async def _loop():
    print("Scheduler _loop STARTED")
    loop_count = 0
    while True:
        loop_count += 1
        # print(f"DEBUG: scheduler._loop() - Iteration {loop_count} - Top of while True") # Can be too noisy
        try:
            await asyncio.sleep(settings.TICK_REAL_SEC)
            # print(f"DEBUG: scheduler._loop() - Iteration {loop_count} - Woke from sleep, calling advance_tick.")
            await advance_tick()
            # print(f"DEBUG: scheduler._loop() - Iteration {loop_count} - advance_tick completed.")

            # Periodic NPC Action Log
            if loop_count % NPC_ACTION_LOG_INTERVAL == 0:
                print(f"--- NPC Status Update (Tick {loop_count}) ---")
                npc_statuses_for_frontend = [] # Collect statuses for a single WS message
                try:
                    npcs_status_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name, current_action_id').execute()) # Added id
                    if npcs_status_res and npcs_status_res.data:
                        for npc_stat in npcs_status_res.data:
                            action_title = "Idle/None"
                            npc_name_log = npc_stat.get('name', 'Unknown')
                            current_action_id_log = npc_stat.get('current_action_id')
                            emoji_log = "🧍"

                            if current_action_id_log:
                                action_inst_res = await execute_supabase_query(lambda: supa.table('action_instance').select('def_id').eq('id', current_action_id_log).maybe_single().execute())
                                if action_inst_res and action_inst_res.data and action_inst_res.data.get('def_id'):
                                    action_def_id_log = action_inst_res.data['def_id']
                                    action_def_details = action_defs_map.get(action_def_id_log) # Use pre-fetched action_defs_map if available and passed to _loop or advance_tick context
                                    # For simplicity, re-fetch here or ensure action_defs_map is accessible
                                    if not action_defs_map: # Fallback if map not available (should be passed or global)
                                        action_defs_res_temp = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, emoji').execute())
                                        action_defs_map_temp = {ad['id']: {'title': ad['title'], 'emoji': ad['emoji']} for ad in (action_defs_res_temp.data or [])}
                                    else: action_defs_map_temp = action_defs_map # Use existing if passed
                                    
                                    if action_def_id_log in action_defs_map_temp:
                                        action_title = action_defs_map_temp[action_def_id_log]['title']
                                        emoji_log = action_defs_map_temp[action_def_id_log]['emoji']
                            
                            log_line = f"{emoji_log} {npc_name_log}: {action_title}"
                            print(f"    {log_line} (ID: {current_action_id_log})")
                            npc_statuses_for_frontend.append(log_line)
                    else:
                        print("    Could not fetch NPC statuses for periodic log.")
                    if npc_statuses_for_frontend:
                        # Get current time for this log message
                        time_data = await get_current_sim_time_and_day()
                        await broadcast_ws_message("npc_status_summary", {"day": time_data['day'], "sim_min_of_day": time_data['sim_min'], "statuses": npc_statuses_for_frontend})
                except Exception as e_status_log:
                    print(f"    Error during periodic NPC status log: {e_status_log}")
                print("-------------------------------------")

        except Exception as e_loop:
            print(f"CRITICAL ERROR IN _loop: {e_loop}") # Changed from DEBUG to CRITICAL
            import traceback; traceback.print_exc()
            break

def start_loop():
    print("Scheduler start_loop CALLED")
    asyncio.create_task(_loop())

def register_ws(ws: Any):
    _ws_clients.append(ws)

def unregister_ws(ws: Any):
    if ws in _ws_clients:
        _ws_clients.remove(ws)

# Helper function to broadcast WebSocket messages (add this at module level in scheduler.py)
async def broadcast_ws_message(message_type: str, data: Dict):
    typed_payload = {"type": message_type, "data": data}
    # print(f"Broadcasting WS: {json.dumps(typed_payload)}") # Optional: for deep debugging
    active_clients_after_send = []
    for ws in _ws_clients:
        if ws:
            try: 
                await ws.send_text(json.dumps(typed_payload))
                active_clients_after_send.append(ws)
            except Exception as e: 
                print(f"Error sending WS message ({message_type}) to client {ws}: {e} - Removing client.")
        else:
            print(f"Found a None WebSocket object in _ws_clients during {message_type} broadcast")
    _ws_clients[:] = active_clients_after_send
