from pydantic import BaseModel
from typing import List, Optional, Dict, Any # Ensure these are imported

class Position(BaseModel):
    x: int
    y: int
    areaId: str # In Supabase schema, this is UUID, but playbook uses string here.
                # For consistency with readme, UUID (str) is fine.

class NPCSeed(BaseModel):
    name: str
    traits: List[str]
    backstory: str
    spawn: Position

class SeedPayload(BaseModel):
    npcs: List[NPCSeed]

# --- ADDING MISSING MODELS FOR NPC DETAIL --- 
class ActionInfo(BaseModel):
    time: Optional[str] = None
    title: str
    status: Optional[str] = None
    area_name: Optional[str] = None

class ReflectionInfo(BaseModel):
    content: str
    time: Optional[str] = None

class MemoryEvent(BaseModel):
    content: str
    time: Optional[str] = None
    type: Optional[str] = None # This is 'kind' from DB
    metadata: Optional[Dict[str, Any]] = None # ADDED metadata field

class NPCUIDetailData(BaseModel):
    npc_id: str
    npc_name: str
    last_completed_action: Optional[ActionInfo] = None
    completed_actions: List[ActionInfo] = []
    queued_actions: List[ActionInfo] = []
    latest_reflection: Optional[str] = None
    reflections: List[ReflectionInfo] = []
    current_plan_summary: List[str] = []
    memory_stream: List[MemoryEvent] = []
# --- END ADDED MODELS ---

# --- ADDING MODELS FOR DIALOGUE TRANSCRIPT ---
class DialogueTurnResponse(BaseModel):
    speaker_name: str
    text: str
    sim_min_of_turn: int # Original sim_min for sorting/reference
    timestamp_str: str # Formatted time string for display

class DialogueTranscriptResponse(BaseModel):
    dialogue_id: str
    turns: List[DialogueTurnResponse]
# --- END DIALOGUE TRANSCRIPT MODELS ---
