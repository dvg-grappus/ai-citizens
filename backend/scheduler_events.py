import random
from typing import Dict

from .services import supa, execute_supabase_query
from .memory_service import get_embedding
from .websocket_utils import broadcast_ws_message

RANDOM_CHALLENGE_PROBABILITY = 0.05

# Configuration of possible challenges
RANDOM_CHALLENGES = [
    {
        "code": "fire_alarm",
        "label": "Fire alarm rings",
        "effect_desc": "The fire alarm blares!",
        "duration": 30,
        "priority_action": "Evacuate",
        "metadata": {},
    },
    {
        "code": "pizza_drop",
        "label": "Free pizza in Lounge",
        "effect_desc": "A wild pizza appears in the Lounge!",
        "duration": 60,
        "priority_action": "Get Pizza",
        "metadata": {"target_area_name": "Lounge", "npc_trait_filter": "greedy"},
    },
    {
        "code": "wifi_down",
        "label": "Office Wi-Fi outage",
        "effect_desc": "The Office Wi-Fi just went down!",
        "duration": 240,
        "priority_action": "Complain about Wi-Fi",
        "metadata": {"target_area_name": "Office", "affected_action_title": "Work"},
    },
]


async def spawn_random_challenge(current_sim_minutes_total: int, current_day: int):
    if random.random() < RANDOM_CHALLENGE_PROBABILITY:
        challenge = random.choice(RANDOM_CHALLENGES)
        print(
            f"EVENT: Random challenge triggered - {challenge['label']} at Day {current_day}, SimMin {current_sim_minutes_total}"
        )

        event_start_min = current_sim_minutes_total
        event_end_min = current_sim_minutes_total + challenge["duration"]

        sim_event_payload = {
            "type": challenge["code"],
            "start_min": event_start_min,
            "end_min": event_end_min,
            "metadata": challenge["metadata"],
        }
        event_response_obj = await execute_supabase_query(
            lambda: supa.table("sim_event").insert(sim_event_payload).execute()
        )

        event_id = None
        if (
            event_response_obj
            and event_response_obj.data
            and len(event_response_obj.data) > 0
        ):
            event_id = event_response_obj.data[0].get("id")

        if event_id:
            print(
                f"  -> sim_event row inserted, ID: {event_id}. Desc: {challenge['effect_desc']}"
            )
            ws_event_data = {
                "event_code": challenge["code"],
                "description": challenge["effect_desc"],
                "tick": current_sim_minutes_total,
                "event_id": event_id,
                "day": current_day,
            }
            await broadcast_ws_message("sim_event", ws_event_data)
            affected = await create_event_observations(challenge, current_sim_minutes_total)
            if affected:
                from .planning_and_reflection import run_replanning
                for npc_id in affected:
                    # Construct new event_info for replanning after a challenge
                    event_info = {
                        "source": "challenge",
                        "challenge_code": challenge.get("code", "unknown_challenge"), # e.g., "pizza_drop"
                        "original_description": challenge.get("effect_desc", "A challenge occurred!")
                    }
                    await run_replanning(npc_id, event_info, current_sim_minutes_total)
        else:
            error_info = "No data returned from insert"
            if hasattr(event_response_obj, "error") and event_response_obj.error:
                error_info = event_response_obj.error
            elif not (event_response_obj and event_response_obj.data):
                error_info = f"Insert call did not return data. Status: {getattr(event_response_obj, 'status_code', 'N/A')}"
            print(
                f"  !!!! Failed to insert sim_event for {challenge['code']} or get ID. Details: {error_info}"
            )


async def create_event_observations(event_data: Dict, current_sim_minutes_total: int):
    """Create observation memories for NPCs based on environmental events.
    Returns a list of NPC IDs who received observations."""
    try:
        npcs_res = await execute_supabase_query(
            lambda: supa.table("npc").select("id, name, spawn").execute()
        )
        if not (npcs_res and npcs_res.data):
            return []

        target_area_name = event_data.get("metadata", {}).get("target_area_name")
        target_area_id = None

        if target_area_name:
            area_res = await execute_supabase_query(
                lambda: supa.table("area")
                .select("id")
                .eq("name", target_area_name)
                .maybe_single()
                .execute()
            )
            if area_res and area_res.data:
                target_area_id = area_res.data.get("id")

        event_desc = event_data.get(
            "effect_desc",
            f"Something happened: {event_data.get('label', 'Unknown event')}",
        )

        affected_npcs = []
        for npc in npcs_res.data:
            npc_id = npc.get("id")
            npc_area_id = npc.get("spawn", {}).get("areaId")

            if target_area_id and npc_area_id != target_area_id:
                continue

            observation_content = event_desc
            if target_area_name and npc_area_id == target_area_id:
                observation_content = f"[Environment] While in the {target_area_name}, I noticed: {event_desc}"
            else:
                observation_content = f"[Environment] {event_desc}"

            observation_embedding = await get_embedding(observation_content)
            if observation_embedding:
                mem_payload = {
                    "npc_id": npc_id,
                    "sim_min": current_sim_minutes_total,
                    "kind": "obs",
                    "content": observation_content,
                    "importance": 3,
                    "embedding": observation_embedding,
                }
                await execute_supabase_query(
                    lambda: supa.table("memory").insert(mem_payload).execute()
                )
                affected_npcs.append(npc_id)
        return affected_npcs
    except Exception as e:
        print(f"Error creating event observations: {e}")
        return []
