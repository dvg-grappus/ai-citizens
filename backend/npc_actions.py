import random
from typing import List, Dict

from .services import supa, execute_supabase_query
from .memory_service import get_embedding
from .websocket_utils import broadcast_ws_message

# Local constants replicated from scheduler
SIM_DAY_MINUTES = 24 * 60
MOVEMENT_AREA_MARGIN = 20
EXPECTED_AREA_WIDTH = 400
EXPECTED_AREA_HEIGHT = 300


async def update_npc_actions_and_state(
    all_npcs_data: List[Dict],
    current_sim_minutes_total: int,
    actual_current_day: int,
    new_sim_min_of_day: int,
    all_areas_data: List[Dict],
):
    # No debug logging here
    if not all_npcs_data:
        return

    action_defs_res = await execute_supabase_query(
        lambda: supa.table("action_def").select("id, title, emoji").execute()
    )
    action_defs_map = {
        ad["id"]: {"title": ad["title"], "emoji": ad["emoji"]}
        for ad in (action_defs_res.data or [])
    }

    for npc_snapshot in all_npcs_data:
        npc_id = npc_snapshot["id"]
        npc_name = npc_snapshot.get("name", "UnknownNPC")

        current_action_instance_id = npc_snapshot.get("current_action_id")
        current_position_data = npc_snapshot.get("spawn", {})  # Ensure spawn is a dict
        action_just_completed = False
        new_action_started_this_tick = (
            False  # Flag to track if a new action (not wander) started
        )

        # 1. Check completion of current action
        if current_action_instance_id:
            action_instance_res = await execute_supabase_query(
                lambda: supa.table("action_instance")
                .select("start_min, duration_min, status, def_id, object_id")
                .eq("id", current_action_instance_id)
                .maybe_single()
                .execute()
            )
            if action_instance_res and action_instance_res.data:
                act_inst = action_instance_res.data
                action_planned_day_start_abs = (
                    actual_current_day - 1
                ) * SIM_DAY_MINUTES
                action_instance_start_abs = (
                    action_planned_day_start_abs + act_inst["start_min"]
                )

                if act_inst["status"] == "active" and (
                    current_sim_minutes_total
                    >= action_instance_start_abs + act_inst["duration_min"]
                ):
                    await execute_supabase_query(
                        lambda: supa.table("action_instance")
                        .update({"status": "done"})
                        .eq("id", current_action_instance_id)
                        .execute()
                    )
                    await execute_supabase_query(
                        lambda: supa.table("npc")
                        .update({"current_action_id": None})
                        .eq("id", npc_id)
                        .execute()
                    )
                    current_action_instance_id = None
                    action_just_completed = True
            else:
                await execute_supabase_query(
                    lambda: supa.table("npc")
                    .update({"current_action_id": None})
                    .eq("id", npc_id)
                    .execute()
                )
                current_action_instance_id = None
                action_just_completed = True

        # 2. If no current action OR an action just completed, find and start next scheduled action for *today*
        if not current_action_instance_id:
            plan_response_obj = await execute_supabase_query(
                lambda: supa.table("plan")
                .select("actions")
                .eq("npc_id", npc_id)
                .eq("sim_day", actual_current_day)
                .maybe_single()
                .execute()
            )
            next_action_to_start = None
            if (
                plan_response_obj
                and plan_response_obj.data
                and plan_response_obj.data.get("actions")
            ):
                action_instance_ids_in_plan = plan_response_obj.data["actions"]
                if action_instance_ids_in_plan:
                    action_instances_res = await execute_supabase_query(
                        lambda: supa.table("action_instance")
                        .select("id, start_min, status, def_id, object_id")
                        .in_("id", action_instance_ids_in_plan)
                        .order("start_min")
                        .execute()
                    )
                    if action_instances_res and action_instances_res.data:
                        for inst in action_instances_res.data:
                            if (
                                inst["status"] == "queued"
                                and new_sim_min_of_day >= inst["start_min"]
                            ):
                                next_action_to_start = inst
                                break

            if next_action_to_start:
                new_action_instance_id = next_action_to_start["id"]
                new_action_def_id = next_action_to_start.get("def_id")
                object_id_for_new_action = next_action_to_start.get("object_id")
                action_details = action_defs_map.get(
                    new_action_def_id, {"title": "Unknown Action", "emoji": "❓"}
                )
                action_title_log = action_details["title"]
                action_emoji_log = action_details["emoji"]

                await execute_supabase_query(
                    lambda: supa.table("action_instance")
                    .update({"status": "active"})
                    .eq("id", new_action_instance_id)
                    .execute()
                )

                npc_update_payload = {"current_action_id": new_action_instance_id}
                action_moved_npc = False

                if object_id_for_new_action:
                    obj_res = await execute_supabase_query(
                        lambda: supa.table("object")
                        .select("area_id, name")
                        .eq("id", object_id_for_new_action)
                        .maybe_single()
                        .execute()
                    )
                    if obj_res and obj_res.data and obj_res.data.get("area_id"):
                        obj_data = obj_res.data
                        target_area_id_for_action = obj_data["area_id"]

                        effective_movable_width = (
                            EXPECTED_AREA_WIDTH - 2 * MOVEMENT_AREA_MARGIN
                        )
                        effective_movable_height = (
                            EXPECTED_AREA_HEIGHT - 2 * MOVEMENT_AREA_MARGIN
                        )

                        if effective_movable_width < 1 or effective_movable_height < 1:
                            wander_target_x = EXPECTED_AREA_WIDTH / 2
                            wander_target_y = EXPECTED_AREA_HEIGHT / 2
                        else:
                            wander_target_x = random.uniform(
                                MOVEMENT_AREA_MARGIN,
                                EXPECTED_AREA_WIDTH - MOVEMENT_AREA_MARGIN,
                            )
                            wander_target_y = random.uniform(
                                MOVEMENT_AREA_MARGIN,
                                EXPECTED_AREA_HEIGHT - MOVEMENT_AREA_MARGIN,
                            )

                        action_position_payload = {
                            "x": wander_target_x,
                            "y": wander_target_y,
                            "areaId": target_area_id_for_action,
                        }
                        npc_update_payload["spawn"] = action_position_payload
                        action_moved_npc = True

                await execute_supabase_query(
                    lambda: supa.table("npc")
                    .update(npc_update_payload)
                    .eq("id", npc_id)
                    .execute()
                )
                current_action_instance_id = new_action_instance_id
                new_action_started_this_tick = True

                if action_moved_npc:
                    before_area_id = current_position_data.get("areaId")
                    current_position_data = npc_update_payload["spawn"]
                    after_area_id = current_position_data.get("areaId")
                    if (
                        before_area_id != after_area_id
                        and before_area_id is not None
                        and after_area_id is not None
                    ):
                        await create_area_change_observations(
                            npc_id,
                            npc_name,
                            before_area_id,
                            after_area_id,
                            all_npcs_data,
                            current_sim_minutes_total,
                            actual_current_day,
                        )

                await broadcast_ws_message(
                    "action_start",
                    {
                        "npc_name": npc_name,
                        "action_title": action_title_log,
                        "emoji": action_emoji_log,
                        "sim_time": new_sim_min_of_day,
                        "day": actual_current_day,
                    },
                )
            else:
                if npc_snapshot.get("current_action_id"):
                    await execute_supabase_query(
                        lambda: supa.table("npc")
                        .update({"current_action_id": None})
                        .eq("id", npc_id)
                        .execute()
                    )
                current_action_instance_id = None

        # 3. Always-on Same-Area Wander
        perform_wander_this_tick = False

        npc_wander_probability_from_db = npc_snapshot.get("wander_probability")
        if (
            isinstance(npc_wander_probability_from_db, (float, int))
            and 0.0 <= float(npc_wander_probability_from_db) <= 1.0
        ):
            npc_specific_wander_probability = float(npc_wander_probability_from_db)
        else:
            if npc_wander_probability_from_db is not None:
                print(
                    f"[Scheduler] NPC {npc_name} has invalid wander_probability '{npc_wander_probability_from_db}'. Defaulting to 0.4."
                )
            npc_specific_wander_probability = 0.40

        if not new_action_started_this_tick or (
            new_action_started_this_tick and not action_moved_npc
        ):
            if random.random() < npc_specific_wander_probability:
                perform_wander_this_tick = True

        if perform_wander_this_tick:
            current_area_id_for_wander = current_position_data.get("areaId")
            if current_area_id_for_wander:
                effective_movable_width = EXPECTED_AREA_WIDTH - 2 * MOVEMENT_AREA_MARGIN
                effective_movable_height = (
                    EXPECTED_AREA_HEIGHT - 2 * MOVEMENT_AREA_MARGIN
                )

                if effective_movable_width < 1 or effective_movable_height < 1:
                    wander_target_x = EXPECTED_AREA_WIDTH / 2
                    wander_target_y = EXPECTED_AREA_HEIGHT / 2
                else:
                    wander_target_x = random.uniform(
                        MOVEMENT_AREA_MARGIN, EXPECTED_AREA_WIDTH - MOVEMENT_AREA_MARGIN
                    )
                    wander_target_y = random.uniform(
                        MOVEMENT_AREA_MARGIN,
                        EXPECTED_AREA_HEIGHT - MOVEMENT_AREA_MARGIN,
                    )

                current_x = current_position_data.get("x")
                current_y = current_position_data.get("y")

                if wander_target_x != current_x or wander_target_y != current_y:
                    wander_position_payload = {
                        "x": wander_target_x,
                        "y": wander_target_y,
                        "areaId": current_area_id_for_wander,
                    }
                    await execute_supabase_query(
                        lambda: supa.table("npc")
                        .update({"spawn": wander_position_payload})
                        .eq("id", npc_id)
                        .execute()
                    )
                    # current_position_data = wander_position_payload


async def create_area_change_observations(
    moving_npc_id,
    moving_npc_name,
    from_area_id,
    to_area_id,
    all_npcs_data,
    current_sim_minutes_total,
    actual_current_day,
):
    """Create observation memories when NPCs change areas or notice others in their area."""
    try:
        from_area_name = "an area"
        to_area_name = "an area"

        sim_min_of_day = current_sim_minutes_total % SIM_DAY_MINUTES

        area_res_from = await execute_supabase_query(
            lambda: supa.table("area")
            .select("name")
            .eq("id", from_area_id)
            .maybe_single()
            .execute()
        )
        if area_res_from and area_res_from.data:
            from_area_name = area_res_from.data.get("name", "an area")

        area_res_to = await execute_supabase_query(
            lambda: supa.table("area")
            .select("name")
            .eq("id", to_area_id)
            .maybe_single()
            .execute()
        )
        if area_res_to and area_res_to.data:
            to_area_name = area_res_to.data.get("name", "an area")

        npcs_in_new_area = [
            npc
            for npc in all_npcs_data
            if npc.get("spawn", {}).get("areaId") == to_area_id
            and npc["id"] != moving_npc_id
        ]

        if npcs_in_new_area:
            moving_npc_data_list = [
                n for n in all_npcs_data if n["id"] == moving_npc_id
            ]
            if moving_npc_data_list:
                moving_npc_data = moving_npc_data_list[0]
                for other_npc_in_new_area in npcs_in_new_area:
                    moving_sees_other_obs = f"[Social] I saw {other_npc_in_new_area['name']} in the {to_area_name}."
                    moving_sees_other_embedding = await get_embedding(
                        moving_sees_other_obs
                    )
                    if moving_sees_other_embedding:
                        mem_payload_mover = {
                            "npc_id": moving_npc_id,
                            "sim_min": current_sim_minutes_total,
                            "kind": "obs",
                            "content": moving_sees_other_obs,
                            "importance": 2,
                            "embedding": moving_sees_other_embedding,
                        }
                        db_response_mover = await execute_supabase_query(
                            lambda: supa.table("memory")
                            .insert(mem_payload_mover)
                            .execute()
                        )
                        if db_response_mover.data:
                            await broadcast_ws_message(
                                "social_event",
                                {
                                    "observer_npc_id": moving_npc_id,
                                    "observer_npc_name": moving_npc_name,
                                    "event_type": "saw_other_in_new_area",
                                    "target_npc_name": other_npc_in_new_area["name"],
                                    "area_name": to_area_name,
                                    "description": moving_sees_other_obs,
                                    "sim_min_of_day": sim_min_of_day,
                                    "day": actual_current_day,
                                },
                            )

                    other_sees_moving_enter_obs = (
                        f"[Social] I saw {moving_npc_name} enter the {to_area_name}."
                    )
                    other_sees_moving_enter_embedding = await get_embedding(
                        other_sees_moving_enter_obs
                    )
                    if other_sees_moving_enter_embedding:
                        mem_payload_other = {
                            "npc_id": other_npc_in_new_area["id"],
                            "sim_min": current_sim_minutes_total,
                            "kind": "obs",
                            "content": other_sees_moving_enter_obs,
                            "importance": 2,
                            "embedding": other_sees_moving_enter_embedding,
                        }
                        db_response_other = await execute_supabase_query(
                            lambda: supa.table("memory")
                            .insert(mem_payload_other)
                            .execute()
                        )
                        if db_response_other.data:
                            await broadcast_ws_message(
                                "social_event",
                                {
                                    "observer_npc_id": other_npc_in_new_area["id"],
                                    "observer_npc_name": other_npc_in_new_area["name"],
                                    "event_type": "other_saw_me_enter",
                                    "target_npc_name": moving_npc_name,
                                    "area_name": to_area_name,
                                    "description": other_sees_moving_enter_obs,
                                    "sim_min_of_day": sim_min_of_day,
                                    "day": actual_current_day,
                                },
                            )

        npcs_in_old_area = [
            npc
            for npc in all_npcs_data
            if npc.get("spawn", {}).get("areaId") == from_area_id
            and npc["id"] != moving_npc_id
        ]

        for other_npc_in_old_area in npcs_in_old_area:
            other_sees_moving_leave_obs = (
                f"[Social] I saw {moving_npc_name} leave the {from_area_name}."
            )
            other_sees_moving_leave_embedding = await get_embedding(
                other_sees_moving_leave_obs
            )
            if other_sees_moving_leave_embedding:
                mem_payload = {
                    "npc_id": other_npc_in_old_area["id"],
                    "sim_min": current_sim_minutes_total,
                    "kind": "obs",
                    "content": other_sees_moving_leave_obs,
                    "importance": 2,
                    "embedding": other_sees_moving_leave_embedding,
                }
                db_response_leave = await execute_supabase_query(
                    lambda: supa.table("memory").insert(mem_payload).execute()
                )
                if db_response_leave.data:
                    await broadcast_ws_message(
                        "social_event",
                        {
                            "observer_npc_id": other_npc_in_old_area["id"],
                            "observer_npc_name": other_npc_in_old_area["name"],
                            "event_type": "other_saw_me_leave",
                            "target_npc_name": moving_npc_name,
                            "area_name": from_area_name,
                            "description": other_sees_moving_leave_obs,
                            "sim_min_of_day": sim_min_of_day,
                            "day": actual_current_day,
                        },
                    )
    except Exception as e:
        print(f"Error creating area change observations or broadcasting: {e}")


async def create_plan_adherence_observations(
    all_npcs_data, current_sim_minutes_total, current_day, current_min_of_day
):
    """Create observations about whether NPCs are following their plans or have unexpected deviations."""
    try:
        time_label = "noon" if current_min_of_day == 720 else "midnight"

        for npc in all_npcs_data:
            npc_id = npc.get("id")
            npc_name = npc.get("name", "Unknown")
            current_action_id = npc.get("current_action_id")

            plan_res = await execute_supabase_query(
                lambda: supa.table("plan")
                .select("actions")
                .eq("npc_id", npc_id)
                .eq("sim_day", current_day)
                .maybe_single()
                .execute()
            )

            if not (plan_res and plan_res.data and plan_res.data.get("actions")):
                observation_content = f"[Periodic] At {time_label}, I realized I don't have a plan for today."
                importance = 2
            else:
                plan_action_ids = plan_res.data.get("actions", [])
                current_action_title = "nothing scheduled"
                scheduled_action_found = False

                if plan_action_ids:
                    time_window_start = max(0, current_min_of_day - 60)
                    time_window_end = min(1439, current_min_of_day + 60)
                    scheduled_actions_res = await execute_supabase_query(
                        lambda: supa.table("action_instance")
                        .select("id, def_id(title), start_min, status")
                        .in_("id", plan_action_ids)
                        .gte("start_min", time_window_start)
                        .lte("start_min", time_window_end)
                        .order("start_min")
                        .execute()
                    )

                    if scheduled_actions_res and scheduled_actions_res.data:
                        scheduled_action = None
                        for action in scheduled_actions_res.data:
                            if (
                                abs(action.get("start_min", 0) - current_min_of_day)
                                <= 60
                            ):
                                scheduled_action = action
                                break

                        if scheduled_action:
                            scheduled_action_found = True
                            current_action_title = scheduled_action.get(
                                "def_id", {}
                            ).get("title", "an activity")
                            scheduled_action_id = scheduled_action.get("id")
                            scheduled_action_status = scheduled_action.get(
                                "status", "unknown"
                            )

                if not scheduled_action_found:
                    if current_action_id:
                        action_res = await execute_supabase_query(
                            lambda: supa.table("action_instance")
                            .select("def_id(title)")
                            .eq("id", current_action_id)
                            .maybe_single()
                            .execute()
                        )
                        if action_res and action_res.data:
                            actual_action_title = action_res.data.get("def_id", {}).get(
                                "title", "something unplanned"
                            )
                            observation_content = f"[Periodic] At {time_label}, I was doing {actual_action_title} which wasn't part of my original plan."
                            importance = 2
                        else:
                            observation_content = f"[Periodic] At {time_label}, I was doing something unplanned."
                            importance = 2
                    else:
                        observation_content = f"[Periodic] At {time_label}, I had nothing scheduled and was idle as expected."
                        importance = 1
                else:
                    if current_action_id and current_action_id == scheduled_action_id:
                        observation_content = f"[Periodic] At {time_label}, I was following my plan by doing {current_action_title}."
                        importance = 1
                    elif current_action_id:
                        action_res = await execute_supabase_query(
                            lambda: supa.table("action_instance")
                            .select("def_id(title)")
                            .eq("id", current_action_id)
                            .maybe_single()
                            .execute()
                        )
                        if action_res and action_res.data:
                            actual_action_title = action_res.data.get("def_id", {}).get(
                                "title", "something different"
                            )
                            observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title} according to my plan, but instead I was doing {actual_action_title}."
                            importance = 3
                        else:
                            observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title}, but I was doing something else."
                            importance = 3
                    else:
                        observation_content = f"[Periodic] At {time_label}, I was supposed to be {current_action_title}, but I wasn't doing anything."
                        importance = 3

            observation_embedding = await get_embedding(observation_content)
            if observation_embedding:
                mem_payload = {
                    "npc_id": npc_id,
                    "sim_min": current_sim_minutes_total,
                    "kind": "obs",
                    "content": observation_content,
                    "importance": importance,
                    "embedding": observation_embedding,
                }
                await execute_supabase_query(
                    lambda: supa.table("memory").insert(mem_payload).execute()
                )
    except Exception as e:
        print(f"Error creating plan adherence observations: {e}")
