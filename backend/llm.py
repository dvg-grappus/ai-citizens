import openai
from typing import Optional, List
from .config import get_settings

settings = get_settings()

# Initialize the OpenAI client (v1.x SDK)
# Ensure OPENAI_API_KEY is loaded by get_settings()
client = openai.OpenAI(
    api_key=settings.OPENAI_API_KEY
)

# The OpenAI v1.x client's chat.completions.create is synchronous by default.

def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 150, model: str = "gpt-4o-mini") -> Optional[str]:
    """Calls the OpenAI ChatCompletion API and returns the content of the first choice."""
    # print(f"--- Calling LLM ---")
    # print(f"SYSTEM: {system_prompt}")
    # print(f"USER: {user_prompt}")
    # print(f"MODEL: {model}, MAX_TOKENS: {max_tokens}")
    # print(f"-------------------")
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7, # A common default, can be tuned
        )
        
        if completion.choices and len(completion.choices) > 0:
            content = completion.choices[0].message.content
            # print(f"--- LLM Response ---")
            # print(content)
            # print(f"--------------------")
            return content.strip() if content else None
        else:
            print("LLM call returned no choices.")
            return None

    except openai.APIConnectionError as e:
        print(f"OpenAI APIConnectionError: {e}")
    except openai.RateLimitError as e:
        print(f"OpenAI RateLimitError: {e}")
    except openai.APIStatusError as e:
        print(f"OpenAI APIStatusError: {e.status_code} - {e.response}")
    except Exception as e:
        print(f"An unexpected error occurred while calling LLM: {e}")
    
    return None

# For asyncio compatibility if needed later (e.g. if retry_with_backoff is made async)
# import asyncio
# async def call_llm_async(...):
#    loop = asyncio.get_event_loop()
#    return await loop.run_in_executor(None, call_llm, ...)

