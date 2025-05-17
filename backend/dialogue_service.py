import asyncio
import random
import re
from typing import List, Dict, Any, Set, Optional

from .config import get_settings
from .llm import call_llm
from .prompts import DIALOGUE_SYSTEM_PROMPT_TEMPLATE, DIALOGUE_USER_PROMPT_TEMPLATE, format_traits
from .memory_service import retrieve_memories, get_embedding
from .services import supa, execute_supabase_query
# We will need to import run_daily_planning from planning_and_reflection if we call it directly,
# or scheduler's get_current_sim_time_and_day.
# For now, this version will return NPCs to replan.

settings = get_settings()

# --- State for Dialogue Processing ---
pending_dialogue_requests: List[Dict[str, Any]] = []
npc_dialogue_cooldown_until: Dict[str, int] = {}
DIALOGUE_COOLDOWN_MINUTES = 360 # Value from scheduler.py

def add_pending_dialogue_request(npc_a_id: str, npc_b_id: str, npc_a_name: str, npc_b_name: str, npc_a_traits: List[str], npc_b_traits: List[str], trigger_event: str, current_tick: int):
    """Adds a dialogue request to the pending list if not already present for this pair this tick."""
    # Basic check to prevent duplicate requests for the same pair in the same tick, can be more sophisticated
    for req in pending_dialogue_requests:
        if req['tick'] == current_tick and \
           ((req['npc_a_id'] == npc_a_id and req['npc_b_id'] == npc_b_id) or \
            (req['npc_a_id'] == npc_b_id and req['npc_b_id'] == npc_a_id)):
            # print(f"DEBUG: Dialogue request for {npc_a_name} & {npc_b_name} at tick {current_tick} already pending.")
            return

    pending_dialogue_requests.append({
        'npc_a_id': npc_a_id, 'npc_b_id': npc_b_id,
        'npc_a_name': npc_a_name, 'npc_b_name': npc_b_name,
        'npc_a_traits': npc_a_traits, 'npc_b_traits': npc_b_traits,
        'trigger_event': trigger_event, 'tick': current_tick
    })
    # print(f"DEBUG: Added pending dialogue request for {npc_a_name} and {npc_b_name} at tick {current_tick}")


async def process_pending_dialogues(current_sim_minutes_total: int) -> List[str]:
    """
    Processes pending dialogue requests.
    Returns a list of NPC IDs that need to replan as a result of dialogues.
    """
    global pending_dialogue_requests, npc_dialogue_cooldown_until # To modify them

    npcs_to_replan = []

    if not pending_dialogue_requests:
        return npcs_to_replan

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

        if current_sim_minutes_total > request_tick + DIALOGUE_COOLDOWN_MINUTES: # Stale
            processed_indices.append(i)
            continue

        if npc_dialogue_cooldown_until.get(npc_a_id, 0) > current_sim_minutes_total or \
           npc_dialogue_cooldown_until.get(npc_b_id, 0) > current_sim_minutes_total:
            processed_indices.append(i)
            continue

        initiation_chance = 0.60 
        if 'friendly' in npc_a_traits or 'friendly' in npc_b_traits: initiation_chance += 0.15
        if 'grumpy' in npc_a_traits or 'grumpy' in npc_b_traits: initiation_chance -= 0.15
        initiation_chance = max(0.1, min(0.9, initiation_chance))

        if random.random() < initiation_chance:
            print(f"  Dialogue initiated between {npc_a_name} and {npc_b_name} (Chance: {initiation_chance:.2f})")
            dialogue_turns = 3 

            dialogue_insert_payload = {'npc_a': npc_a_id, 'npc_b': npc_b_id, 'start_min': current_sim_minutes_total}
            dialogue_response = await execute_supabase_query(lambda: supa.table('dialogue').insert(dialogue_insert_payload).select('id').execute())
            
            if not (dialogue_response and dialogue_response.data and len(dialogue_response.data) > 0):
                print(f"    !!!! Failed to insert dialogue row for {npc_a_name} & {npc_b_name}. Error: {getattr(dialogue_response, 'error', 'N/A')}")
                processed_indices.append(i)
                continue
            dialogue_id = dialogue_response.data[0]['id']
            print(f"    Dialogue row inserted, ID: {dialogue_id}")

            mem_a = await retrieve_memories(npc_a_id, trigger_event, "dialogue", current_sim_minutes_total)
            mem_b = await retrieve_memories(npc_b_id, trigger_event, "dialogue", current_sim_minutes_total)
            combined_memories = f"Memories for {npc_a_name}:\n{mem_a}\n\nMemories for {npc_b_name}:\n{mem_b}"

            dialogue_system_prompt = DIALOGUE_SYSTEM_PROMPT_TEMPLATE.format(num_turns=dialogue_turns * 2)
            dialogue_user_prompt = DIALOGUE_USER_PROMPT_TEMPLATE.format(
                npc_a_name=npc_a_name, npc_a_traits=format_traits(npc_a_traits),
                npc_b_name=npc_b_name, npc_b_traits=format_traits(npc_b_traits),
                trigger_event=trigger_event, retrieved_memories=combined_memories
            )
            raw_dialogue_text = call_llm(dialogue_system_prompt, dialogue_user_prompt, max_tokens=400)

            if raw_dialogue_text:
                print(f"    Raw dialogue:\n{raw_dialogue_text}")
                lines = raw_dialogue_text.strip().split('\n')
                current_speaker_id = npc_a_id
                
                for turn_text in lines:
                    speaker_match_a = re.match(f"^{re.escape(npc_a_name)}:\s*(.+)", turn_text, re.IGNORECASE)
                    speaker_match_b = re.match(f"^{re.escape(npc_b_name)}:\s*(.+)", turn_text, re.IGNORECASE)
                    
                    parsed_utterance = None
                    if speaker_match_a:
                        current_speaker_id = npc_a_id
                        parsed_utterance = speaker_match_a.group(1).strip()
                    elif speaker_match_b:
                        current_speaker_id = npc_b_id
                        parsed_utterance = speaker_match_b.group(1).strip()
                    else: 
                        print(f"      Warning: Could not parse speaker from dialogue line: '{turn_text}'")
                        parsed_utterance = turn_text 
                        if not parsed_utterance.strip(): continue

                    if not parsed_utterance: continue

                    turn_payload = {'dialogue_id': dialogue_id, 'speaker_id': current_speaker_id, 'sim_min': current_sim_minutes_total, 'text': parsed_utterance}
                    await execute_supabase_query(lambda: supa.table('dialogue_turn').insert(turn_payload).execute())
                    
                    mem_content = f"[Social] {npc_a_name if current_speaker_id == npc_a_id else npc_b_name} said: \"{parsed_utterance}\" during encounter about {trigger_event[:30]}..."
                    utterance_embedding = await get_embedding(mem_content)
                    if utterance_embedding:
                        mem_payload_speaker = {'npc_id': current_speaker_id, 'sim_min': current_sim_minutes_total, 'kind': 'obs', 'content': mem_content, 'importance': 2, 'embedding': utterance_embedding}
                        await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_speaker).execute())
                        
                        other_participant_id = npc_b_id if current_speaker_id == npc_a_id else npc_a_id
                        mem_payload_other = {'npc_id': other_participant_id, 'sim_min': current_sim_minutes_total, 'kind': 'obs', 'content': mem_content, 'importance': 2, 'embedding': utterance_embedding}
                        await execute_supabase_query(lambda: supa.table('memory').insert(mem_payload_other).execute())
                
                await execute_supabase_query(lambda: supa.table('dialogue').update({'end_min': current_sim_minutes_total}).eq('id', dialogue_id).execute())
                print(f"    Dialogue ID {dialogue_id} ended and recorded.")

                npc_dialogue_cooldown_until[npc_a_id] = current_sim_minutes_total + DIALOGUE_COOLDOWN_MINUTES
                npc_dialogue_cooldown_until[npc_b_id] = current_sim_minutes_total + DIALOGUE_COOLDOWN_MINUTES
                print(f"    NPCs {npc_a_name} & {npc_b_name} on dialogue cooldown until sim_min {npc_dialogue_cooldown_until[npc_a_id]}.")

                if random.random() < 0.30:
                    if npc_a_id not in npcs_to_replan: npcs_to_replan.append(npc_a_id)
                if random.random() < 0.30:
                    if npc_b_id not in npcs_to_replan: npcs_to_replan.append(npc_b_id)
            else: # No raw_dialogue_text
                 print(f"    LLM call for dialogue between {npc_a_name} and {npc_b_name} returned no text.")
        
        else: # Did not pass initiation chance
            print(f"  Dialogue NOT initiated between {npc_a_name} and {npc_b_name} (Chance: {initiation_chance:.2f})")
        
        processed_indices.append(i)
    
    for index in sorted(processed_indices, reverse=True):
        pending_dialogue_requests.pop(index)
        
    return npcs_to_replan 