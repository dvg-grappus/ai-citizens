import os
from supabase import create_client, Client
from dotenv import load_dotenv
import ast

# Load environment variables from .env file
load_dotenv_success = load_dotenv()

print(f"load_dotenv() successful: {load_dotenv_success}")

# Supabase credentials from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") # Use anon key for client-side operations
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Use service role key for admin operations

print(f"Attempting to load from .env:")
print(f"  SUPABASE_URL found: {'Yes' if SUPABASE_URL else 'No'}")
print(f"  SUPABASE_SERVICE_ROLE_KEY found: {'Yes' if SUPABASE_KEY else 'No'}")

if not SUPABASE_URL or not SUPABASE_KEY:
    # print("Error: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env file.")
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env file.")
    if not load_dotenv_success:
        print("Hint: .env file might not have been found or loaded correctly.")
    print("Please ensure your .env file is in the project root and contains the correct key names and values.")
    exit(1)

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Test Supabase Connection ---
print("\n--- Testing Supabase Connection with Service Role Key ---")
try:
    print("Attempting to select from 'prompts' table as a connection test...")
    # Perform the select query
    test_response = supabase.table("prompts").select("name").limit(1).execute()

    print(f"Connection test raw response: {test_response}") # Log raw response

    # Check for explicit API error in the response object (e.g. PostgrestAPIError)
    if hasattr(test_response, 'error') and test_response.error:
        error_details = test_response.error
        print(f"!!! Supabase connection test FAILED with API error: {error_details} !!!")
        if hasattr(error_details, 'message'):
            print(f"Error message: {error_details.message}")
        if hasattr(error_details, 'code'):
            print(f"Error code: {error_details.code}")
        if hasattr(error_details, 'details'):
            print(f"Error details: {error_details.details}")
        if hasattr(error_details, 'hint'):
            print(f"Error hint: {error_details.hint}")
        exit(1)
    
    # If there's no explicit error object, check if data is as expected (a list for select queries)
    # response.data should be a list (empty if table is empty, or with data)
    if isinstance(test_response.data, list):
        print("Connection test SUCCEEDED. Able to query 'prompts' table (it might be empty).")
    else:
        # This case handles unexpected response structures where .error might not be set
        # but data is also not the expected list.
        print(f"Connection test FAILED or table is unqueryable. Response data is not a list as expected for a select query. Data: {test_response.data}")
        exit(1)

except Exception as e:
    # This catches other exceptions during the API call (network errors, client misconfig etc.)
    print(f"!!! Supabase connection test FAILED with an unhandled exception: {type(e).__name__} - {e} !!!")
    print("This could indicate an issue with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, network, or Supabase project status.")
    exit(1)
print("--- End of Supabase Connection Test ---\n")

# Prompts to be inserted (extracted manually from backend/prompts.py)
# Note: AVAILABLE_ACTIONS_STR is dynamically generated, so we'll store its template
# The application code will need to fetch AVAILABLE_ACTIONS_LIST and reconstruct this part of the prompt
# or store AVAILABLE_ACTIONS_LIST in another table. For now, let's keep it simple.

AVAILABLE_ACTIONS_LIST_FOR_DB = [
    "Sleep", "Brush Teeth", "Work", "Eat", "Walk",
    "Chat", "Relax", "Read", "Nap", "Explore",
    "Watch TV", "Relax on Couch", "Have Coffee"
]
AVAILABLE_ACTIONS_STR_FOR_DB = ", ".join(AVAILABLE_ACTIONS_LIST_FOR_DB)


prompts_data = [
    {
        "name": "PLAN_SYSTEM_PROMPT_TEMPLATE",
        "content": "You control NPC {name}. Today is {sim_date}. Your core traits are: {traits_summary}."
    },
    {
        "name": "AVAILABLE_ACTIONS_LIST", # Storing this as a special prompt
        "content": str(AVAILABLE_ACTIONS_LIST_FOR_DB) # Store as string representation of list
    },
    {
        "name": "PLAN_USER_PROMPT_TEMPLATE",
        "content": (
            f"Based on your personality and the following memories, produce an ordered list of actions (max 8) for today.\n"
            f"You MUST choose actions EXCLUSIVELY from the following list: {AVAILABLE_ACTIONS_STR_FOR_DB}.\n" # Use the hardcoded list for now
            f"Do NOT invent new actions. If you want to do something like 'Eat Breakfast', use the action 'Eat'.\n"
            f"Format each action as: HH:MM — <ACTION_TITLE_FROM_LIST>\n"
            f"Example: 09:00 — Work\n"
            f"Your day starts at 00:00 and ends at 23:59. Schedule a reasonable number of actions.\n"
            f"CONTEXT (recent memories, reflections, and relevant observations):\n{{retrieved_memories}}\n"
            f"TASK: Provide your schedule for today, using only the allowed action titles."
        )
    },
    {
        "name": "REFLECTION_SYSTEM_PROMPT_TEMPLATE",
        "content": "You are {npc_name}. Your task is to summarize the key events and your main thoughts for {sim_date} as exactly 1-3 bullet points. Each bullet point MUST start with '•' and end with [Importance: N] where N is 1-5."
    },
    {
        "name": "REFLECTION_USER_PROMPT_TEMPLATE",
        "content": (
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
        )
    },
    {
        "name": "DIALOGUE_SYSTEM_PROMPT_TEMPLATE",
        "content": (
            "You are an AI generating a brief, natural dialogue between two NPCs in a simulation. "
            "You are {npc_name} with the following traits: {traits}. Generate a short, realistic dialogue."
        )
    },
    {
        "name": "DIALOGUE_USER_PROMPT_TEMPLATE",
        "content": (
            "You are talking with {other_npc_name} who has these traits: {other_npc_traits}.\n"
            "You are currently in the {area_name}.\n"
            "Consider your personality and any relevant memories provided below.\n"
            "CONTEXT (your relevant memories):\n{memories}\n"
            "Write a brief, natural dialogue with just 3-4 exchanges between you and {other_npc_name}.\n"
            "Focus on what YOU would say, but include {other_npc_name}'s responses to create a coherent conversation.\n"
            "Make it feel realistic and appropriate to both your personalities."
        )
    },
    {
        "name": "DIALOGUE_SUMMARY_SYSTEM_PROMPT",
        "content": "You are an expert in summarizing conversations."
    },
    {
        "name": "DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE",
        "content": '''You are {npc_name}.
Summarize the following conversation you had with {other_npc_name} in a single, concise sentence, from your perspective. Focus on the main topic or outcome.

Conversation:
{dialogue_transcript}

Your one-sentence summary:'''
    }
]

def populate_prompts():
    print("Populating prompts table...")
    for prompt in prompts_data:
        try:
            # supabase-py v2.x .upsert().execute() returns a PostgrestAPIResponse object directly.
            # It is not a tuple like (data_response, count_response) unless specific count options are used.
            api_response = supabase.table("prompts").upsert(prompt).execute()

            if hasattr(api_response, 'error') and api_response.error:
                print(f"Error upserting {prompt['name']}: {api_response.error}")
                if hasattr(api_response.error, 'message'):
                    print(f"  Error message: {api_response.error.message}")
                if hasattr(api_response.error, 'details'):
                    print(f"  Error details: {api_response.error.details}")
                if hasattr(api_response.error, 'hint'):
                    print(f"  Error hint: {api_response.error.hint}")
            elif api_response.data: # Data should be a list of the upserted records
                 print(f"Upserted: {prompt['name']}") # (Data: {api_response.data})") # Optional: log data
            else:
                # This case might occur if RLS prevents insert/update and returns empty data without an error object (less common with service key)
                # Or if the upsert resulted in no change and the API returns empty data by design for such cases.
                print(f"Upsert for {prompt['name']} resulted in no data being returned and no explicit error. Response: {api_response}")
        except Exception as e:
            print(f"Exception during upsert of {prompt['name']}: {type(e).__name__} - {e}")

    # Special handling for AVAILABLE_ACTIONS_LIST and PLAN_USER_PROMPT_TEMPLATE
    # We need to ensure the application code can reconstruct the dynamic parts if needed
    # For now, we've stored a static version.
    # The application code should fetch 'AVAILABLE_ACTIONS_LIST' and parse it.
    # Then, it should format 'PLAN_USER_PROMPT_TEMPLATE' by replacing the placeholder for AVAILABLE_ACTIONS_STR.

    print("Finished populating prompts table.")

if __name__ == "__main__":
    populate_prompts() 