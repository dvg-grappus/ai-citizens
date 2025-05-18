# backend/prompts.py

# 6.1 Daily Plan
# SYSTEM: You control NPC {{name}}. Today is {{sim_date}}.
# CONTEXT (memories):
# {{retrieved_memories}}
# TASK: Produce an ordered list of actions (max 8) for the day.
# FORMAT:
# 1. HH:MM — <ACTION_ID>
# ...
PLAN_SYSTEM_PROMPT_TEMPLATE = "You control NPC {name}. Today is {sim_date}. Your core traits are: {traits_summary}."

# Define available actions for the LLM to choose from
AVAILABLE_ACTIONS_LIST = [
    "Sleep", "Brush Teeth", "Work", "Eat", "Walk", 
    "Chat", "Relax", "Read", "Nap", "Explore",
    "Watch TV", "Relax on Couch", "Have Coffee"
]
AVAILABLE_ACTIONS_STR = ", ".join(AVAILABLE_ACTIONS_LIST)

PLAN_USER_PROMPT_TEMPLATE = (
    f"Based on your personality and the following memories, produce an ordered list of actions (max 8) for today.\n"
    f"You MUST choose actions EXCLUSIVELY from the following list: {AVAILABLE_ACTIONS_STR}.\n"
    f"Do NOT invent new actions. If you want to do something like \'Eat Breakfast\', use the action \'Eat\'.\n"
    f"Format each action as: HH:MM — <ACTION_TITLE_FROM_LIST>\n"
    f"Example: 09:00 — Work\n"
    f"Your day starts at 00:00 and ends at 23:59. Schedule a reasonable number of actions.\n"
    f"CONTEXT (recent memories, reflections, and relevant observations):\n{{retrieved_memories}}\n"
    f"TASK: Provide your schedule for today, using only the allowed action titles."
)

# 6.2 Observation Log Row (This is a direct string format, not a prompt template for LLM)
# Example: f"07:25 — Saw {other} enter {area}."

# 6.3 Reflection
# SYSTEM: Summarise key events for {{sim_date}} in <=3 lines.
# CONTEXT: {{retrieved_memories}}
# OUTPUT: • … • …
# Also assign Importance 1—5 to each line.
REFLECTION_SYSTEM_PROMPT_TEMPLATE = "You are {npc_name}. Your task is to summarize the key events and your main thoughts for {sim_date} as exactly 1-3 bullet points. Each bullet point MUST start with '•' and end with [Importance: N] where N is 1-5."
REFLECTION_USER_PROMPT_TEMPLATE = (
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

# 6.4 Dialogue Generation
# SYSTEM: Generate {{turns}} lines of dialogue between
# {{npcA}} ({{traits}}) & {{npcB}} ({{traits}})
# CONTEXT: {{retrieved_memories}}
# TOPIC: {{trigger}}
# FORMAT:
# NPC_A: …
# NPC_B: …
DIALOGUE_SYSTEM_PROMPT_TEMPLATE = (
    "You are an AI generating a brief, natural dialogue between two NPCs in a simulation. "
    "You are {npc_name} with the following traits: {traits}. Generate a short, realistic dialogue."
)
DIALOGUE_USER_PROMPT_TEMPLATE = (
    "You are talking with {other_npc_name} who has these traits: {other_npc_traits}.\n"
    "You are currently in the {area_name}.\n"
    "Consider your personality and any relevant memories provided below.\n"
    "CONTEXT (your relevant memories):\n{memories}\n"
    "Write a brief, natural dialogue with just 3-4 exchanges between you and {other_npc_name}.\n"
    "Focus on what YOU would say, but include {other_npc_name}'s responses to create a coherent conversation.\n"
    "Make it feel realistic and appropriate to both your personalities."
)

# Helper to format traits for prompts
def format_traits(traits_list: list[str]) -> str:
    if not traits_list: 
        return "no specific traits listed"
    if len(traits_list) == 1:
        return traits_list[0]
    return ", ".join(traits_list[:-1]) + " and " + traits_list[-1]

DIALOGUE_SUMMARY_SYSTEM_PROMPT = "You are an expert in summarizing conversations."
DIALOGUE_SUMMARY_USER_PROMPT_TEMPLATE = """You are {npc_name}.
Summarize the following conversation you had with {other_npc_name} in a single, concise sentence, from your perspective. Focus on the main topic or outcome.

Conversation:
{dialogue_transcript}

Your one-sentence summary:""" 