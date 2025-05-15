from supabase import create_client, Client
from .config import get_settings # Use relative import
import random

settings = get_settings()

supa: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

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

def get_state():
    print("Backend: get_state() called - V3 Emoji Logic")
    try:
        npcs_res = supa.table('npc').select('id, name, traits, backstory, relationships, spawn, energy, current_action_id').execute()
        areas_res = supa.table('area').select('*').execute()
        sim_clock_res = supa.table('sim_clock').select('sim_min').eq('id', 1).maybe_single().execute()
        environment_res = supa.table('environment').select('day').eq('id', 1).maybe_single().execute()
        
        action_defs_res = supa.table('action_def').select('id, emoji, title').execute()
        def_id_to_emoji_title = {adef['id']: {'emoji': adef.get('emoji', '❓'), 'title': adef.get('title', 'Unknown')} for adef in (action_defs_res.data or [])}

        processed_npcs = []
        if npcs_res.data:
            for npc_data in npcs_res.data:
                x = npc_data.get('spawn', {}).get('x')
                y = npc_data.get('spawn', {}).get('y')
                current_action_instance_id = npc_data.get('current_action_id')
                emoji = "🧍" # Default idle
                action_title_for_log = "Idle"

                if current_action_instance_id:
                    # Fetch the specific active action instance for this NPC
                    action_inst_res = supa.table('action_instance').select('def_id, status').eq('id', current_action_instance_id).maybe_single().execute()
                    if action_inst_res.data and action_inst_res.data.get('status') == 'active':
                        action_def_id = action_inst_res.data.get('def_id')
                        if action_def_id and action_def_id in def_id_to_emoji_title:
                            emoji = def_id_to_emoji_title[action_def_id]['emoji']
                            action_title_for_log = def_id_to_emoji_title[action_def_id]['title']
                        # else: print(f"DEBUG GET_STATE: Def ID {action_def_id} not in map or no emoji for {npc_data.get('name')}")
                    # else: print(f"DEBUG GET_STATE: Action instance {current_action_instance_id} not active or not found for {npc_data.get('name')}")
                
                # This log can be pushed to frontend via a special WS message if needed
                # print(f"State for {npc_data.get('name')}: Action '{action_title_for_log}', Emoji '{emoji}'") 

                processed_npcs.append({
                    **npc_data,
                    'x': x, 'y': y,
                    'emoji': emoji,
                    # 'current_action_title': action_title_for_log # Optionally pass to frontend if needed beyond emoji
                })
        
        state = {
            "npcs": processed_npcs,
            "areas": areas_res.data if areas_res.data else [],
            "sim_clock": sim_clock_res.data if sim_clock_res.data else {"sim_min": 0},
            "environment": environment_res.data if environment_res.data else {"day": 1}
        }
        return state
        
    except Exception as e:
        print(f"Error in get_state V3: {e}")
        import traceback; traceback.print_exc()
        return {
            "npcs": [], "areas": [],
            "sim_clock": {"sim_min": 0}, "environment": {"day": 1}
        }
