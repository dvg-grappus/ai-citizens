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

SIM_DAY_MINUTES = 24 * 60

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


async def run_replanning(npc_id: str, event_info: Dict, current_sim_min: int) -> None:
    """Replan the remainder of the day for a single NPC based on an event."""
    npc_name_for_logging = f"NPC ID {npc_id}" 
    try:
        original_event_description = event_info.get("original_description", event_info.get("description", "Unknown event"))
        print(f"REPLANNING: Initiated for {npc_name_for_logging} due to event: {original_event_description}")

        npc_res = await execute_supabase_query(
            lambda: supa.table("npc")
            .select("name, traits")
            .eq("id", npc_id)
            .maybe_single()
            .execute()
        )
        if not npc_res or not npc_res.data:
            print(f"REPLANNING: NPC data not found for {npc_id}. Aborting replan.")
            return

        npc_name = npc_res.data.get("name", npc_id)
        npc_name_for_logging = npc_name
        npc_traits = npc_res.data.get("traits", [])
        print(f"REPLANNING: Fetched NPC details for {npc_name}.")

        # Fetch all available action definitions to guide the LLM
        all_action_defs_response = await execute_supabase_query(lambda: supa.table('action_def').select('id, title, base_minutes').execute())
        if not (all_action_defs_response and all_action_defs_response.data):
            print(f"REPLANNING: Could not fetch action definitions for {npc_name}. Aborting replan.")
            return
        action_defs_data = all_action_defs_response.data
        # For matching LLM output to action_def IDs later
        defs_by_id = {d["id"]: d for d in action_defs_data}
        # For providing LLM with a list of valid action titles
        valid_action_titles = [ad['title'] for ad in action_defs_data if ad.get('title')]
        if not valid_action_titles:
            print(f"REPLANNING: No valid action titles found in action_def table for {npc_name}. Aborting replan.")
            return
        valid_actions_list_str = ", ".join(f'\"{title}\"' for title in valid_action_titles)

        current_day = (current_sim_min // SIM_DAY_MINUTES) + 1
        sim_min_of_day = current_sim_min % SIM_DAY_MINUTES

        plan_res = await execute_supabase_query(
            lambda: supa.table("plan")
            .select("id, actions")
            .eq("npc_id", npc_id)
            .eq("sim_day", current_day)
            .maybe_single()
            .execute()
        )
        if not plan_res or not plan_res.data:
            print(f"REPLANNING: No existing plan found for {npc_name} for Day {current_day}. Aborting replan.")
            return

        plan_id = plan_res.data["id"]
        existing_action_ids = plan_res.data.get("actions") or []

        action_instances_res = None
        if existing_action_ids:
            action_instances_res = await execute_supabase_query(
                lambda: supa.table("action_instance")
                .select("id, def_id, start_min, status")
                .in_("id", existing_action_ids)
                .order("start_min")
                .execute()
            )

        keep_action_ids = []
        remaining_action_lines = []
        if action_instances_res and action_instances_res.data:
            for inst in action_instances_res.data:
                if inst["start_min"] >= sim_min_of_day and inst["status"] != "done":
                    title = defs_by_id.get(inst["def_id"], {}).get("title", "?")
                    remaining_action_lines.append(
                        f"{inst['start_min'] // 60:02d}:{inst['start_min'] % 60:02d} - {title}"
                    )
                else:
                    keep_action_ids.append(inst["id"])

        remaining_plan_desc = "; ".join(remaining_action_lines) if remaining_action_lines else "None"
        print(f"REPLANNING: For {npc_name}, current time {sim_min_of_day // 60:02d}:{sim_min_of_day % 60:02d}. Remaining plan: [{remaining_plan_desc}]")

        decision_system = f"You control NPC {npc_name}."
        decision_user = (
            f"Current time: {sim_min_of_day // 60:02d}:{sim_min_of_day % 60:02d}.\\n"
            f"Upcoming plan: {remaining_plan_desc}.\\n"
            f"Event: {original_event_description}.\\n"
            "Should you create a new plan for the rest of the day? Answer Yes or No."
        )

        print(f"REPLANNING: Asking LLM if {npc_name} should replan. Event details: {original_event_description}")
        decision_raw = call_llm(decision_system, decision_user, max_tokens=10)

        if not decision_raw or not decision_raw.strip().lower().startswith("y"):
            print(f"REPLANNING: LLM decided NOT to replan for {npc_name}. LLM response: '{decision_raw}'. Aborting replan.")
            return
        
        print(f"REPLANNING: LLM decided YES to replan for {npc_name}. LLM response: '{decision_raw}'. Proceeding to generate new plan.")

        memory_query = original_event_description 
        retrieved = await retrieve_memories(npc_id, memory_query, "planning", current_sim_min)

        system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.format(
            name=npc_name,
            sim_date=f"Day {current_day}",
            traits_summary=format_traits(npc_traits),
        )
        user_prompt = (
            f"You must create a revised schedule starting from {sim_min_of_day // 60:02d}:{sim_min_of_day % 60:02d} because: {original_event_description}.\\n"
            f"IMPORTANT: You MUST choose actions EXCLUSIVELY from the following list of valid action titles: [{valid_actions_list_str}].\\n"
            f"Format each chosen action as HH:MM — <ACTION_TITLE>. Do not include any other text before or after the list of actions.\\n"
            f"CONTEXT:\\n{retrieved}"
        )

        print(f"REPLANNING: Calling LLM to generate new plan for {npc_name}. Context based on: '{memory_query}'. Valid actions provided: {valid_actions_list_str}")
        raw_plan_text = call_llm(system_prompt, user_prompt, max_tokens=400) # Increased max_tokens slightly for longer action list

        if not raw_plan_text:
            print(f"REPLANNING: LLM failed to generate a new plan for {npc_name}. Aborting replan.")
            return
        
        print(f"REPLANNING: LLM generated raw plan for {npc_name}:\\n{raw_plan_text}")

        new_action_ids = []
        parsed_actions_for_log = []
        # Retrieve action_defs_map_title_to_id for parsing, similar to run_daily_planning
        action_defs_map_title_to_id = {ad['title']: ad['id'] for ad in action_defs_data if ad.get('title')}

        # Use splitlines() for more robust line splitting from LLM output
        for line in raw_plan_text.splitlines():
            # Simpler regex focusing on the em-dash, and ensuring spaces are handled flexibly.
            # Original: r"(?:\d+\.\s*)?(\d{2}):(\d{2})\s*[-—–]\s*(.+)"
            match = re.fullmatch(r"(?:\d+\.\s*)?(\d{2}):(\d{2})\s*—\s*(.+)", line.strip())
            if not match:
                # Add a log for lines that don't match the expected HH:MM - Action format
                if line.strip(): # Only log non-empty, non-matching lines
                    print(f"      REPLANNING Debug ({npc_name}): Skipping unparseable line: '{line.strip()}'")
                continue
            hh, mm, title_raw = match.groups()
            action_title_from_llm = title_raw.strip()
            # Attempt to strip leading/trailing quotes that LLM might have included from the prompt examples
            action_title_cleaned = action_title_from_llm.strip('"').strip("'")
            
            action_def_id = action_defs_map_title_to_id.get(action_title_cleaned) 

            if not action_def_id:
                # Log both the raw and cleaned versions for debugging
                print(f"      REPLANNING Warning ({npc_name}): Action title '{action_title_cleaned}' (raw: '{action_title_from_llm}') not found in action_def_map or is invalid. Skipping.")
                continue
            
            # Get duration from the initially fetched defs_by_id or action_defs_data
            # We need a map from ID to duration if not already present
            action_defs_map_id_to_duration = {ad['id']: ad.get('base_minutes', 30) for ad in action_defs_data if ad.get('id')}
            duration_min = action_defs_map_id_to_duration.get(action_def_id, 30)
            
            start_min = int(hh) * 60 + int(mm)
            if start_min < sim_min_of_day:
                print(f"      REPLANNING Warning ({npc_name}): Action '{action_title_cleaned}' at {hh}:{mm} is before current time. Skipping.")
                continue
            
            # Object ID assignment logic (simplified example, adapt from run_daily_planning if complex objects are needed for replanned actions)
            object_id_for_action = None 
            # Example: if action_title == "Work": find PC object_id
            # This part might need to be more robust if replanned actions often require specific objects

            action_payload = {
                "npc_id": npc_id,
                "def_id": action_def_id,
                "object_id": object_id_for_action, 
                "start_min": start_min,
                "duration_min": duration_min,
                "status": "queued",
            }
            insert_res = await execute_supabase_query(
                lambda: supa.table("action_instance").insert(action_payload).execute()
            )
            if insert_res and insert_res.data and len(insert_res.data) > 0:
                new_id = insert_res.data[0].get("id")
                if new_id:
                    new_action_ids.append(new_id)
                    parsed_actions_for_log.append(f"{hh}:{mm} - {action_title_cleaned}")
                else:
                    print(f"        REPLANNING: Inserted action '{action_title_cleaned}' for {npc_name} but ID not in response: {insert_res.data}")
            else:
                db_error = getattr(insert_res, 'error', None)
                print(f"        REPLANNING: Failed to insert action '{action_title_cleaned}' for {npc_name}. Error: {db_error}. Data: {insert_res.data}")

        if new_action_ids:
            print(f"REPLANNING: Successfully parsed {len(parsed_actions_for_log)} new actions for {npc_name}.")
            if remaining_action_lines: 
                actions_to_delete = [inst_id for inst_id in existing_action_ids if inst_id not in keep_action_ids]
                if actions_to_delete:
                    print(f"REPLANNING: Deleting {len(actions_to_delete)} old actions for {npc_name}.")
                    await execute_supabase_query(
                        lambda: supa.table("action_instance")
                        .delete()
                        .in_("id", actions_to_delete)
                        .execute()
                    )
                else:
                    print(f"REPLANNING: No old actions to delete for {npc_name} as new plan starts after previous one or previous was empty.")

            updated_ids = keep_action_ids + new_action_ids
            await execute_supabase_query(
                lambda: supa.table("plan")
                .update({"actions": updated_ids})
                .eq("id", plan_id)
                .execute()
            )

            replan_reason_display = "[Unspecified Event]"
            event_source = event_info.get("source")

            if event_source == "dialogue":
                partner_name = event_info.get("partner_name", "Unknown")
                replan_reason_display = f"[Dialogue with {partner_name}]"
            elif event_source == "challenge":
                challenge_code = event_info.get("challenge_code", "Unknown")
                replan_reason_display = f"[Challenge: {challenge_code}]"
            elif event_source == "user_event":
                user_event_type = event_info.get("user_event_type", "custom").lower()
                if "environment" in user_event_type or "disturbance" in user_event_type:
                    replan_reason_display = "[Environment Event]"
                else:
                    replan_reason_display = "[External User Event]"
            elif not event_source and original_event_description != "Unknown event" and original_event_description != "an unspecified event":
                 replan_reason_display = f"[Event: {original_event_description[:30]}{(len(original_event_description)>30 and '...') or ''}]"

            mem_content = (
                f"Replanned on Day {current_day} at {sim_min_of_day // 60:02d}:{sim_min_of_day % 60:02d} due to: {replan_reason_display}. "
                f"New plan: {'; '.join(parsed_actions_for_log)}"
            )
            
            emb = await get_embedding(mem_content)
            if emb:
                mem_payload = {
                    "npc_id": npc_id,
                    "sim_min": current_sim_min,
                    "kind": "replan",
                    "content": mem_content,
                    "importance": 3, 
                    "embedding": emb,
                }
                await execute_supabase_query(
                    lambda: supa.table("memory").insert(mem_payload).execute()
                )
                print(f"REPLANNING: Successfully saved 'replan' memory for {npc_name} with reason: {replan_reason_display}.")
            else:
                print(f"REPLANNING: Failed to get embedding for replan memory content for {npc_name}. 'replan' memory NOT saved.")

            await broadcast_ws_message(
                "replan_event",
                {
                    "npc_id": npc_id,
                    "npc_name": npc_name,
                    "day": current_day,
                    "sim_min_of_day": sim_min_of_day,
                    "replan_reason": replan_reason_display,
                    "original_event": original_event_description
                },
            )
            print(f"REPLANNING: Completed and broadcasted replan_event for {npc_name}.")
        else:
            print(f"REPLANNING: No valid new actions were generated for {npc_name} from LLM output. No 'replan' memory created, plan NOT updated.")

    except Exception as e:
        print(f"ERROR in run_replanning for {npc_name_for_logging}: {e}")
        traceback.print_exc()

