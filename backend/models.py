from pydantic import BaseModel
from typing import List, Optional # Optional might be needed if fields can be absent

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
