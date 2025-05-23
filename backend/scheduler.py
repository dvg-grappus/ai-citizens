import asyncio
import json
from typing import List, Any, Dict, Set, Optional  # Added Set and Optional
import re  # For parsing plan
from datetime import date  # For sim_date
import math  # Already there, but good to note for sqrt
import random  # For dialogue initiation chance
from postgrest.exceptions import APIError  # Import APIError

# Use relative imports for consistency and to avoid issues if backend is run as a module
from .config import get_settings
from .llm import call_llm
from .prompts import (
    PLAN_SYSTEM_PROMPT_TEMPLATE,
    PLAN_USER_PROMPT_TEMPLATE,
    REFLECTION_SYSTEM_PROMPT_TEMPLATE,
    REFLECTION_USER_PROMPT_TEMPLATE,
    DIALOGUE_SYSTEM_PROMPT_TEMPLATE,
    DIALOGUE_USER_PROMPT_TEMPLATE,
    format_traits,
)
from .memory_service import retrieve_memories, get_embedding
from .services import supa, execute_supabase_query, get_area_details
from .websocket_utils import register_ws, unregister_ws, broadcast_ws_message
from .planning_and_reflection import run_daily_planning, run_nightly_reflection
from .dialogue_service import (
    process_pending_dialogues as process_dialogues_ext,
    add_pending_dialogue_request as add_dialogue_request_ext,
    are_npcs_on_cooldown,
)
from .npc_actions import (
    update_npc_actions_and_state,
    create_area_change_observations,
    create_plan_adherence_observations,
)
from .scheduler_events import (
    spawn_random_challenge,
    create_event_observations,
)

settings = get_settings()
# _ws_clients: List[Any] = [] # Renamed _ws to _ws_clients for clarity # REMOVE THIS LINE
SIM_DAY_MINUTES = 24 * 60
MAX_CONCURRENT_DB_OPS = 5  # Tune this value
db_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_OPS)
# --- End Semaphore ---

NPC_ACTION_LOG_INTERVAL = 10  # Log NPC actions every this many ticks

# Global constants
MOVEMENT_AREA_MARGIN = 20  # NPCs should stay 20 units away from area boundaries
EXPECTED_AREA_WIDTH = 400  # Standard assumed width for an area's local coordinate space
EXPECTED_AREA_HEIGHT = (
    300  # Standard assumed height for an area's local coordinate space
)


async def get_current_sim_time_and_day() -> Dict[str, int]:
    """Fetches current sim_min from sim_clock and day from environment."""
    try:
        sim_clock_response = await execute_supabase_query(
            lambda: supa.table("sim_clock")
            .select("sim_min")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )
        environment_response = await execute_supabase_query(
            lambda: supa.table("environment")
            .select("day")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )

        sim_clock_data = sim_clock_response.data
        environment_data = environment_response.data

        current_sim_min = sim_clock_data.get("sim_min", 0) if sim_clock_data else 0
        current_day = environment_data.get("day", 1) if environment_data else 1

        return {"sim_min": current_sim_min, "day": current_day}
    except Exception as e:
        print(f"Error fetching sim time and day: {e}")
        return {"sim_min": 0, "day": 1}  # Fallback


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


async def advance_tick():
    try:
        # print("DEBUG: advance_tick - Top of tick") # Silenced
        time_data_before_tick_res = await execute_supabase_query(
            lambda: supa.table("sim_clock")
            .select("sim_min")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )  # Fetch sim_min
        env_day_res = await execute_supabase_query(
            lambda: supa.table("environment")
            .select("day")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )  # Fetch day
        current_sim_min_total_old = (
            time_data_before_tick_res.data.get("sim_min", 0)
            if time_data_before_tick_res.data
            else 0
        )
        current_day_old = env_day_res.data.get("day", 1) if env_day_res.data else 1
        # print(f"Tick START: Day {current_day_old}, Min {current_sim_min_total_old}") # REMOVE

        increment_value = settings.TICK_SIM_MIN
        rpc_params = {"increment_value": increment_value}
        time_update_response = await execute_supabase_query(
            lambda: supa.rpc("increment_sim_min", rpc_params).execute()
        )

        if not (
            time_update_response
            and time_update_response.data
            and len(time_update_response.data) > 0
        ):
            print(
                f"!!!! advance_tick - RPC increment_sim_min FAILED. Cannot proceed with tick."
            )
            return

        new_time_data = time_update_response.data[0]
        new_sim_min_of_day = new_time_data.get("new_sim_min")
        actual_current_day = new_time_data.get("new_day")

        if new_sim_min_of_day is None or actual_current_day is None:
            return  # Should have data from RPC
        # print(f"Tick  END : Day {actual_current_day}, Min {new_sim_min_of_day} (RPC successful)") # REMOVE

        current_sim_minutes_total = (
            (actual_current_day - 1) * SIM_DAY_MINUTES
        ) + new_sim_min_of_day

        # Fetch all NPCs and Areas once for this tick if needed by sub-functions
        # These are used by update_npc_actions_and_state and encounter_detection
        all_npcs_res = await execute_supabase_query(
            lambda: supa.table("npc")
            .select("id, name, current_action_id, spawn, traits, wander_probability")
            .execute()
        )
        all_npcs_data = all_npcs_res.data or []
        all_areas_res = await execute_supabase_query(
            lambda: supa.table("area").select("id, bounds").execute()
        )
        all_areas_data_for_tick = all_areas_res.data or []

        await update_npc_actions_and_state(
            all_npcs_data,
            current_sim_minutes_total,
            actual_current_day,
            new_sim_min_of_day,
            all_areas_data_for_tick,
        )

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

            npc1_id = npc1_data["id"]
            npc1_name = npc1_data.get("name", "NPC1")
            npc1_pos_data = npc1_data.get("spawn", {})
            npc1_area_id = npc1_pos_data.get("areaId")

            npc2_id = npc2_data["id"]
            npc2_name = npc2_data.get("name", "NPC2")
            npc2_pos_data = npc2_data.get("spawn", {})
            npc2_area_id = npc2_pos_data.get("areaId")

            if npc1_area_id == npc2_area_id:
                # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are in the same area: {npc1_area_id}.") # Too verbose
                distance = math.sqrt(
                    (npc1_pos_data["x"] - npc2_pos_data["x"]) ** 2
                    + (npc1_pos_data["y"] - npc2_pos_data["y"]) ** 2
                )

                if distance < 10000:  # Effectively same-area check now
                    # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are close enough (dist: {distance:.2f} < 10000).") # Too verbose

                    # ---- START NEW COOLDOWN CHECK from dialogue_service ----
                    if await are_npcs_on_cooldown(
                        npc1_id, npc2_id, current_sim_minutes_total
                    ):
                        # print(f"[DialogueCheck] NPCs {npc1_name} & {npc2_name} on cooldown (checked by scheduler). Skipping further checks.") # Optional: verbose log
                        return  # Skip to next pair if on cooldown
                    # ---- END NEW COOLDOWN CHECK ----

                    if random.random() < 0.50:
                        print(
                            f"[DialogueCheck] SUCCESS: Random chance (50%) passed for {npc1_name} and {npc2_name}. Adding dialogue request."
                        )

                        # Prepare additional arguments for add_pending_dialogue_request
                        npc1_traits = npc1_data.get("traits", [])
                        npc2_traits = npc2_data.get("traits", [])
                        area_name_for_trigger = (
                            "their current area"  # Placeholder, ideally fetch area name
                        )
                        if npc1_area_id:  # Try to get a more specific area name
                            area_details = await get_area_details(
                                npc1_area_id
                            )  # Assuming get_area_details can fetch by ID
                            if area_details and area_details.get("name"):
                                area_name_for_trigger = area_details.get("name")

                        trigger_event = f"saw {npc2_name} in {area_name_for_trigger}"  # From NPC1's perspective

                        await add_dialogue_request_ext(
                            npc_a_id=npc1_id,
                            npc_b_id=npc2_id,
                            npc_a_name=npc1_name,
                            npc_b_name=npc2_name,
                            npc_a_traits=npc1_traits,
                            npc_b_traits=npc2_traits,
                            trigger_event=trigger_event,
                            current_tick=current_sim_minutes_total,
                        )
                    else:
                        print(
                            f"[DialogueCheck] FAILED: Random chance (50%) for {npc1_name} and {npc2_name}."
                        )
                else:
                    print(
                        f"[DialogueCheck] FAILED: NPCs {npc1_name} and {npc2_name} are too far apart (dist: {distance:.2f})."
                    )
            # else:
            # print(f"[DialogueCheck] NPCs {npc1_name} and {npc2_name} are in different areas.")
        # --- End Dialogue Encounter Detection & Initiation ---

        # Process pending dialogues using the external service
        npcs_to_replan_after_dialogue = await process_dialogues_ext(
            current_sim_minutes_total
        )
        if npcs_to_replan_after_dialogue:
            print(
                f"Scheduler: {len(npcs_to_replan_after_dialogue)} NPCs need replanning after dialogues: {npcs_to_replan_after_dialogue}"
            )
            for npc_id_to_replan in npcs_to_replan_after_dialogue:
                # Check if NPC exists in all_npcs_data before attempting to replan
                if any(npc["id"] == npc_id_to_replan for npc in all_npcs_data):
                    print(
                        f"Scheduler: Triggering replan for NPC {npc_id_to_replan} due to dialogue outcome."
                    )
                    await run_daily_planning(
                        actual_current_day,
                        current_sim_minutes_total,
                        specific_npc_id=npc_id_to_replan,
                    )
                else:
                    print(
                        f"Scheduler: NPC {npc_id_to_replan} marked for replan not found in current NPC list. Skipping replan."
                    )

        # MODIFIED: Split reflection and planning into separate conditions
        # Run reflections at midnight (start of day)
        if (
            new_sim_min_of_day < settings.TICK_SIM_MIN
        ):  # True at start of day (00:00 to 00:14 for TICK_SIM_MIN=15)
            if actual_current_day > 1:  # Reflection for previous day
                day_that_just_ended = actual_current_day - 1
                reflection_context_time = (
                    (day_that_just_ended - 1) * SIM_DAY_MINUTES
                ) + (
                    SIM_DAY_MINUTES - 1
                )  # Effective end of day
                print(
                    f"Running nightly reflection at start of Day {actual_current_day}"
                )
                await run_nightly_reflection(
                    day_that_just_ended, reflection_context_time
                )

        # MODIFIED: Run planning at 5 AM (300 minutes into the day)
        # Using a range to ensure it triggers even with different tick intervals
        if 300 <= new_sim_min_of_day < (300 + settings.TICK_SIM_MIN):
            print(f"Running daily planning at 5 AM of Day {actual_current_day}")
            await run_daily_planning(actual_current_day, current_sim_minutes_total)

        # Create plan adherence observations at 12:00 and 00:00
        if new_sim_min_of_day == 720 or new_sim_min_of_day == 0:  # 12:00 or 00:00
            await create_plan_adherence_observations(
                all_npcs_data,
                current_sim_minutes_total,
                actual_current_day,
                new_sim_min_of_day,
            )

        await spawn_random_challenge(current_sim_minutes_total, actual_current_day)

        # Observation Logging (simplified log for now)
        # print(f"  Observation logging for Day {actual_current_day} - {new_sim_min_of_day // 60:02d}:{new_sim_min_of_day % 60:02d}") # REMOVE

        # 5. WebSocket broadcast
        await broadcast_ws_message(
            "tick_update",
            {"new_sim_min": new_sim_min_of_day, "new_day": actual_current_day},
        )
    except Exception as e_adv_tick:
        print(f"CRITICAL ERROR in advance_tick: {e_adv_tick}")
        import traceback

        traceback.print_exc()


# Modify _loop to call spawn_random_challenge
async def _loop():
    print("Scheduler _loop STARTED")  # KEEP
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
            print(f"CRITICAL ERROR IN _loop: {e_loop}")  # KEEP
            import traceback

            traceback.print_exc()  # KEEP
            break  # Keep break to stop a runaway error loop


def start_loop():
    print("Scheduler start_loop CALLED")
    asyncio.create_task(_loop())
