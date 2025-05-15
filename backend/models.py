from pydantic import BaseModel
from typing import List, Optional, Dict # Ensure these are imported

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

class NPCUIDetailData(BaseModel):
    npc_id: str
    npc_name: str
    last_completed_action: Optional[ActionInfo] = None
    queued_actions: List[ActionInfo] = []
    latest_reflection: Optional[str] = None
    current_plan_summary: List[str] = []
# --- END ADDED MODELS ---
