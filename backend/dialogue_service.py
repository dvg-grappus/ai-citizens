import asyncio
import random
import re
from typing import List, Dict, Any, Set, Optional, Tuple

from .config import get_settings
from .llm import call_llm
from .prompts import (
    DIALOGUE_SYSTEM_PROMPT_TEMPLATE, DIALOGUE_USER_PROMPT_TEMPLATE, format_traits,
    DIALOGUE_SUMMARY_SYSTEM_PROMPT, DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE
)
from .memory_service import retrieve_memories, get_embedding
from .services import supa, execute_supabase_query
from .websocket_utils import broadcast_ws_message
# We will need to import run_daily_planning from planning_and_reflection if we call it directly,
# or scheduler's get_current_sim_time_and_day.
# For now, this version will return NPCs to replan.

settings = get_settings()

# --- State for Dialogue Processing ---
pending_dialogue_requests: List[Dict[str, Any]] = []
# global npc_dialogue_cooldown_until # REMOVED - Will use DB table
# npc_dialogue_cooldown_until: Dict[str, int] = {} # REMOVED
DIALOGUE_COOLDOWN_MINUTES = 480 # UPDATED to 8 hours (8 * 60)

def _get_canonical_npc_pair(npc_id1: str, npc_id2: str) -> Tuple[str, str]:
    """Returns NPC IDs in a canonical order (lexicographically smaller first)."""
    return tuple(sorted((npc_id1, npc_id2)))

async def are_npcs_on_cooldown(npc_id1_check: str, npc_id2_check: str, current_tick: int) -> bool:
    """Checks the DB to see if a given pair of NPCs is on dialogue cooldown."""
    id1_canon, id2_canon = _get_canonical_npc_pair(npc_id1_check, npc_id2_check)
    try:
        cooldown_res = await execute_supabase_query(
            lambda: supa.table('npc_dialogue_cooldowns')
            .select('cooldown_until_sim_min')
            .eq('npc_id_1', id1_canon)
            .eq('npc_id_2', id2_canon)
            .maybe_single()
            .execute()
        )
        if cooldown_res and cooldown_res.data and cooldown_res.data.get('cooldown_until_sim_min', 0) > current_tick:
            return True # Cooldown is active
    except Exception as e:
        print(f"Error checking are_npcs_on_cooldown in DB: {e}")
        # If DB check fails, assume not on cooldown to allow dialogue attempts (fail open)
    return False # Not on cooldown or DB check failed

async def add_pending_dialogue_request(npc_a_id: str, npc_b_id: str, npc_a_name: str, npc_b_name: str, npc_a_traits: List[str], npc_b_traits: List[str], trigger_event: str, current_tick: int):
    """Adds a dialogue request if not already present and NPCs are not on DB cooldown (checked by caller or here as safeguard)."""
    
    # This check is somewhat redundant if the scheduler calls are_npcs_on_cooldown first, 
    # but kept as a direct safeguard within the service if called from elsewhere or if scheduler's check is bypassed.
    if await are_npcs_on_cooldown(npc_a_id, npc_b_id, current_tick):
        print(f"[DialogueAddAttemptDB-Direct] Cooldown active for pair ({npc_a_name}, {npc_b_name}). Request at tick {current_tick} rejected.")
        return

    for req in pending_dialogue_requests:
        if req['tick'] == current_tick and \
           ((req['npc_a_id'] == npc_a_id and req['npc_b_id'] == npc_b_id) or \
            (req['npc_a_id'] == npc_b_id and req['npc_b_id'] == npc_a_id)):
            return

    pending_dialogue_requests.append({
        'npc_a_id': npc_a_id, 'npc_b_id': npc_b_id,
        'npc_a_name': npc_a_name, 'npc_b_name': npc_b_name,
        'npc_a_traits': npc_a_traits, 'npc_b_traits': npc_b_traits,
        'trigger_event': trigger_event, 'tick': current_tick
    })

async def process_pending_dialogues(current_sim_minutes_total: int) -> None:
    """Processes dialogues and triggers replanning when appropriate."""
    global pending_dialogue_requests

    if not pending_dialogue_requests:
        return
    print(f"DEBUG: Processing {len(pending_dialogue_requests)} pending dialogue requests at tick {current_sim_minutes_total}.")
    
    processed_indices = []
    for i, request in enumerate(pending_dialogue_requests):
        npc_a_id = request['npc_a_id']
        npc_b_id = request['npc_b_id']
        npc_a_name = request['npc_a_name']
        npc_b_name = request['npc_b_name']
        npc_a_traits = request['npc_a_traits']
        npc_b_traits = request['npc_b_traits']
        trigger_event = request['trigger_event']
        request_tick = request['tick']

        if current_sim_minutes_total > request_tick + DIALOGUE_COOLDOWN_MINUTES: # Stale check remains
            processed_indices.append(i)
            continue

        # Final cooldown safeguard. The primary cooldown check and the 50% initiation chance
        # are handled in scheduler.py *before* a dialogue request is added.
        # If a request reaches this point, it means it passed those initial checks.
        if await are_npcs_on_cooldown(npc_a_id, npc_b_id, current_sim_minutes_total):
            print(f"  [ProcessQueueDB] Dialogue for {npc_a_name} & {npc_b_name} skipped: Cooldown (final check).")
            processed_indices.append(i)
            continue

        # Dialogue proceeds if not on cooldown (checked above).
        # The initial 50% chance to attempt dialogue is in scheduler.py.
        print(f"  Dialogue processing for {npc_a_name} and {npc_b_name}")
        dialogue_insert_payload = {'npc_a': npc_a_id, 'npc_b': npc_b_id, 'start_min': current_sim_minutes_total}
        dialogue_response = await execute_supabase_query(lambda: supa.table('dialogue').insert(dialogue_insert_payload).execute())
        
        if not (dialogue_response and dialogue_response.data and len(dialogue_response.data) > 0):
            print(f"    !!!! Failed to insert dialogue row for {npc_a_name} & {npc_b_name}.")
            processed_indices.append(i) # Mark as processed
            continue # Skip to next request
        
        # If we reach here, dialogue row was inserted successfully
        dialogue_id = dialogue_response.data[0]['id']
        print(f"    Dialogue row inserted, ID: {dialogue_id}")

        mem_a = await retrieve_memories(npc_a_id, trigger_event, "dialogue", current_sim_minutes_total)
        # mem_b = await retrieve_memories(npc_b_id, trigger_event, "dialogue", current_sim_minutes_total) # mem_b not used in current prompts
        dialogue_system_prompt = DIALOGUE_SYSTEM_PROMPT_TEMPLATE.format(
            npc_name=npc_a_name, 
            traits=format_traits(npc_a_traits)
        )
        area_name_for_dialogue = "their current location" 
        if " in " in trigger_event:
            try: area_name_for_dialogue = trigger_event.split(" in ", 1)[1].strip('.')
            except: pass

        dialogue_user_prompt = DIALOGUE_USER_PROMPT_TEMPLATE.format(
            other_npc_name=npc_b_name, 
            other_npc_traits=format_traits(npc_b_traits),
            area_name=area_name_for_dialogue, 
            memories=mem_a 
        )
        raw_dialogue_text = call_llm(dialogue_system_prompt, dialogue_user_prompt, max_tokens=400)

        if raw_dialogue_text:
            print(f"    Raw dialogue:\n{raw_dialogue_text}")
            lines = raw_dialogue_text.strip().split('\n')
            current_speaker_id_for_turn = npc_a_id # Default if parsing fails early
            
            for turn_text_raw in lines:
                turn_text = turn_text_raw.strip()
                if not turn_text: # Skip empty lines
                    continue

                # General pattern to capture speaker and utterance
                # Handles optional bolding around speaker, colon, and then captures utterance
                # Example: **Alice:** utterance OR Alice: utterance
                match = re.match(r"^(?:\\*\\*)?([^:]+?)(?:\\*\\*)?:\s*(.+)$", turn_text)
                
                parsed_utterance = None
                speaker_name_candidate = None

                if match:
                    speaker_name_candidate = match.group(1).strip()
                    speaker_name_candidate = speaker_name_candidate.strip('*') # Strip markdown bold asterisks
                    parsed_utterance = match.group(2).strip()
                    
                    if speaker_name_candidate.lower() == npc_a_name.lower():
                        current_speaker_id_for_turn = npc_a_id
                    elif speaker_name_candidate.lower() == npc_b_name.lower():
                        current_speaker_id_for_turn = npc_b_id
                    else:
                        # Name in line doesn't match known speakers, could be narration or misformatted
                        print(f"      Warning: Speaker '{speaker_name_candidate}' in line '{turn_text}' does not match known NPCs. Attributing to last known speaker or default.")
                        # Keep current_speaker_id_for_turn as is (last valid speaker or default)
                        # And treat the whole line as utterance if name mismatch
                        parsed_utterance = turn_text # Or just match.group(2) if we want to discard the unknown speaker part
                else:
                    # Line doesn't fit Speaker: Utterance pattern, treat as continuation or unformatted line
                    print(f"      Warning: Could not parse standard Speaker: Text from line: '{turn_text}'. Treating as utterance.")
                    parsed_utterance = turn_text 
                    # current_speaker_id_for_turn remains from previous turn or default

                if not parsed_utterance: # Should not happen if logic above is correct, but safeguard
                    continue

                turn_payload = {'dialogue_id': dialogue_id, 'speaker_id': current_speaker_id_for_turn, 'sim_min': current_sim_minutes_total, 'text': parsed_utterance}
                await execute_supabase_query(lambda: supa.table('dialogue_turn').insert(turn_payload).execute())
            await execute_supabase_query(lambda: supa.table('dialogue').update({'end_min': current_sim_minutes_total}).eq('id', dialogue_id).execute())
            print(f"    Dialogue ID {dialogue_id} ended and recorded.")

            # --- Update Cooldown in DB ---
            id1_canon, id2_canon = _get_canonical_npc_pair(npc_a_id, npc_b_id)
            new_cooldown_until = current_sim_minutes_total + DIALOGUE_COOLDOWN_MINUTES
            try:
                await execute_supabase_query(
                    lambda: supa.table('npc_dialogue_cooldowns')
                    .upsert({'npc_id_1': id1_canon, 'npc_id_2': id2_canon, 'cooldown_until_sim_min': new_cooldown_until})
                    .execute()
                )
                print(f"    NPCs {npc_a_name} & {npc_b_name} on dialogue cooldown until sim_min {new_cooldown_until} (DB updated).")
            except Exception as e_db_cooldown_set:
                print(f"    !!!! Failed to set dialogue cooldown in DB for {npc_a_name} & {npc_b_name}: {e_db_cooldown_set}")
            # --- End Update Cooldown in DB ---

            # Dialogue summary saving and broadcast logic as before
            summary_a = call_llm(DIALOGUE_SUMMARY_SYSTEM_PROMPT, DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE.format(npc_name=npc_a_name, other_npc_name=npc_b_name, dialogue_transcript=raw_dialogue_text), 100) or f"I talked with {npc_b_name}."
            emb_a = await get_embedding(summary_a)
            if emb_a:
                mem_payload_a = {'npc_id': npc_a_id, 'sim_min': current_sim_minutes_total, 'kind': 'dialogue_summary', 'content': summary_a, 'importance': 3, 'embedding': emb_a, 'metadata': {'dialogue_id': dialogue_id, 'other_participant_name': npc_b_name}}
                db_res_sum_a = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_a).execute())
                if db_res_sum_a.data: print(f"    Saved dialogue summary for {npc_a_name}"); await broadcast_ws_message("dialogue_event", {"npc_id": npc_a_id, "npc_name": npc_a_name, "other_participant_name": npc_b_name, "summary": summary_a, "dialogue_id": dialogue_id, "sim_min_of_day": current_sim_minutes_total % 1440, "day": (current_sim_minutes_total // 1440) + 1 })

            summary_b = call_llm(DIALOGUE_SUMMARY_SYSTEM_PROMPT, DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE.format(npc_name=npc_b_name, other_npc_name=npc_a_name, dialogue_transcript=raw_dialogue_text), 100) or f"I talked with {npc_a_name}."
            emb_b = await get_embedding(summary_b)
            if emb_b:
                mem_payload_b = {'npc_id': npc_b_id, 'sim_min': current_sim_minutes_total, 'kind': 'dialogue_summary', 'content': summary_b, 'importance': 3, 'embedding': emb_b, 'metadata': {'dialogue_id': dialogue_id, 'other_participant_name': npc_a_name}}
                db_res_sum_b = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_b).execute())
                if db_res_sum_b.data: print(f"    Saved dialogue summary for {npc_b_name}"); await broadcast_ws_message("dialogue_event", {"npc_id": npc_b_id, "npc_name": npc_b_name, "other_participant_name": npc_a_name, "summary": summary_b, "dialogue_id": dialogue_id, "sim_min_of_day": current_sim_minutes_total % 1440, "day": (current_sim_minutes_total // 1440) + 1 })
            
            # Trigger replanning for both NPCs based on dialogue summary
            from .planning_and_reflection import run_replanning
            await run_replanning(npc_a_id, {"description": summary_a}, current_sim_minutes_total)
            await run_replanning(npc_b_id, {"description": summary_b}, current_sim_minutes_total)
        else: # No raw_dialogue_text
             print(f"    LLM call for dialogue between {npc_a_name} & {npc_b_name} returned no text.")
        
        processed_indices.append(i) # Mark as processed after successful handling or if LLM failed
    
    for index in sorted(processed_indices, reverse=True):
        pending_dialogue_requests.pop(index)

    return None
