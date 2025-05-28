# backend/prompts.py

import os
from supabase import create_client, Client
from dotenv import load_dotenv
import ast # For safely evaluating string to list
from typing import Optional, List # Added List for get_available_actions_list type hint

# Load environment variables
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") # Use anon key for read operations

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env file or environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cache for prompts to reduce DB calls
PROMPT_CACHE = {}

def get_prompt_from_db(prompt_name: str) -> Optional[str]:
    """Fetches a prompt by its name from the Supabase 'prompts' table."""
    if prompt_name in PROMPT_CACHE:
        return PROMPT_CACHE[prompt_name]

    try:
        response = supabase.table("prompts").select("content").eq("name", prompt_name).limit(1).single().execute()
        if response.data:
            PROMPT_CACHE[prompt_name] = response.data["content"]
            return response.data["content"]
        else:
            print(f"Warning: Prompt '{prompt_name}' not found in Supabase.")
            return None
    except Exception as e:
        print(f"Error fetching prompt '{prompt_name}' from Supabase: {e}")
        return None

# --- Functions to retrieve and format specific prompts ---

def get_available_actions_list() -> List[str]:
    """Fetches and parses the AVAILABLE_ACTIONS_LIST from Supabase."""
    actions_str = get_prompt_from_db("AVAILABLE_ACTIONS_LIST")
    if actions_str:
        try:
            # Safely evaluate the string representation of the list
            actions_list = ast.literal_eval(actions_str)
            if isinstance(actions_list, list):
                return actions_list
            else:
                print(f"Warning: 'AVAILABLE_ACTIONS_LIST' from DB is not a list: {actions_list}")
                return [] # Fallback to empty list
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing 'AVAILABLE_ACTIONS_LIST' from DB: {e}")
            return [] # Fallback to empty list
    # Fallback if not found in DB or error parsing
    print("Warning: 'AVAILABLE_ACTIONS_LIST' not found or unparsable in DB. Using hardcoded default.")
    return [
        "Sleep", "Brush Teeth", "Work", "Eat", "Walk",
        "Chat", "Relax", "Read", "Nap", "Explore",
        "Watch TV", "Relax on Couch", "Have Coffee"
    ]


def get_plan_system_prompt() -> str:
    return get_prompt_from_db("PLAN_SYSTEM_PROMPT_TEMPLATE") or \
           "You control NPC {name}. Today is {sim_date}. Your core traits are: {traits_summary}." # Fallback

def get_plan_user_prompt() -> str:
    """
    Fetches the PLAN_USER_PROMPT_TEMPLATE.
    If the fetched prompt contains '{{AVAILABLE_ACTIONS_AS_STRING}}', it's replaced dynamically.
    """
    plan_user_raw = get_prompt_from_db("PLAN_USER_PROMPT_TEMPLATE")

    if not plan_user_raw:
        # Fallback to a basic template if not found in DB
        # Ensure f-string interpolation for actions_list is done correctly
        actions_list_str = ", ".join(get_available_actions_list())
        plan_user_raw = (
            f"Based on your personality and the following memories, produce an ordered list of actions (max 8) for today.\n"
            f"You MUST choose actions EXCLUSIVELY from the following list: {actions_list_str}.\n"
            f"Do NOT invent new actions. If you want to do something like 'Eat Breakfast', use the action 'Eat'.\n"
            f"Format each action as: HH:MM — <ACTION_TITLE_FROM_LIST>\n"
            f"Example: 09:00 — Work\n"
            f"Your day starts at 00:00 and ends at 23:59. Schedule a reasonable number of actions.\n"
            f"CONTEXT (recent memories, reflections, and relevant observations):\n{{retrieved_memories}}\n"
            f"TASK: Provide your schedule for today, using only the allowed action titles."
        )
        return plan_user_raw # Return here as it's already formatted with dynamic actions

    # If fetched from DB, replace placeholder if it exists
    # This allows users to make the action list dynamic by adding the placeholder in Supabase.
    current_actions_str = ", ".join(get_available_actions_list())
    return plan_user_raw.replace("{{AVAILABLE_ACTIONS_AS_STRING}}", current_actions_str)


def get_reflection_system_prompt() -> str:
    return get_prompt_from_db("REFLECTION_SYSTEM_PROMPT_TEMPLATE") or \
           "You are {npc_name}. Your task is to summarize the key events and your main thoughts for {sim_date} as exactly 1-3 bullet points. Each bullet point MUST start with '•' and end with [Importance: N] where N is 1-5." # Fallback

def get_reflection_user_prompt() -> str:
    return get_prompt_from_db("REFLECTION_USER_PROMPT_TEMPLATE") or \
           (
            "Consider your core traits: {traits_summary}.\n"
            "Based on the following log of your activities and observations from the day, reflect on what happened.\n"
            "\n"
            "FORMAT YOUR RESPONSE EXACTLY LIKE THIS:\n"
            "• First reflection point [Importance: X]\n"
            "• Second reflection point [Importance: Y]\n"
            "• Third reflection point [Importance: Z]\n"
            "\n"
            "IMPORTANT: Each line MUST start with a bullet point (•) and end with [Importance: N] where N is a number from 1-5.\n"
            "CONTEXT (memories from the day - plans, observations, dialogues):\n{retrieved_memories}\n"
            "TASK: Provide your reflection as 1-3 bullet points with importance scores in the exact format shown above."
        ) # Fallback

def get_dialogue_system_prompt() -> str:
    return get_prompt_from_db("DIALOGUE_SYSTEM_PROMPT_TEMPLATE") or \
           (
            "You are an AI generating a brief, natural dialogue between two NPCs in a simulation. "
            "You are {npc_name} with the following traits: {traits}. Generate a short, realistic dialogue."
        ) # Fallback

def get_dialogue_user_prompt() -> str:
    return get_prompt_from_db("DIALOGUE_USER_PROMPT_TEMPLATE") or \
           (
            "You are talking with {other_npc_name} who has these traits: {other_npc_traits}.\n"
            "You are currently in the {area_name}.\n"
            "Consider your personality and any relevant memories provided below.\n"
            "CONTEXT (your relevant memories):\n{memories}\n"
            "Write a brief, natural dialogue with just 3-4 exchanges between you and {other_npc_name}.\n"
            "Focus on what YOU would say, but include {other_npc_name}'s responses to create a coherent conversation.\n"
            "Make it feel realistic and appropriate to both your personalities."
        ) # Fallback

def get_dialogue_summary_system_prompt() -> str:
    return get_prompt_from_db("DIALOGUE_SUMMARY_SYSTEM_PROMPT") or \
            "You are an expert in summarizing conversations." # Fallback

def get_dialogue_summary_user_prompt() -> str:
    return get_prompt_from_db("DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE") or \
           '''You are {npc_name}.
Summarize the following conversation you had with {other_npc_name} in a single, concise sentence, from your perspective. Focus on the main topic or outcome.

Conversation:
{dialogue_transcript}

Your one-sentence summary:''' # Fallback


# Helper to format traits for prompts (can remain as is, or be moved if not prompt-specific)
def format_traits(traits_list: list[str]) -> str:
    if not traits_list:
        return "no specific traits listed"
    if len(traits_list) == 1:
        return traits_list[0]
    return ", ".join(traits_list[:-1]) + " and " + traits_list[-1]

# --- Example of how to use ---
# if __name__ == "__main__":
#     print("--- Plan System Prompt ---")
#     # Example: print(get_plan_system_prompt().format(name="Alice", sim_date="2023-10-28", traits_summary="curious and adventurous"))
#     print(get_plan_system_prompt()) # Print raw template
#     print("\n--- Plan User Prompt ---")
#     # Note: {retrieved_memories} would be dynamically filled by the application
#     # Example: print(get_plan_user_prompt().format(retrieved_memories="Woke up early. Saw a bird."))
#     plan_user_template = get_plan_user_prompt()
#     # If it needs formatting for {{retrieved_memories}}
#     # print(plan_user_template.format(retrieved_memories="Test memories"))
#     print(plan_user_template) # Print potentially placeholder-replaced template
#     print("\n--- Available Actions ---")
#     print(get_available_actions_list())

# The next step would be to find all usages of the old prompt constants and replace them with calls to these getter functions. 