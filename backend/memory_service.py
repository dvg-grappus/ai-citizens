import asyncio
import math
import numpy as np
from typing import List, Dict, Tuple, Literal, Optional

from .services import supa, execute_supabase_query
from .llm import client as openai_client
from .config import get_settings

settings = get_settings()

MAX_MEMORIES_TO_FETCH = 400
TOP_K_MEMORIES = 20
EMBEDDING_MODEL = "text-embedding-3-small"
RECENCY_DECAY_CONSTANT_TAU_MINUTES = 60 * 24

QUERY_WEIGHTS: Dict[Literal["planning", "reflection", "dialogue"], Tuple[float, float, float]] = {
    "planning": (0.2, 0.4, 0.4),
    "reflection": (0.3, 0.5, 0.2),
    "dialogue": (0.1, 0.2, 0.7),
}

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

async def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> Optional[List[float]]:
    try:
        response = await asyncio.to_thread(
            openai_client.embeddings.create,
            input=[text.strip()],
            model=model
        )
        if response.data and len(response.data) > 0:
            return response.data[0].embedding
        return None
    except Exception as e:
        print(f"Error getting embedding for text '{text[:50]}...': {e}")
        return None

async def retrieve_memories(
    npc_id: str,
    query_text: str,
    query_type: Literal["planning", "reflection", "dialogue"],
    current_sim_time_minutes: int
) -> str:
    weights = QUERY_WEIGHTS.get(query_type)
    if not weights:
        # Simplified log message
        weights = QUERY_WEIGHTS["planning"]
    w_recency, w_importance, w_similarity = weights

    try:
        memories_response_obj = await execute_supabase_query(lambda: supa.table("memory")
            .select("id, npc_id, sim_min, kind, content, importance, embedding")
            .eq("npc_id", npc_id)
            .order("sim_min", desc=True)
            .limit(MAX_MEMORIES_TO_FETCH)
            .execute())
        
        if not memories_response_obj.data:
            return "No memories found."
        fetched_memories = memories_response_obj.data
    except Exception as e:
        print(f"Error fetching memories for NPC {npc_id}: {e}")
        return "Error retrieving memories."

    query_embedding = await get_embedding(query_text)
    if not query_embedding:
        return "Could not generate query embedding."

    scored_memories = []
    for mem in fetched_memories:
        if not mem.get('content') or mem.get('embedding') is None or mem.get('sim_min') is None:
            continue

        delta_t_minutes = current_sim_time_minutes - mem['sim_min']
        recency_score = math.exp(-delta_t_minutes / RECENCY_DECAY_CONSTANT_TAU_MINUTES)
        
        importance_db = mem.get('importance', 1)
        importance_score = (importance_db - 1) / 4.0 if importance_db is not None else 0.0
        
        similarity_score = 0.0
        try:
            mem_embedding_db = mem['embedding']
            if isinstance(mem_embedding_db, str):
                try:
                    import json # Local import for safety
                    mem_embedding_db = json.loads(mem_embedding_db)
                    if not isinstance(mem_embedding_db, list):
                         raise ValueError("Parsed JSON is not a list")
                except (json.JSONDecodeError, ValueError) as parse_error:
                    # Simplified error log
                    mem_embedding_db = None
            
            if isinstance(mem_embedding_db, list) and query_embedding:
                 similarity_score = cosine_similarity(query_embedding, mem_embedding_db)

        except Exception as e_sim:
            # Simplified error log
            pass

        total_score = (
            w_recency * recency_score +
            w_importance * importance_score +
            w_similarity * similarity_score
        )
        scored_memories.append({"content": mem['content'], "score": total_score, "sim_min": mem['sim_min'], "kind": mem['kind']})
    
    top_memories = sorted(scored_memories, key=lambda x: x["score"], reverse=True)[:TOP_K_MEMORIES]
    
    formatted_memory_strings = [f"{mem_item['content']}" for mem_item in top_memories]

    return "\n".join(formatted_memory_strings) if formatted_memory_strings else "No relevant memories found after scoring."


async def save_memory_batch(memories: List[Dict]) -> Optional[List[Dict]]:
    """Saves a batch of memory records to the database."""
    if not memories:
        return []
    try:
        response = await execute_supabase_query(lambda: supa.table('memory').insert(memories).execute())
        return response.data if response and response.data else None
    except Exception as e:
        print(f"Error in save_memory_batch: {e}")
        return None

async def get_recent_memories_for_npc(npc_id: str, limit: int = 10) -> Optional[List[Dict]]:
    """Fetches the most recent memories for a given NPC."""
    try:
        response = await execute_supabase_query(
            lambda: supa.table('memory')
            .select("*") # Select all fields for general use
            .eq('npc_id', npc_id)
            .order('sim_min', desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response and response.data else []
    except Exception as e:
        print(f"Error in get_recent_memories_for_npc for {npc_id}: {e}")
        return []

async def main_test():
    print("Testing memory retrieval...")
    # Placeholder for actual test implementation
    # Example:
    # npc_id_test = "your-npc-uuid-from-db"
    # current_sim_time_test = 720 # Noon, Day 1
    # if settings.OPENAI_API_KEY and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
    #     retrieved = await retrieve_memories(npc_id_test, "what happened recently?", "reflection", current_sim_time_test)
    #     print("\\nRetrieved context for reflection:")
    #     print(retrieved)
    # else:
    #     print("Skipping test: Supabase/OpenAI config not fully available.")
    pass

if __name__ == '__main__':
    asyncio.run(main_test())