import asyncio
import os
import sys

# Add the project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.scheduler import run_nightly_reflection, get_current_sim_time_and_day

async def test():
    # Get current simulation time
    time_data = await get_current_sim_time_and_day()
    current_day = time_data["day"]
    sim_min = time_data["sim_min"]
    
    print(f"Current simulation state: Day {current_day}, Time {sim_min}")
    
    # Run reflection for the current day
    print(f"Running reflection for Day {current_day}")
    await run_nightly_reflection(current_day, sim_min)
    
    print("Reflection test completed!")

if __name__ == "__main__":
    asyncio.run(test()) 