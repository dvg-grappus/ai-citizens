import asyncio
import re
import traceback
from typing import List, Dict, Optional, Any # Added Any for supa functions if not more specific types are available

# Imports from the 'backend' package
from .llm import call_llm
from .prompts import (
    PLAN_SYSTEM_PROMPT_TEMPLATE, PLAN_USER_PROMPT_TEMPLATE,
    REFLECTION_SYSTEM_PROMPT_TEMPLATE, REFLECTION_USER_PROMPT_TEMPLATE, format_traits
)
from .memory_service import retrieve_memories, get_embedding
from .services import supa, execute_supabase_query # supa is used directly
from .websocket_utils import broadcast_ws_message # Import from the new utils file

# It's good practice to define constants if they are specific to this module,
# or import them if they are global settings.
# For now, assuming no new constants are needed here beyond what's imported.

async def run_daily_planning(current_day: int, current_sim_minutes_total: int, specific_npc_id: Optional[str] = None):
    print(f"PLANNING: Day {current_day} (5:00 AM) {'for NPC ' + specific_npc_id if specific_npc_id else 'for ALL NPCs'}")
    try:
        if specific_npc_id:
            npcs_response_obj = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits, backstory').eq('id', specific_npc_id).execute()) # Fetch only specific NPC
        else:
            npcs_response_obj = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits, backstory').execute()) # Fetch all NPCs
        
        if not (npcs_response_obj and npcs_response_obj.data):
            print(f"PLANNING: No NPC(s) found {'with ID ' + specific_npc_id if specific_npc_id else ''}.")
            return
        npcs_data = npcs_response_obj.data if isinstance(npcs_response_obj.data, list) else [npcs_response_obj.data] 
        sim_date_str = f"Day {current_day}"
        
        all_action_defs_response = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, base_minutes').execute())
        action_defs_data = all_action_defs_response.data or []
        action_defs_map_title_to_id = {ad['title']: ad['id'] for ad in action_defs_data if ad.get('title')}
        action_defs_map_id_to_duration = {ad['id']: ad.get('base_minutes', 30) for ad in action_defs_data if ad.get('id')}

        all_objects_response = await execute_supabase_query(lambda: supa.table('object').select('id, name, area_id').execute())
        all_objects_data = all_objects_response.data or []

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
                    
                    object_id_for_action = None
                    if action_title == "Work":
                        pc_objects = [obj for obj in all_objects_data if obj.get('name') == "PC"]
                        if pc_objects: object_id_for_action = pc_objects[0]['id'] 
                    elif action_title == "Sleep":
                        bed_objects = [obj for obj in all_objects_data if obj.get('name') == "Bed"]
                        if bed_objects: object_id_for_action = bed_objects[0]['id'] 
                    elif action_title == "Brush Teeth":
                        toothbrush_objects = [obj for obj in all_objects_data if obj.get('name') == "Toothbrush"]
                        if toothbrush_objects: object_id_for_action = toothbrush_objects[0]['id']
                    elif action_title == "Watch TV":
                        tv_objects = [obj for obj in all_objects_data if obj.get('name') == "TV"]
                        if tv_objects: object_id_for_action = tv_objects[0]['id']
                    elif action_title == "Relax on Couch":
                        couch_objects = [obj for obj in all_objects_data if obj.get('name') == "Couch"]
                        if couch_objects: object_id_for_action = couch_objects[0]['id']
                    elif action_title == "Have Coffee":
                        coffee_table_objects = [obj for obj in all_objects_data if obj.get('name') == "Coffee Table"]
                        if coffee_table_objects: object_id_for_action = coffee_table_objects[0]['id']

                    action_instance_data = {
                        'npc_id': npc_id,
                        'def_id': action_def_id,
                        'object_id': object_id_for_action,
                        'start_min': action_start_sim_min_of_day,
                        'duration_min': duration_min,
                        'status': 'queued'
                    }
                    action_instance_data_list = [action_instance_data]
                    
                    def _insert_action_sync(data_list: List[Dict[str, Any]]) -> Any: # Added typing
                        return supa.table('action_instance').insert(data_list).execute()
                    insert_response_obj = await execute_supabase_query(lambda: _insert_action_sync(action_instance_data_list))

                    action_instance_id = None
                    if insert_response_obj.data and len(insert_response_obj.data) > 0:
                        action_instance_id = insert_response_obj.data[0].get('id')
                        if action_instance_id:
                            plan_action_instance_ids.append(action_instance_id)
                            parsed_actions_for_log.append(f"{hh}:{mm} - {action_title}")
                        else:
                            print(f"        !!!! Inserted '{action_title}' but ID not in response: {insert_response_obj.data}")
                    else:
                        db_error = getattr(insert_response_obj, 'error', None)
                        print(f"        !!!! Failed to insert '{action_title}'. Error: {db_error}. Data: {insert_response_obj.data}")
            
            if plan_action_instance_ids:
                print(f"    PLANNING - Successfully created plan for {npc_name} with {len(parsed_actions_for_log)} actions.")
                plan_data = {'npc_id': npc_id, 'sim_day': current_day, 'actions': plan_action_instance_ids}
                await execute_supabase_query(lambda: supa.table('plan').insert(plan_data).execute())
                
                plan_memory_content = f"Planned for {sim_date_str}: {len(parsed_actions_for_log)} actions. Details: {'; '.join(parsed_actions_for_log)}"
                plan_memory_embedding = await get_embedding(plan_memory_content)
                if plan_memory_embedding:
                    plan_memory_payload = {'npc_id': npc_id, 'sim_min': current_sim_minutes_total, 'kind': 'plan','content': plan_memory_content, 'importance': 3, 'embedding': plan_memory_embedding}
                    await execute_supabase_query(lambda: supa.table('memory').insert(plan_memory_payload).execute())

                await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "completed_planning", "day": current_day, "num_actions": len(parsed_actions_for_log)})
            else:
                print(f"    PLANNING - No valid action instances for {npc_name}, plan not created.")
                await broadcast_ws_message("planning_event", {"npc_name": npc_name, "status": "failed_planning", "day": current_day})

    except Exception as e:
        print(f"ERROR in run_daily_planning: {e}")
        traceback.print_exc()

async def run_nightly_reflection(day_being_reflected: int, current_sim_minutes_total: int):
    print(f"REFLECTION: Day {day_being_reflected} (12:00 AM Midnight) ...")
    try:
        npcs_response_obj = await execute_supabase_query(lambda: supa.table('npc').select('id, name, traits').execute())
        if not (npcs_response_obj and npcs_response_obj.data): 
            print("REFLECTION: No NPCs found.")
            return
        
        npcs_data = npcs_response_obj.data # Expecting a list from .execute()
        sim_date_str = f"Day {day_being_reflected}"

        for npc in npcs_data:
            npc_id = npc['id']; npc_name = npc['name']
            await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "started_reflection", "day": day_being_reflected})
            npc_traits_summary = format_traits(npc.get('traits', []))
            print(f"  REFLECTING for {npc_name} (ID: {npc_id})...")
            
            # The original code had a memory check here, which I'm keeping
            await execute_supabase_query(lambda: supa.table('memory')
                .select('id, kind') # Minimal select
                .eq('npc_id', npc_id)
                .eq('kind', 'obs') # Filter for observations
                .order('sim_min', desc=True) # Most recent first
                .limit(50) # Increased limit for better context for reflection
                .execute())
            
            reflection_query_text = f"Key events and main thoughts for {npc_name} on {sim_date_str}? What are 1-3 most salient high-level questions I can answer about my experiences today?"
            retrieved_memories_str = await retrieve_memories(npc_id, reflection_query_text, "reflection", current_sim_minutes_total)
            
            system_prompt = REFLECTION_SYSTEM_PROMPT_TEMPLATE.format(npc_name=npc_name, sim_date=sim_date_str)
            user_prompt = REFLECTION_USER_PROMPT_TEMPLATE.format(traits_summary=npc_traits_summary, retrieved_memories=retrieved_memories_str)
            
            raw_reflection_text = call_llm(system_prompt, user_prompt, max_tokens=500, model="gpt-4o") # Increased max_tokens for richer reflection
            
            if not raw_reflection_text:
                print(f"  ERROR: LLM returned empty or null response for {npc_name}'s reflection!")
                await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "failed_reflection_llm", "day": day_being_reflected})
                continue
            
            # Attempt to parse bullet points, allowing for variations
            reflection_points = []
            lines = raw_reflection_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue
                # More robust bullet point detection
                if re.match(r"^[•*-]\s*", line): # Matches •, *, -
                    reflection_points.append(line[re.match(r"^[•*-]\s*", line).end():].strip())
                elif re.match(r"^\d+\.\s*", line): # Matches "1. "
                     reflection_points.append(line[re.match(r"^\d+\.\s*", line).end():].strip())
                else: # If no clear bullet, treat the line as a point (might be a paragraph)
                    reflection_points.append(line)

            if not reflection_points:
                print(f"  ERROR: No reflection points could be parsed for {npc_name}. Raw text: {raw_reflection_text}")
                await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "failed_reflection_parsing", "day": day_being_reflected})
                continue

            print(f"  REFLECTION - Successfully generated {len(reflection_points)} reflection points for {npc_name}.")

            memories_to_insert = []
            for point_content in reflection_points:
                if not point_content: continue # Skip empty points

                # For reflection, let's make importance slightly higher than observations
                importance = 2 
                # Heuristic: if question mark in point, could be a question/insight, raise importance
                if '?' in point_content: importance = 3
                # Heuristic: Longer reflections might be more insightful
                if len(point_content) > 150: importance = 3 
                if len(point_content) > 250: importance = 4


                reflection_embedding = await get_embedding(point_content)
                if reflection_embedding:
                    memories_to_insert.append({
                        'npc_id': npc_id,
                        'sim_min': current_sim_minutes_total,
                        'kind': 'reflect',
                        'content': point_content,
                        'importance': importance,
                        'embedding': reflection_embedding
                    })
            
            if memories_to_insert:
                await execute_supabase_query(lambda: supa.table('memory').insert(memories_to_insert).execute())
                print(f"    -> REFLECTION - Saved {len(memories_to_insert)} reflection memories for {npc_name}.")
                await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "completed_reflection", "day": day_being_reflected, "num_reflections": len(memories_to_insert)})
            else:
                print(f"    -> REFLECTION - No valid reflection memories to save for {npc_name}.")
                await broadcast_ws_message("reflection_event", {"npc_name": npc_name, "status": "no_reflections_saved", "day": day_being_reflected})

    except Exception as e:
        print(f"ERROR in run_nightly_reflection for NPC {npc.get('name', 'UNKNOWN') if 'npc' in locals() else 'N/A'}: {e}")
        traceback.print_exc()
        if 'npc' in locals() and npc: # Check if npc is defined
             await broadcast_ws_message("reflection_event", {"npc_name": npc.get('name', 'UNKNOWN'), "status": "error_reflection", "day": day_being_reflected}) 