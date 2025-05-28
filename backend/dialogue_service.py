import asyncio
import random
import re
from typing import List, Dict, Any, Set, Optional, Tuple

from .config import get_settings
from .llm import call_llm
from .prompts import (
    get_dialogue_system_prompt, get_dialogue_user_prompt, format_traits,
    get_dialogue_summary_system_prompt, get_dialogue_summary_user_prompt
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

# Track active dialogues to prevent race conditions
active_dialogues_pending_completion: Dict[Tuple[str, str], int] = {}

def _parse_dialogue_from_llm(raw_text: str, npc_a_name: str, npc_b_name: str) -> List[Dict[str, str]]:
    """
    Parses the raw dialogue text from the LLM into structured turns.
    Returns a list of dictionaries with 'speaker' and 'line' keys.
    """
    dialogue_turns = []
    
    # Split by lines and process each
    lines = raw_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to match patterns like "**Alice:** Hello" or "Alice: Hello" 
        # First try the bold format with potential actions
        match = re.match(r'\*\*(.+?)\*\*\s*:\s*(.+)', line)
        if not match:
            # Try regular format
            match = re.match(r'([A-Za-z]+):\s*(.+)', line)
            
        if match:
            speaker = match.group(1).strip()
            dialogue_content = match.group(2).strip()
            
            # Verify the speaker is one of our NPCs (case-insensitive)
            if speaker.lower() == npc_a_name.lower() or speaker.lower() == npc_b_name.lower():
                # Normalize the speaker name to match the actual NPC name
                if speaker.lower() == npc_a_name.lower():
                    speaker = npc_a_name
                else:
                    speaker = npc_b_name
                    
                dialogue_turns.append({
                    'speaker': speaker,
                    'line': dialogue_content
                })
        else:
            # If no speaker pattern found but previous turn exists, might be continuation
            if dialogue_turns and line and not line.startswith('*'):
                dialogue_turns[-1]['line'] += ' ' + line
    
    return dialogue_turns

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

async def add_pending_dialogue_request(npc_a_id: str, npc_b_id: str, npc_a_name: str, npc_b_name: str, npc_a_traits: List[str], npc_b_traits: List[str], trigger_event: str, current_tick: int, area_name: str):
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
        'trigger_event': trigger_event, 'tick': current_tick,
        'area_name': area_name
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
        area_name = request['area_name']

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
        
        # Track this dialogue as active
        dialogue_pair = _get_canonical_npc_pair(npc_a_id, npc_b_id)
        if dialogue_pair not in active_dialogues_pending_completion:
            active_dialogues_pending_completion[dialogue_pair] = 0
        active_dialogues_pending_completion[dialogue_pair] += 1
        
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
        dialogue_system_template_A = get_dialogue_system_prompt()
        dialogue_user_template_A = get_dialogue_user_prompt()

        system_prompt_A = dialogue_system_template_A.format(npc_name=npc_a_name, traits=format_traits(npc_a_traits))
        user_prompt_A = dialogue_user_template_A.format(
            other_npc_name=npc_b_name,
            other_npc_traits=format_traits(npc_b_traits),
            area_name=area_name,
            memories=mem_a
        )

        raw_dialogue_text = call_llm(system_prompt_A, user_prompt_A, max_tokens=600)

        if raw_dialogue_text:
            print(f"    Raw dialogue:\n{raw_dialogue_text}")
            parsed_dialogue_turns = _parse_dialogue_from_llm(raw_dialogue_text, npc_a_name, npc_b_name)

            if not parsed_dialogue_turns:
                print(f"DIALOGUE: Could not parse dialogue between {npc_a_name} and {npc_b_name}. Raw text: {raw_dialogue_text}")
                await broadcast_ws_message("dialogue_event", {"status": "failed_parsing", "npc_a_name": npc_a_name, "npc_b_name": npc_b_name})
                # Don't try to decrement if it doesn't exist
                dialogue_pair = _get_canonical_npc_pair(npc_a_id, npc_b_id)
                if dialogue_pair in active_dialogues_pending_completion:
                    active_dialogues_pending_completion[dialogue_pair] -= 1
                    if active_dialogues_pending_completion[dialogue_pair] <= 0:
                        del active_dialogues_pending_completion[dialogue_pair]
                processed_indices.append(i)  # Mark as processed even if parsing failed
                continue  # Skip to next dialogue instead of returning

            # 4. Summarize Dialogue from perspective of NPC A
            dialogue_summary_system_template_A = get_dialogue_summary_system_prompt()
            dialogue_summary_user_template_A = get_dialogue_summary_user_prompt()
            
            summary_system_A = dialogue_summary_system_template_A # No formatting needed for this system prompt
            summary_user_A = dialogue_summary_user_template_A.format(
                npc_name=npc_a_name,
                other_npc_name=npc_b_name,
                dialogue_transcript="\n".join([f"{turn['speaker']}: {turn['line']}" for turn in parsed_dialogue_turns])
            )
            summary_A = call_llm(summary_system_A, summary_user_A, max_tokens=150)

            # 5. Summarize Dialogue from perspective of NPC B
            # Retrieve relevant memories for NPC B about NPC A and the trigger event
            query_context_for_B = f"Thoughts about {npc_a_name} regarding: {trigger_event}"
            # For B's summary, we don't need B's memories for generating the summary of a transcript they just participated in.
            # The transcript itself is the context.
            dialogue_summary_system_template_B = get_dialogue_summary_system_prompt()
            dialogue_summary_user_template_B = get_dialogue_summary_user_prompt()

            summary_system_B = dialogue_summary_system_template_B # No formatting needed
            summary_user_B = dialogue_summary_user_template_B.format(
                npc_name=npc_b_name,
                other_npc_name=npc_a_name,
                dialogue_transcript="\n".join([f"{turn['speaker']}: {turn['line']}" for turn in parsed_dialogue_turns])
            )
            summary_B = call_llm(summary_system_B, summary_user_B, max_tokens=150)

            print(f"  DIALOGUE SUMMARY - {npc_a_name}: {summary_A}")

            # If we reach here, dialogue row was inserted successfully
            dialogue_id = dialogue_response.data[0]['id']
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
            emb_a = await get_embedding(summary_A)
            if emb_a:
                mem_payload_a = {'npc_id': npc_a_id, 'sim_min': current_sim_minutes_total, 'kind': 'dialogue_summary', 'content': summary_A, 'importance': 3, 'embedding': emb_a, 'metadata': {'dialogue_id': dialogue_id, 'other_participant_name': npc_b_name}}
                db_res_sum_a = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_a).execute())
                if db_res_sum_a.data: print(f"    Saved dialogue summary for {npc_a_name}"); await broadcast_ws_message("dialogue_event", {"npc_id": npc_a_id, "npc_name": npc_a_name, "other_participant_name": npc_b_name, "summary": summary_A, "dialogue_id": dialogue_id, "sim_min_of_day": current_sim_minutes_total % 1440, "day": (current_sim_minutes_total // 1440) + 1 })

            emb_b = await get_embedding(summary_B)
            if emb_b:
                mem_payload_b = {'npc_id': npc_b_id, 'sim_min': current_sim_minutes_total, 'kind': 'dialogue_summary', 'content': summary_B, 'importance': 3, 'embedding': emb_b, 'metadata': {'dialogue_id': dialogue_id, 'other_participant_name': npc_a_name}}
                db_res_sum_b = await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_b).execute())
                if db_res_sum_b.data: print(f"    Saved dialogue summary for {npc_b_name}"); await broadcast_ws_message("dialogue_event", {"npc_id": npc_b_id, "npc_name": npc_b_name, "other_participant_name": npc_a_name, "summary": summary_B, "dialogue_id": dialogue_id, "sim_min_of_day": current_sim_minutes_total % 1440, "day": (current_sim_minutes_total // 1440) + 1 })
            
            # Trigger replanning for both NPCs based on dialogue summary
            from .planning_and_reflection import run_replanning
            # Construct new event_info for replanning after dialogue
            event_info_a = {
                "source": "dialogue",
                "partner_name": npc_b_name,
                "original_description": summary_A # The dialogue summary is the detailed description
            }
            await run_replanning(npc_a_id, event_info_a, current_sim_minutes_total)

            event_info_b = {
                "source": "dialogue",
                "partner_name": npc_a_name,
                "original_description": summary_B # The dialogue summary is the detailed description
            }
            await run_replanning(npc_b_id, event_info_b, current_sim_minutes_total)
        else: # No raw_dialogue_text
             print(f"    LLM call for dialogue between {npc_a_name} & {npc_b_name} returned no text.")
        
        # Clean up the active dialogue tracking
        if dialogue_pair in active_dialogues_pending_completion:
            active_dialogues_pending_completion[dialogue_pair] -= 1
            if active_dialogues_pending_completion[dialogue_pair] <= 0:
                del active_dialogues_pending_completion[dialogue_pair]
        
        processed_indices.append(i) # Mark as processed after successful handling or if LLM failed
    
    for index in sorted(processed_indices, reverse=True):
        pending_dialogue_requests.pop(index)

    return None
