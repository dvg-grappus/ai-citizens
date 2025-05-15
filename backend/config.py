from functools import lru_cache
# from pydantic import BaseSettings # This should be from pydantic_settings for Pydantic V2
from pydantic_settings import BaseSettings # Corrected import for Pydantic V2

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    OPENAI_API_KEY: str
    TICK_REAL_SEC: float = 1.0  # 1 real-sec
    TICK_SIM_MIN: int = 15       # Changed from 5 to 15 sim-min

    class Config:
        env_file = '.env' # Path relative to project root where uvicorn is run

@lru_cache()
def get_settings():
    return Settings()
