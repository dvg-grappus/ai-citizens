import asyncio
from supabase import create_client, Client
from typing import Optional, List, Dict # Ensure all needed types are imported
from .config import get_settings # Use relative import
import random
from .models import NPCUIDetailData, ActionInfo, ReflectionInfo, MemoryEvent # Import new models
from postgrest.exceptions import APIError # Add APIError
import httpx # ADD HTTPOX IMPORT FOR EXCEPTION HANDLING
import time # ADD TIME IMPORT FOR SLEEP

settings = get_settings()

supa: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

# --- Semaphore and DB Execution Helper MOVED HERE ---
MAX_CONCURRENT_DB_OPS = 5 
db_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_OPS)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5

# Define a set of httpx exceptions that might be worth retrying
RETRYABLE_HTTPX_EXCEPTIONS = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.TimeoutException, # Includes ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout
    httpx.NetworkError # Generic network error
)

async def execute_supabase_query(query_executable_lambda):
    """Helper to run a Supabase query method (passed as a lambda) with semaphore and retries."""
    last_exception = None
    for attempt in range(MAX_RETRIES):
        async with db_semaphore:
            try:
                response = await asyncio.to_thread(query_executable_lambda)
                return response
            except APIError as e:
                if str(e.code) == "204": 
                    class EmptyResponse:
                        def __init__(self):
                            self.data = None; self.error = None; self.status_code = 204; self.count = None
                    return EmptyResponse()
                else:
                    print(f"Supabase APIError in services.execute_supabase_query (Code: {e.code}, Attempt: {attempt + 1}/{MAX_RETRIES}): {e.message}")
                    last_exception = e
                    # Decide if this specific APIError is retryable, e.g., based on code or message
                    # For now, assume most APIErrors are not transient unless specifically handled
                    if attempt == MAX_RETRIES - 1: raise
                    # If retryable, let it fall through to the sleep logic, otherwise re-raise immediately
                    # For now, we'll just re-raise non-204 APIErrors without retry unless they are wrapped by an httpx error.
                    # This part might need refinement based on observed APIError codes that are transient.
                    raise # Re-raise APIError if not a 204, no retry for these by default yet.
            
            except RETRYABLE_HTTPX_EXCEPTIONS as e_httpx:
                print(f"Supabase query failed with retryable HTTPX error (Attempt {attempt + 1}/{MAX_RETRIES}): {type(e_httpx).__name__} - {e_httpx}")
                last_exception = e_httpx
                if attempt < MAX_RETRIES - 1:
                    backoff_time = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    print(f"Retrying in {backoff_time:.2f} seconds...")
                    await asyncio.sleep(backoff_time) # Use asyncio.sleep for async code
                else:
                    print(f"Max retries reached for HTTPX error.")
                    raise # Re-raise the last httpx exception
            
            except Exception as e_generic:
                print(f"Supabase Generic Exception in services.execute_supabase_query (Attempt: {attempt + 1}/{MAX_RETRIES}): {type(e_generic).__name__} - {e_generic}")
                last_exception = e_generic
                # For truly generic exceptions, usually not safe to retry unless known to be transient.
                # If the generic exception was caused by an httpx.ReadError [Errno 35], our RETRYABLE_HTTPX_EXCEPTIONS should catch it.
                # If it's something else, re-raise immediately.
                raise # Re-raise generic exception immediately

    # This part should ideally not be reached if exceptions are re-raised properly in the loop
    if last_exception:
        print("Raising last recorded exception after all retries failed.")
        raise last_exception
    # Fallback, though logically an error should have been raised or a response returned.
    raise Exception("execute_supabase_query finished all retries without success or explicit error.")

# --- End Semaphore and DB Execution Helper ---

# --- Core Generic Service Functions ---
async def get_npc_by_id(npc_id: str) -> Optional[Dict]:
    """Fetches an NPC by its ID."""
    try:
        response = await execute_supabase_query(lambda: supa.table('npc').select('*').eq('id', npc_id).maybe_single().execute())
        return response.data if response else None
    except Exception as e:
        print(f"Error in get_npc_by_id for {npc_id}: {e}")
        return None

async def save_npc(npc_data: Dict) -> Optional[Dict]:
    """Saves (updates) NPC data. Assumes npc_data includes 'id' and fields to update."""
    if 'id' not in npc_data:
        print("Error in save_npc: 'id' not found in npc_data")
        return None
    
    npc_id = npc_data.pop('id') # Remove id from data, use it in eq
    try:
        response = await execute_supabase_query(lambda: supa.table('npc').update(npc_data).eq('id', npc_id).execute())
        # Update typically returns a list of the updated records
        return response.data[0] if response and response.data else None 
    except Exception as e:
        print(f"Error in save_npc for {npc_id}: {e}")
        return None

async def get_object_by_id(object_id: str) -> Optional[Dict]:
    """Fetches an object by its ID."""
    try:
        response = await execute_supabase_query(lambda: supa.table('object').select('*').eq('id', object_id).maybe_single().execute())
        return response.data if response else None
    except Exception as e:
        print(f"Error in get_object_by_id for {object_id}: {e}")
        return None

async def get_area_details(area_id: str) -> Optional[Dict]:
    """Fetches area details by area ID."""
    try:
        response = await execute_supabase_query(lambda: supa.table('area').select('*').eq('id', area_id).maybe_single().execute())
        return response.data if response else None
    except Exception as e:
        print(f"Error in get_area_details for {area_id}: {e}")
        return None

async def update_npc_current_action(npc_id: str, action_id: Optional[str]) -> Optional[Dict]:
    """Updates the current_action_id for a given NPC."""
    try:
        response = await execute_supabase_query(lambda: supa.table('npc').update({'current_action_id': action_id}).eq('id', npc_id).execute())
        return response.data[0] if response and response.data else None
    except Exception as e:
        print(f"Error in update_npc_current_action for {npc_id}: {e}")
        return None

# --- End Core Generic Service Functions ---

print("DEBUG_IMPORT: services.py - supa, semaphore, execute_supabase_query DEFINED.") # DEBUG

def insert_npcs(npcs_data: list):
    # The playbook has npc.dict() in main.py, so npcs_data will be a list of dicts
    response = supa.table('npc').insert(npcs_data).execute()
    # Add error handling/response checking as good practice, though playbook is minimal
    if response.data:
        return response.data
    if hasattr(response, 'error') and response.error:
        print(f"Error inserting NPCs: {response.error}")
        # Decide how to handle error, e.g., raise exception or return error indicator
    return None

async def get_npc_ui_details(npc_id_to_fetch: str, current_day_from_env: int) -> Optional[NPCUIDetailData]:
    print(f"Fetching UI details for NPC: {npc_id_to_fetch}, Current Day: {current_day_from_env}")
    try:
        # First check if the NPC exists
        npc_info_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name').eq('id', npc_id_to_fetch).maybe_single().execute())
        if not (npc_info_res and npc_info_res.data):
            print(f"  NPC {npc_id_to_fetch} not found in npc table. This could be due to a database reseed or NPC deletion.")
            return None
        npc_name = npc_info_res.data['name']

        # Cache of area IDs to names for quick lookup
        area_cache = {}
        areas_res = await execute_supabase_query(lambda: supa.table('area').select('id, name').execute())
        if areas_res and areas_res.data:
            for area in areas_res.data:
                area_cache[area['id']] = area['name']

        # Cache of object IDs to area names
        object_to_area_cache = {}
        objects_res = await execute_supabase_query(lambda: supa.table('object').select('id, area_id').execute())
        if objects_res and objects_res.data:
            for obj in objects_res.data:
                if obj['area_id'] in area_cache:
                    object_to_area_cache[obj['id']] = area_cache[obj['area_id']]

        # Get the last completed action (for backward compatibility)
        last_completed_action_info = None
        
        # Get up to 5 completed actions
        completed_actions_list: List[ActionInfo] = []
        # Use DISTINCT ON to prevent duplicate actions with the same start_min and title
        completed_actions_res = await execute_supabase_query(lambda: supa.table('action_instance')
            .select('id, start_min, def_id(id, title), object_id, status')
            .eq('npc_id', npc_id_to_fetch)
            .eq('status', 'done')
            .order('start_min', desc=True)
            .limit(5)
            .execute())
            
        if completed_actions_res and completed_actions_res.data:
            # Process the results to filter out duplicates with the same time and title
            unique_actions = {}
            for ad in completed_actions_res.data:
                sm = ad.get('start_min')
                title = ad.get('def_id', {}).get('title', '?')
                time_key = f"{sm // 60:02d}:{sm % 60:02d}" if sm is not None else ""
                
                # Create a unique key using time and title to deduplicate
                action_key = f"{time_key}_{title}"
                
                # Skip if we already have this action
                if action_key in unique_actions:
                    continue
                    
                # Add to unique actions dictionary
                unique_actions[action_key] = ad
            
            # Now process the unique actions
            for idx, ad in enumerate(unique_actions.values()):
                sm = ad.get('start_min')
                t = f"{sm // 60:02d}:{sm % 60:02d}" if sm is not None else ""
                area_name = None
                if ad.get('object_id') and ad['object_id'] in object_to_area_cache:
                    area_name = object_to_area_cache[ad['object_id']]
                action_info = ActionInfo(
                    time=t, 
                    title=ad.get('def_id',{}).get('title','?'), 
                    status='done',
                    area_name=area_name
                )
                completed_actions_list.append(action_info)
                # Set the first one as the last_completed_action for backward compatibility
                if idx == 0:
                    last_completed_action_info = action_info

        queued_actions_list: List[ActionInfo] = []
        plan_res = await execute_supabase_query(lambda: supa.table('plan').select('actions').eq('npc_id', npc_id_to_fetch).eq('sim_day', current_day_from_env).maybe_single().execute())
        
        current_plan_summary_list: List[str] = [] # Define here for use by both queued and summary

        if plan_res and plan_res.data and plan_res.data.get('actions'):
            action_instance_ids_for_today = plan_res.data['actions']
            if action_instance_ids_for_today and len(action_instance_ids_for_today) > 0: # Check if list is not empty
                # Fetch details for all action instances in today's plan
                all_actions_in_plan_res = await execute_supabase_query(lambda: supa.table('action_instance')
                    .select('id, start_min, def_id(title), status, object_id') # Fetch object_id too for full detail if needed
                    .in_('id', action_instance_ids_for_today)
                    .order('start_min', desc=False)
                    .execute())
                
                if all_actions_in_plan_res and all_actions_in_plan_res.data:
                    for act_detail in all_actions_in_plan_res.data:
                        title = act_detail.get('def_id', {}).get('title', 'Unknown')
                        sm = act_detail.get('start_min'); 
                        time_str = f"{sm // 60:02d}:{sm % 60:02d}" if sm is not None else "??:??"
                        status_str = act_detail.get('status', 'unknown')
                        
                        # Get area name if object_id is available
                        area_name = None
                        if act_detail.get('object_id') and act_detail['object_id'] in object_to_area_cache:
                            area_name = object_to_area_cache[act_detail['object_id']]
                        
                        # Populate Current Day's Plan Summary
                        location_str = f" in {area_name}" if area_name else ""
                        current_plan_summary_list.append(f"{time_str} - {title}{location_str} ({status_str})")
                        
                        # Populate Queued Actions (up to 10)
                        if status_str == 'queued' and len(queued_actions_list) < 10:
                            queued_actions_list.append(ActionInfo(
                                time=time_str, 
                                title=title, 
                                status=status_str,
                                area_name=area_name
                            ))
        
        latest_reflection_str = None
        reflections_list: List[ReflectionInfo] = []
        memory_stream_list: List[MemoryEvent] = []
        
        # Fetch up to 50 most recent memories of all types
        all_recent_memories_res = await execute_supabase_query(lambda: supa.table('memory')
            .select('content, sim_min, kind')
            .eq('npc_id', npc_id_to_fetch)
            .order('sim_min', desc=True)
            .limit(50)
            .execute())

        if all_recent_memories_res and all_recent_memories_res.data:
            temp_reflections: List[ReflectionInfo] = []
            for memory in all_recent_memories_res.data:
                content = memory.get('content', '')
                sim_min = memory.get('sim_min')
                mem_kind = memory.get('kind', 'unknown')
                
                time_str = ""
                if sim_min is not None:
                    day_num = sim_min // 1440 + 1
                    min_of_day = sim_min % 1440
                    hour = min_of_day // 60
                    minute = min_of_day % 60
                    time_str = f"Day {day_num}, {hour:02d}:{minute:02d}"

                # Populate overall memory_stream_list
                memory_stream_list.append(MemoryEvent(
                    content=content,
                    time=time_str,
                    type=mem_kind
                ))
                
                # Populate reflections_list (up to 5) and latest_reflection_str
                if mem_kind == 'reflect':
                    reflection_info = ReflectionInfo(content=content, time=time_str)
                    temp_reflections.append(reflection_info)

            # Sort temp_reflections by time (desc based on sim_min) if not already guaranteed by query
            # The query already sorts by sim_min desc, so the first ones encountered are the latest.
            reflections_list = temp_reflections[:5] # Take the first 5 found
            if reflections_list:
                latest_reflection_str = reflections_list[0].content

        return NPCUIDetailData(
            npc_id=npc_id_to_fetch, npc_name=npc_name,
            last_completed_action=last_completed_action_info,
            completed_actions=completed_actions_list,
            queued_actions=queued_actions_list,
            latest_reflection=latest_reflection_str,
            reflections=reflections_list,
            current_plan_summary=current_plan_summary_list,
            memory_stream=memory_stream_list
        )
    except Exception as e:
        print(f"Error in get_npc_ui_details for {npc_id_to_fetch}: {e}")
        import traceback; traceback.print_exc()
        return None

# Ensure get_state also uses the local execute_supabase_query for all its direct supa calls.
async def get_state():
    try:
        npcs_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits, backstory, relationships, spawn, energy, current_action_id').execute())
        areas_res = await execute_supabase_query(lambda: supa.table('area').select('*').execute())
        sim_clock_res = await execute_supabase_query(lambda: supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute())
        environment_res = await execute_supabase_query(lambda: supa.table('environment').select('day').eq('id', 1).maybe_single().execute())
        action_defs_res = await execute_supabase_query(lambda: supa.table('action_def').select('id, emoji, title').execute())
        
        def_id_to_emoji_title = { ad['id']: {'emoji': ad.get('emoji', '❓'), 'title': ad.get('title', 'Unknown')} for ad in (action_defs_res.data or []) }
        processed_npcs = []
        if npcs_res and npcs_res.data:
            for npc_data in npcs_res.data:
                current_action_instance_id = npc_data.get('current_action_id')
                emoji = "🧍"; action_title_for_log = "Idle"
                if current_action_instance_id:
                    action_inst_res = await execute_supabase_query(lambda: supa.table('action_instance').select('def_id, status').eq('id', current_action_instance_id).maybe_single().execute())
                    if action_inst_res and action_inst_res.data and action_inst_res.data.get('status') == 'active':
                        action_def_id = action_inst_res.data.get('def_id')
                        if action_def_id and action_def_id in def_id_to_emoji_title:
                            emoji = def_id_to_emoji_title[action_def_id]['emoji']
                processed_npcs.append({**npc_data, 'x': npc_data.get('spawn', {}).get('x'), 'y': npc_data.get('spawn', {}).get('y'), 'emoji': emoji })
        
        return {
            "npcs": processed_npcs, "areas": (areas_res.data if areas_res else []),
            "sim_clock": (sim_clock_res.data if sim_clock_res else {"sim_min": 0}), 
            "environment": (environment_res.data if environment_res else {"day": 1})
        }
    except Exception as e:
        print(f"Error in get_state: {e}"); import traceback; traceback.print_exc()
        return {"npcs": [], "areas": [], "sim_clock": {"sim_min": 0}, "environment": {"day": 1}}
