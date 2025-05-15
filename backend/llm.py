import openai
import time
from functools import wraps
from typing import Optional, List
from .config import get_settings

settings = get_settings()

# Initialize the OpenAI client (v1.x SDK)
# Ensure OPENAI_API_KEY is loaded by get_settings()
client = openai.OpenAI(
    api_key=settings.OPENAI_API_KEY
)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

def retry_with_backoff(func):
    """Decorator to retry a function with exponential backoff."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        retries = 0
        while retries < MAX_RETRIES:
            try:
                return await func(*args, **kwargs)
            except openai.APIError as e: # Catch specific OpenAI errors if possible, or general Exception
                retries += 1
                if retries >= MAX_RETRIES:
                    print(f"LLM call failed after {MAX_RETRIES} retries: {e}")
                    raise
                print(f"LLM call failed (attempt {retries}/{MAX_RETRIES}): {e}. Retrying in {RETRY_DELAY_SECONDS}s...")
                import asyncio # Local import for async sleep if not already global
                await asyncio.sleep(RETRY_DELAY_SECONDS) # Use asyncio.sleep for async functions
            except Exception as e:
                print(f"An unexpected error occurred during LLM call: {e}")
                raise # Re-raise unexpected errors immediately
        return None # Should not be reached if MAX_RETRIES is handled correctly
    return wrapper

# @retry_with_backoff # Apply decorator if needed for robustness, playbook doesn't specify async for this wrapper
# The original playbook snippet for llm.py doesn't show it as async,
# but if it's called from async functions (like in scheduler), it should be async.
# For now, making it synchronous as per implied playbook snippet structure, but OpenAI v1 client calls are often async.
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

if __name__ == '__main__':
    # Test call (ensure .env is loaded or OPENAI_API_KEY is set in environment)
    # This requires config.py to be runnable standalone or OPENAI_API_KEY to be set
    # For simplicity, this test won't run directly via playbook.
    # To test: set OPENAI_API_KEY env var and run `python -m backend.llm` from project root.
    print("Testing LLM call...")
    test_system = "You are a helpful assistant."
    test_user = "What is the capital of France?"
    response = call_llm(test_system, test_user, max_tokens=50)
    if response:
        print(f"Test LLM Response: {response}")
    else:
        print("Test LLM call failed.") 