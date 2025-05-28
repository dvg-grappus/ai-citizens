from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
import datetime

from ..services import supa, execute_supabase_query # Assuming supa client is in services
from ..config import get_settings, Settings # For Supabase client initialization if needed, though supa should be pre-configured

router = APIRouter()

class PromptResponse(BaseModel):
    id: int
    name: str
    content: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

class PromptUpdateRequest(BaseModel):
    content: str

@router.get("/prompts/", response_model=List[PromptResponse], tags=["Prompts"])
async def get_all_prompts():
    """
    Retrieve all prompts from the database.
    """
    try:
        response = await execute_supabase_query(
            lambda: supa.table("prompts").select("id, name, content, created_at, updated_at").order("name").execute()
        )
        if response.data:
            return response.data
        return []
    except Exception as e:
        print(f"Error fetching all prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch prompts from database.")

@router.put("/prompts/{prompt_name}", response_model=PromptResponse, tags=["Prompts"])
async def update_prompt_by_name(prompt_name: str, prompt_update: PromptUpdateRequest):
    """
    Update the content of a specific prompt by its name.
    The 'updated_at' field should be auto-updated by the database trigger.
    """
    try:
        # First, check if the prompt exists to provide a 404 if not
        check_response = await execute_supabase_query(
            lambda: supa.table("prompts").select("id").eq("name", prompt_name).limit(1).maybe_single().execute()
        )
        if not (check_response.data):
            raise HTTPException(status_code=404, detail=f"Prompt with name '{prompt_name}' not found.")

        # If prompt exists, update its content
        update_response = await execute_supabase_query(
            lambda: supa.table("prompts")
            .update({"content": prompt_update.content})
            .eq("name", prompt_name)
            .execute()
        )

        if update_response.data:
            # Fetch the updated prompt to return it, as Supabase update doesn't return the full row by default with python client
            # or it might be simpler to just return the first element of update_response.data if it contains the updated record
            # For now, let's re-fetch to ensure `updated_at` is current from the DB.
            updated_prompt_response = await execute_supabase_query(
                lambda: supa.table("prompts").select("id, name, content, created_at, updated_at").eq("name", prompt_name).single().execute()
            )
            if updated_prompt_response.data:
                return updated_prompt_response.data
            else:
                 # This case should ideally not happen if update was successful
                raise HTTPException(status_code=500, detail="Failed to retrieve updated prompt details after update.")
        else:
            # This might indicate an issue with the update operation itself or RLS policies
            # if the row was found but not updated.
            print(f"Update response for prompt '{prompt_name}' had no data. Response: {update_response}")
            raise HTTPException(status_code=500, detail=f"Failed to update prompt '{prompt_name}'. Update operation returned no data.")

    except HTTPException as http_exc: # Re-raise HTTPExceptions to avoid them being caught by the generic Exception handler
        raise http_exc
    except Exception as e:
        print(f"Error updating prompt '{prompt_name}': {e}")
        # Check if it's a PostgREST APIError for more specific details
        if hasattr(e, 'code') and hasattr(e, 'message'): # Basic check for PostgREST like error
            detail = f"Database error updating prompt: {e.message} (Code: {e.code})"
        else:
            detail = f"An unexpected error occurred while updating prompt '{prompt_name}'."
        raise HTTPException(status_code=500, detail=detail)

# We will add the PUT endpoint next. 