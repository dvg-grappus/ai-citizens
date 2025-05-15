print("DEBUG_IMPORT: Starting services.py") # DEBUG
import asyncio
from supabase import create_client, Client
from typing import Optional, List, Dict # Ensure all needed types are imported
from .config import get_settings # Use relative import
import random
from .models import NPCUIDetailData, ActionInfo # Import new models
from postgrest.exceptions import APIError # Add APIError

print("DEBUG_IMPORT: services.py - Basic imports complete. Defining supa and helpers...") # DEBUG

settings = get_settings()

supa: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

# --- Semaphore and DB Execution Helper MOVED HERE ---
MAX_CONCURRENT_DB_OPS = 5 
db_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_OPS)

async def execute_supabase_query(query_executable_lambda):
    """Helper to run a Supabase query method (passed as a lambda) with the semaphore."""
    async with db_semaphore:
        try:
            response = await asyncio.to_thread(query_executable_lambda)
            return response
        except APIError as e:
            if str(e.code) == "204": 
                # print(f"DEBUG: services.execute_supabase_query - Caught 204 No Content. Returning EmptyResponse.")
                class EmptyResponse:
                    def __init__(self):
                        self.data = None; self.error = None; self.status_code = 204; self.count = None
                return EmptyResponse()
            else:
                print(f"Supabase APIError in services.execute_supabase_query (Code: {e.code}): {e.message}")
                # Consider if all APIErrors should return a structured error response object
                # instead of re-raising, to prevent crashes in calling code if not handled there.
                # For now, re-raising non-204 APIErrors.
                raise 
        except Exception as e_generic:
            print(f"Supabase Generic Exception in services.execute_supabase_query: {e_generic}")
            raise
# --- End Semaphore and DB Execution Helper ---

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
        npc_info_res = await execute_supabase_query(lambda: supa.table('npc').select('id, name').eq('id', npc_id_to_fetch).maybe_single().execute())
        if not (npc_info_res and npc_info_res.data):
            print(f"  NPC {npc_id_to_fetch} not found for details.")
            return None
        npc_name = npc_info_res.data['name']

        last_completed_action_info = None
        last_done_res = await execute_supabase_query(lambda: supa.table('action_instance').select('start_min, def_id(title)').eq('npc_id', npc_id_to_fetch).eq('status', 'done').order('start_min', desc=True).limit(1).maybe_single().execute())
        if last_done_res and last_done_res.data:
            ad = last_done_res.data; sm = ad.get('start_min'); t = f"{sm // 60:02d}:{sm % 60:02d}" if sm is not None else ""
            last_completed_action_info = ActionInfo(time=t, title=ad.get('def_id',{}).get('title','?'), status='done')

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
                        
                        # Populate Current Day's Plan Summary
                        current_plan_summary_list.append(f"{time_str} - {title} ({status_str})")
                        
                        # Populate Queued Actions (up to 10)
                        if status_str == 'queued' and len(queued_actions_list) < 10:
                            queued_actions_list.append(ActionInfo(time=time_str, title=title, status=status_str))
        
        latest_reflection_str = None
        reflection_res = await execute_supabase_query(lambda: supa.table('memory').select('content').eq('npc_id', npc_id_to_fetch).eq('kind', 'reflect').order('sim_min', desc=True).limit(1).maybe_single().execute())
        if reflection_res and reflection_res.data: latest_reflection_str = reflection_res.data.get('content')

        return NPCUIDetailData(
            npc_id=npc_id_to_fetch, npc_name=npc_name,
            last_completed_action=last_completed_action_info,
            queued_actions=queued_actions_list,
            latest_reflection=latest_reflection_str,
            current_plan_summary=current_plan_summary_list
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
        print(f"Error in get_state V4: {e}"); import traceback; traceback.print_exc()
        return {"npcs": [], "areas": [], "sim_clock": {"sim_min": 0}, "environment": {"day": 1}}
