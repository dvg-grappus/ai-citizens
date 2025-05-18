# Artificial Citizens – Bolt Implementation Playbook

*Step‑by‑step commands for Bolt to execute the NPC simulator MVP with zero ambiguity.*

---

## Phase 0 — Infra & Keys (≈30 min)

> **Skip GitHub.** Bolt will run everything locally for now; Vercel deploy steps appear later.

| Step | Tool                  | Exact Action                                                                                            |
| ---- | --------------------- | ------------------------------------------------------------------------------------------------------- |
| 0.1  | **Supabase**          | Create project `artificial-citizens`. Copy `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`. |
| 0.2  | **OpenAI Dashboard**  | Generate `OPENAI_API_KEY` with GPT‑4o + embeddings enabled.                                             |
| 0.3  | **Local `.env` file** | Add:<br>`SUPABASE_URL=…`<br>`SUPABASE_ANON_KEY=…`<br>`SUPABASE_SERVICE_KEY=…`<br>`OPENAI_API_KEY=…`     |

No other infra required for the prototype.

---

## Phase 1 — Data Layer & Supabase Schema (≈2 hrs)

### 1.1 Execute Full SQL Migration

Open Supabase → SQL editor → paste and run:

```sql
-- Areas
create table area (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  bounds jsonb not null
);
-- Objects
create table object (
  id uuid primary key default gen_random_uuid(),
  area_id uuid references area(id) on delete cascade,
  name text not null,
  state text default 'free',
  pos jsonb not null
);
-- NPCs
create table npc (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  traits text[] not null,
  backstory text,
  relationships jsonb default '{}',
  spawn jsonb not null,
  energy int default 100,
  current_action_id uuid,
  wander_probability float default 0.4
);
-- Action definitions
create table action_def (
  id uuid primary key default gen_random_uuid(),
  title text,
  emoji text,
  base_minutes int,
  preconds text[],
  post_effects text[]
);
-- Action instances
create table action_instance (
  id uuid primary key default gen_random_uuid(),
  npc_id uuid references npc(id) on delete cascade,
  def_id uuid references action_def(id),
  object_id uuid references object(id),
  start_min int,
  duration_min int,
  status text check (status in ('queued','active','done'))
);
-- Plans
create table plan (
  id uuid primary key default gen_random_uuid(),
  npc_id uuid references npc(id) on delete cascade,
  sim_day int,
  actions uuid[]
);
-- Enable pgvector & memories
create extension if not exists vector;
create table memory (
  id uuid primary key default gen_random_uuid(),
  npc_id uuid references npc(id) on delete cascade,
  sim_min int,
  kind text check (kind in ('plan','obs','reflect')),
  content text,
  importance int,
  embedding vector(1536)
);
create index on memory using ivfflat (embedding vector_cosine_ops) with (lists = 100);
-- Encounters
create table encounter (
  id uuid primary key default gen_random_uuid(),
  tick int,
  actor_id uuid references npc(id),
  target_id uuid references npc(id),
  description text
);
-- Dialogues
create table dialogue (
  id uuid primary key default gen_random_uuid(),
  npc_a uuid references npc(id),
  npc_b uuid references npc(id),
  start_min int,
  end_min int
);
create table dialogue_turn (
  id uuid primary key default gen_random_uuid(),
  dialogue_id uuid references dialogue(id) on delete cascade,
  speaker_id uuid references npc(id),
  sim_min int,
  text text
);
-- Events
create table sim_event (
  id uuid primary key default gen_random_uuid(),
  type text,
  start_min int,
  end_min int,
  metadata jsonb
);
-- Environment & clock
create table environment (
  id int primary key check (id=1),
  day int,
  speed int
);
insert into environment(id, day, speed) values (1,1,12);
create table sim_clock (
  id int primary key check (id=1),
  sim_min int,
  speed int
);
insert into sim_clock(id, sim_min, speed) values (1,0,12);
```

### 1.2 Disable Row‑Level Security

Supabase → Table → Auth → toggle off RLS for *all* tables. (Re‑enable after demo.)

### 1.3 Seed Data Script

Create `scripts/seed.ts` (Run with `pnpm ts-node scripts/seed.ts`):

```ts
import { createClient } from '@supabase/supabase-js';
const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_KEY!);

// Insert Areas
const { data: areas } = await supabase.from('area').insert([
  { name:'Bedroom', bounds:{x:0,y:0,w:200,h:200} },
  { name:'Office',  bounds:{x:210,y:0,w:200,h:200} },
  { name:'Bathroom',bounds:{x:0,y:210,w:200,h:200} },
  { name:'Lounge',  bounds:{x:210,y:210,w:200,h:200} }
]).select();

// Helper getId
const id = (name:string)=>areas?.find(a=>a.name===name)?.id!;

// Insert Objects
await supabase.from('object').insert([
  { area_id:id('Bedroom'), name:'Bed', state:'free', pos:{x:50,y:50} },
  { area_id:id('Bathroom'), name:'Toothbrush', state:'free', pos:{x:30,y:60} }
]);

// Insert ActionDefs
await supabase.from('action_def').insert([
  { title:'Sleep', emoji:'💤', base_minutes:480 },
  { title:'Brush Teeth', emoji:'🪥', base_minutes:5 },
  { title:'Work', emoji:'💻', base_minutes:480 }
]);

// Insert two sample NPCs
await supabase.from('npc').insert([
  { name:'Alice', traits:['friendly','curious'], backstory:'Likes coffee.', relationships:{}, spawn:{x:20,y:20,areaId:id('Bedroom')}, wander_probability: 0.4 },
  { name:'Bob', traits:['lazy','grumpy'], backstory:'Hates Mondays.', relationships:{}, spawn:{x:240,y:30,areaId:id('Office')}, wander_probability: 0.2 }
]);
```

### 1.4 Generate Supabase Types for TypeScript

```bash
npx supabase gen types typescript --project-id <project-id> > ac-web/src/types/supabase.ts
```

Commit the generated file to version control (or keep in Bolt workspace).

---

## Next → Phase 2 — FastAPI Backend Skeleton

*Reply **continue** for exact step‑by‑step FastAPI setup.*

---

## Phase 2 — Backend Implementation (FastAPI) *(≈4-6 hrs)*

**Goal:** Develop a modular FastAPI backend that manages the simulation lifecycle, NPC states, actions, interactions, and serves data to the frontend via HTTP and WebSockets.

### 2.1 Project Structure Setup

1.  Ensure you have a main project directory (e.g., `ai-citizens`).
2.  Inside this, create a `backend/` directory. This will house all Python backend code.
3.  Create an `ac-web/` directory for the React frontend (details in Phase 3).

### 2.2 Python Environment & Dependencies

1.  Navigate to the root project directory.
2.  It's recommended to use a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  Create a `requirements.txt` file in the root directory with the following content:
    ```txt
    fastapi
    uvicorn[standard]
    supabase
    openai
    python-dotenv
    httpx
    ```
4.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### 2.3 Core Backend Modules

Create the following Python files within the `backend/` directory. Initial simple versions are described; they will be fleshed out with specific logic.

*   **`config.py`**: Manages environment variables and settings.
    ```python
    from pydantic_settings import BaseSettings
    import os
    from dotenv import load_dotenv

    load_dotenv() # Load .env file from project root

class Settings(BaseSettings):
        OPENAI_API_KEY: str = "your_openai_api_key"
        SUPABASE_URL: str = "your_supabase_url"
        SUPABASE_SERVICE_KEY: str = "your_supabase_service_key"

    class Config:
            env_file = "../.env" # Points to .env in the project root
            env_file_encoding = 'utf-8'
            extra = 'ignore' 

    _settings = None

def get_settings():
        global _settings
        if _settings is None:
            _settings = Settings()
        return _settings
    ```
    *Note: Ensure your `.env` file is in the project root, not in `backend/`.*

*   **`models.py`**: (Optional but good practice) Pydantic models for data structures if not directly using dictionaries or Supabase types.
    *Example (can be expanded as needed):*
    ```python
from pydantic import BaseModel
    from typing import List, Optional, Dict

    class NPC(BaseModel):
        id: str
        name: str
        # ... other NPC fields ...

    class Area(BaseModel):
        id: str
        name: str
        bounds: Dict
        # ... other area fields ...
    ```

*   **`services.py`**: Contains functions for direct Supabase interactions (CRUD operations for NPCs, Objects, Areas, etc.). Includes `execute_supabase_query` helper with retry logic.
    *   *Key functions*: `get_npc_by_id`, `save_npc`, `get_object_by_id`, `get_area_details`, `update_npc_current_action`, `get_all_npcs_data_for_tick` (to fetch all relevant NPC data for `scheduler`), etc.
    *   Implements `db_semaphore` for concurrent DB operation limiting.

*   **`memory_service.py`**: Handles creation, retrieval, and embedding of NPC memories.
    *   *Key functions*: `save_memory_batch`, `get_recent_memories_for_npc`, `create_memory_embedding`.

*   **`planning_and_reflection.py`**: Manages NPC daily planning and nightly reflections using OpenAI.
    *   *Key functions*: `run_daily_planning`, `run_nightly_reflection`.
    *   Uses `prompts.py` for LLM prompt templates.

*   **`prompts.py`**: Stores all prompt templates for OpenAI interactions (planning, reflection, dialogue).

*   **`dialogue_service.py`**: Manages pending dialogue requests and processes them using OpenAI.
    *   *Key functions*: `add_pending_dialogue_request`, `process_pending_dialogues`.
    *   Tracks `npc_dialogue_cooldown_until`.

*   **`websocket_utils.py`**: Handles WebSocket connections and message broadcasting.
    *   *Key functions*: `register_ws`, `unregister_ws`, `broadcast_ws_message`.
    *   Maintains `_ws_clients` list.

*   **`scheduler.py`**: The core simulation engine.
    *   Manages simulation time (`sim_tick_data`).
    *   `advance_tick()`: Main function called periodically. Fetches NPC data, runs `update_npc_actions_and_state` for each NPC, processes dialogues, handles planning/reflection triggers.
    *   `update_npc_actions_and_state()`: Determines NPC movement (action-driven or wander), updates positions, handles energy, and checks for dialogue conditions.
    *   Integrates with all other services (`services`, `memory_service`, `dialogue_service`, `planning_and_reflection`).

*   **`main.py`**: FastAPI application entry point. Defines API endpoints and WebSocket route.
    *   Initializes Supabase client and settings.
    *   Endpoints:
        *   `/ws`: WebSocket endpoint for real-time updates.
        *   `/api/state`: Gets the current simulation state (NPCs, areas, objects, clock).
        *   `/api/npc_details/{npc_id}`: Gets detailed information for a specific NPC.
        *   `/api/reset_simulation_day0`: Resets simulation to initial state (Day 0).
        *   `/api/reset_simulation_to_end_of_day1`: Resets to a specific point after Day 1 reflections.
        *   `/api/start_simulation`, `/api/pause_simulation`, `/api/set_speed`.
    *   Manages the main simulation loop (e.g., using `asyncio.create_task` for `scheduler.start_simulation_loop`).

### 2.4 Backend Initialization & Running

1.  **Environment Variables**: Ensure your `.env` file in the project root contains `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `OPENAI_API_KEY`.

2.  **API Endpoints & WebSocket**: Implement the basic structure for the endpoints and WebSocket connection in `backend/main.py`.
    ```python
    # backend/main.py (simplified example)
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    import asyncio

    from .config import get_settings
    from . import scheduler, websocket_utils, services # etc.

    app = FastAPI()
settings = get_settings()

    # CORS middleware (adjust origins as needed for development/production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Example: ["http://localhost:5173"]
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        print("INFO:     Backend startup")
        # Initialize Supabase client (typically done in services.py or globally)
        # services.initialize_supabase_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        # Start the simulation loop if it doesn't auto-start
        asyncio.create_task(scheduler.start_simulation_loop()) 
        print("INFO:     Simulation loop initiated")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket_utils.register_ws(websocket)
        try:
    while True:
                await websocket.receive_text() # Keep connection alive
        except WebSocketDisconnect:
            websocket_utils.unregister_ws(websocket)

    # Define other HTTP endpoints like /api/state, /api/npc_details/{npc_id}, etc.
    # These will call functions from scheduler.py, services.py, etc.

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)
```

3.  **Running the Backend**:
    From the project root directory (containing `backend/` and `ac-web/`):
```bash
uvicorn backend.main:app --reload --port 8000
```
    You should see Uvicorn startup messages and any print statements from your `startup_event`.

### 2.5 Key Logic Implementation (High-Level)

*   **NPC Movement**: Implement in `scheduler.py` (`update_npc_actions_and_state`).
    *   If NPC has an active action targeting an object, move towards a random point within the object's area bounds.
    *   Otherwise, perform same-area wander: with `wander_probability` (from DB, default 0.4), pick a random point within `EXPECTED_AREA_WIDTH`/`HEIGHT` (400x300) centered on the current area, ensuring it's within the general world canvas. Update position if the new point is significantly different.
*   **Dialogue**: `dialogue_service.py` uses OpenAI to generate dialogue when NPCs are close. `scheduler.py` checks proximity and calls `add_pending_dialogue_request`.
*   **Planning/Reflection**: `planning_and_reflection.py` uses OpenAI for daily plans and nightly reflections, triggered by `scheduler.py` at appropriate sim times.
*   **State Broadcasting**: `websocket_utils.broadcast_ws_message` is called by `scheduler.py` (e.g., after `advance_tick`) to send updated state to connected frontend clients.

This phase focuses on getting the backend structure, core services, and the main simulation loop operational. Detailed logic for each function (prompts, specific game mechanics) will be refined in subsequent phases or was part of the iterative development.

---

Next → Phase 3 — Vite/React Frontend Skeleton & Basic UI

---

## Phase 3 — Frontend Implementation (Vite + React + TypeScript + Konva) *(≈6-8 hrs)*

**Goal:** Create a web interface using Vite, React, TypeScript, and Konva to visualize the simulation. This includes rendering areas, NPCs, displaying a clock, logs, and providing an NPC detail modal.

### 3.1 Frontend Project Setup (in `ac-web/` directory)

1.  Navigate to the project root and then into the `ac-web/` directory. If it doesn't exist, create it.
    ```bash
    cd ac-web 
    ```
2.  Initialize a Vite + React + TypeScript project (if not already done):
    ```bash
    pnpm create vite . --template react-ts
    ```
3.  Install necessary dependencies:
    ```bash
    pnpm install konva react-konva zustand date-fns # zustand for state, date-fns for time formatting
    # We use native WebSocket, so socket.io-client is not needed.
    ```
4.  **`.gitignore`**: Ensure `.env.*` and `node_modules/`, `dist/` are in `ac-web/.gitignore`.
5.  **Supabase Types**: If not done in Phase 1, generate Supabase types (ensure you are in the project root for this command, then move back to `ac-web`):
    ```bash
    # From project root
    npx supabase gen types typescript --project-id <your-project-id> > ac-web/src/types/supabase.ts 
    ```

### 3.2 Main Application Structure (`ac-web/src/`)

*   **`main.tsx`**: Entry point. Renders `<App />`. Remove any `App.css` import.
*   **`App.tsx`**: Main component.
    *   Sets up WebSocket connection to `ws://localhost:8000/ws`.
    *   Fetches initial simulation state (`/api/state`) on load.
    *   Manages global state (e.g., using Zustand) for NPCs, areas, clock, logs, selected NPC for modal.
    *   Renders `CanvasStage.tsx`, log panel, clock, and `NPCDetailModal.tsx`.
*   **`vite-env.d.ts`**: Default Vite client types.
*   **`index.html`**: Main HTML file. Update title if desired.
*   **`public/`**: Static assets like `vite.svg` (can be kept or removed).
*   **`assets/`**: Project-specific static assets. `react.svg` can be deleted if unused.

### 3.3 Core UI Components (`ac-web/src/components/`)

*   **`CanvasStage.tsx`**: 
    *   Uses `react-konva` to render the main simulation view.
    *   Renders area rectangles based on data from the backend.
    *   Renders an `<NPCDot />` component for each NPC.
    *   Handles click events on NPCs to open the detail modal.
*   **`NPCDot.tsx`**: 
    *   Represents an individual NPC on the canvas (e.g., a circle with a label).
    *   Manages its own position and smoothly animates to new positions received via WebSocket updates.
    *   `useEffect` hooks for: 
        1.  Initial placement (deps: `npc.id`, `isValidPosition`).
        2.  Animated movement for subsequent updates (deps: `npc.x`, `npc.y`, `npc.current_action_emoji`).
    *   Uses a `MARGIN` of 50 for label visibility when calculating screen position from world coordinates.
    *   Includes idle "jitter" animation logic.
*   **`NPCDetailModal.tsx`**: 
    *   Modal dialog to display detailed information about a selected NPC.
    *   Fetches detailed NPC data from `/api/npc_details/{npc_id}` when an NPC is selected.
    *   Uses `ModalHeader.tsx` and tab components.
    *   No "Refresh" button; data updates via WebSocket and re-selection if necessary.
*   **`ModalHeader.tsx`**: Displays NPC name and a close button for the modal.
*   **`npc_detail_modal_tabs/`** (directory for tab components):
    *   **`ActionsTab.tsx`**: Displays NPC's past and current actions.
    *   **`ReflectionsTab.tsx`**: Displays NPC's reflections.
    *   **`PlanTab.tsx`**: Displays NPC's current day plan.
    *   **`MemoryStreamTab.tsx`**: Displays a stream of the NPC's recent memories.
*   **`NPCDetailModal.styles.ts`**: Contains `styled-components` or CSS-in-JS styles specifically for `NPCDetailModal.tsx` and its sub-components, moving inline styles out.

### 3.4 Styling and Assets

*   **Global Styles**: `App.css` and its imports in `main.tsx` and `App.tsx` should be removed. Basic layout can be achieved with inline styles, component-specific style files, or a global style solution like `styled-components` if preferred for larger styling needs.
*   **Component Styles**: Inline styles or dedicated `.styles.ts` files (as with `NPCDetailModal.styles.ts`) are encouraged for component encapsulation.

### 3.5 State Management (e.g., Zustand)

*   Create a store (e.g., `ac-web/src/store.ts`) to manage shared frontend state:
    *   NPC list, Area list, Object list
    *   Simulation clock (day, time string)
    *   Log messages
    *   Currently selected NPC ID for the detail modal
    *   Modal visibility state
*   Connect components to this store to react to state changes and dispatch actions.

### 3.6 Verification

1.  Ensure the backend (Phase 2) is running on `http://localhost:8000`.
2.  From the `ac-web/` directory, run the frontend development server:
    ```bash
    pnpm dev
    ```
3.  Open your browser to the address provided by Vite (usually `http://localhost:5173`).
4.  **Expected Initial View:**
    *   A canvas displaying the defined areas (e.g., four quadrants).
    *   NPC dots appearing in their initial positions, labeled with name/emoji.
    *   A clock display (e.g., "Day 1 - 00:00").
    *   A panel for logs.
5.  **Functionality Checks:**
    *   NPC dots should move and update their emojis based on backend WebSocket messages.
    *   The clock should update in sync with the backend.
    *   The log panel should display messages from the backend (e.g., "Tick processed", NPC actions).
    *   Clicking an NPC dot should open the `NPCDetailModal` showing that NPC's details.
    *   The modal should have tabs for Actions, Reflections, Plan, and Memory Stream, populating with data.

---

Type **continue** for **Phase 4 — GPT Integration: Planning, Reflection, and Memory**.

---

## Phase 4 — GPT Integration: Planning, Reflection, and Memory *(≈5-7 hrs)*

**Goal:** Enable NPCs to generate daily plans, reflect on their days, and store these as well as observations into a searchable memory stream, all powered by OpenAI's GPT models.

### 4.1 Dependencies

Ensure `openai` and `tiktoken` (for token counting, often a dependency or good practice for managing context windows) are in your `requirements.txt` and installed:
```txt
# In requirements.txt (add if not present)
openai==1.13.3 # Or a more recent compatible version
tiktoken
```
Then `pip install -r requirements.txt`.

### 4.2 Core Modules Involved

*   **`backend/prompts.py`**: This file will store all multi-line string templates for interacting with the LLM. Examples:
    *   `PLAN_PROMPT_TEMPLATE`: Takes NPC details, current date, and retrieved relevant memories. Instructs the LLM to return a list of timed actions for the day.
    *   `REFLECTION_PROMPT_TEMPLATE`: Takes an NPC's memories from the day. Instructs the LLM to generate a few insightful reflections, each with an importance score (1-5).
    *   `OBSERVATION_INSIGHT_PROMPT_TEMPLATE` (Optional): If observations need more than just factual logging, this could be used to generate richer observations or infer NPC thoughts.
    *   `DIALOGUE_PROMPT_TEMPLATE` (Covered also in Dialogue Phase): For generating conversational exchanges.

*   **`backend/planning_and_reflection.py`**: This module houses the primary logic for GPT-driven planning and reflection.
    *   Contains functions like `run_daily_planning(npc_id: str, npc_name: str, current_sim_day: int)` and `run_nightly_reflection(npc_id: str, npc_name: str, current_sim_day: int)`.
    *   These functions will:
        1.  Call `memory_service.retrieve_relevant_memories(...)` to get context for the LLM.
        2.  Format the appropriate prompt from `prompts.py` with the NPC's data and retrieved memories.
        3.  Make calls to an OpenAI LLM (e.g., GPT-4o-mini, GPT-4) using the `openai` SDK. It's good practice to wrap these calls in a helper that handles retries, timeouts, and API key management (via `config.py`).
        4.  Parse the LLM's response (e.g., plan items, reflection statements with importance scores).
        5.  Use `memory_service.save_memory_batch(...)` to store the generated plan or reflections as memories with `kind='plan'` or `kind='reflect'` respectively. The `split('\n')` (not `split('''\n''')`) method should be used for parsing multi-line LLM outputs.

*   **`backend/memory_service.py`**: Responsible for all interactions with the `memory` table.
    *   `save_memory_batch(memories: List[Dict])`: Saves multiple memory entries. Each memory should include `npc_id`, `sim_min`, `kind` (`'obs'`, `'plan'`, `'reflect'`), `content`, `importance`, and an `embedding`.
    *   `create_memory_embedding(text: str)`: Uses OpenAI's embedding API to generate a vector for a given text. This should be called before saving any memory that needs to be retrievable by similarity.
    *   `retrieve_relevant_memories(npc_id: str, query_text: str, limit: int)`: Fetches memories relevant to a query text, typically using cosine similarity on embeddings, possibly combined with recency and importance scores.

*   **`backend/scheduler.py`**: Orchestrates the simulation.
    *   At the start of each simulated day (e.g., `sim_min % 1440 == 0`), it iterates through NPCs and calls `planning_and_reflection.run_daily_planning(...)` for each.
    *   At the end of each simulated day (e.g., just before the clock resets for the next day or `sim_min % 1440 == (1440 - tick_interval)`), it calls `planning_and_reflection.run_nightly_reflection(...)` for each NPC.
    *   During `advance_tick` or related action processing, generates observation memories (e.g., "Alice saw Bob in the Lounge", "Alice started cooking") and saves them via `memory_service.save_memory_batch(...)` with `kind='obs'` and an appropriate importance score (e.g., 1 for simple observations).

### 4.3 Implementation Steps

1.  **Prompts**: Define your initial prompt templates in `backend/prompts.py`.
2.  **Memory Service**: Implement the core functions in `backend/memory_service.py`, ensuring embeddings are generated and stored for searchable memories.
3.  **Planning & Reflection Service**: Implement `run_daily_planning` and `run_nightly_reflection` in `backend/planning_and_reflection.py`. Include LLM call logic (with error handling/retries) and parsing of results. Ensure reflections are saved with `kind='reflect'`.
4.  **Scheduler Integration**: Modify `backend/scheduler.py` to trigger planning and reflection at the correct simulation times. Implement logic for creating and saving observation memories during tick processing.
5.  **Configuration**: Ensure `OPENAI_API_KEY` is correctly set up in your `.env` file and loaded via `backend/config.py`.

### 4.4 Verification & Testing

1.  **Seed NPCs**: Ensure you have at least one or two NPCs in your database (via Phase 1 seed script).
2.  **Run Backend**: Start the FastAPI application.
3.  **Simulate Time**: Allow the simulation to run through at least one full day cycle.
    *   Observe logs for calls to planning and reflection functions.
    *   Check the `plan` table (or `memory` table with `kind='plan'`) after the first sim-midnight to see if daily plans are generated.
    *   Check the `memory` table for `kind='obs'` entries being created as NPCs act and move.
    *   Check the `memory` table for `kind='reflect'` entries after the end of the first sim-day, ensuring they have importance scores.
4.  **Database Inspection**: Directly query your Supabase tables (`npc`, `plan`, `memory`, `action_instance`) to verify that data is being created and linked correctly.
5.  **Frontend Check**: If the frontend is connected, observe if NPC actions roughly correspond to their generated plans. The NPC Detail Modal should display plans and reflections.

This phase integrates the "intelligence" into your NPCs, allowing them to form plans and reflect on their experiences, creating a richer simulation.

---

Type **continue** for **Phase 5 — Dialogue Workflow & (Optional) Random Challenges**.

---

## Phase 5 — Dialogue Workflow & (Optional) Random Challenges *(≈4-6 hrs)*

**Purpose:** Enable NPCs to engage in dialogues when they meet, and optionally, react to dynamic global events, making the simulation more interactive.

### 5.1 Dialogue Initiation (in `backend/scheduler.py`)

1.  **Encounter Detection**: During `update_npc_actions_and_state()` (or a dedicated function called by `advance_tick`), after NPCs have moved:
    *   For each pair of NPCs, check if they are in the same area and if their proximity is below a certain threshold (e.g., < 30-50 pixels).
    *   Check if they are not already in an active dialogue and not on cooldown for dialogue with each other.
2.  **Request Dialogue**: If conditions are met and a random chance (e.g., 30%) passes:
    *   Call `dialogue_service.add_pending_dialogue_request(npc_a_id, npc_b_id, current_sim_time)`.

### 5.2 Dialogue Processing (in `backend/dialogue_service.py`)

This service manages the lifecycle of dialogues.

*   **`pending_dialogue_requests`**: A queue or list holding `(npc_a_id, npc_b_id, sim_time)` tuples.
*   **`npc_dialogue_cooldown_until`**: A dictionary like `{frozenset({npc_id1, npc_id2}): cooldown_end_sim_time}` to manage cooldowns. The `DIALOGUE_COOLDOWN_MINUTES` is set to 360 (6 hours).
*   **`process_pending_dialogues()`**: This function is called by `scheduler.py` during `advance_tick`.
    1.  Iterates through `pending_dialogue_requests`.
    2.  For each request, if NPCs are still available and not on cooldown:
        *   Retrieve necessary context for the dialogue (e.g., traits, recent memories for both NPCs via `memory_service.retrieve_relevant_memories`).
        *   Format a prompt using `DIALOGUE_PROMPT_TEMPLATE` from `prompts.py`.
        *   Call the LLM to generate a multi-turn dialogue (e.g., 3 exchanges).
        *   Parse the LLM response into individual turns (`speaker_id`, `text`).
        *   Save the dialogue interaction: create a `dialogue` entry and multiple `dialogue_turn` entries in the database (via `services.py` or direct Supabase calls within `dialogue_service`).
        *   Save each turn as an observation memory for both participating NPCs using `memory_service.save_memory_batch()` (`kind='obs'`, importance e.g., 2).
        *   Set their dialogue cooldown: `npc_dialogue_cooldown_until[frozenset({npc_a_id, npc_b_id})] = current_sim_time + DIALOGUE_COOLDOWN_MINUTES`.
        *   Determine if NPCs need replanning after dialogue (e.g., based on dialogue content or a fixed probability like 20%). Return a list of NPC IDs that need to replan.
    3.  Clear processed requests from `pending_dialogue_requests`.

### 5.3 Post-Dialogue Behavior (in `backend/scheduler.py`)

*   After `dialogue_service.process_pending_dialogues()` returns, if any NPC IDs are marked for replanning:
    *   Call `planning_and_reflection.run_daily_planning()` for those NPCs to adjust their plans for the remainder of the day.
    *   Otherwise, NPCs resume their queued actions.

### 5.4 Frontend: Displaying Dialogues

*   **Log Panel**: Dialogue turns should appear in the main log panel as they happen.
*   **Speech Bubbles (Optional Enhancement)**: When a dialogue turn occurs, the frontend could briefly display the text as a speech bubble above the speaking NPC's dot on the canvas. This would require WebSocket messages specifically for active dialogue lines.
*   **NPC Detail Modal**: The `MemoryStreamTab` should show dialogue lines as part of an NPC's memory.

--- 
*(The following "Random Challenges" section is optional and describes a potential future enhancement. The core refactoring focused on the dialogue system above.)*

### 5.5 (Optional) Random Challenge Generator

This system would introduce global events that NPCs might react to.

*   **Event Definitions**: Define a set of possible random events (e.g., `fire_alarm`, `pizza_drop`, `power_cut`) with their effects, target areas/NPCs, and display messages.
*   **Triggering**: In `scheduler.py` (e.g., in `advance_tick` or a separate function called by the main loop), have a small probability (e.g., 5% per tick or per few minutes) to trigger a random event.
*   **Implementation**:
    1.  When an event triggers, store it in a `sim_event` table (type, start/end time, metadata).
    2.  Broadcast the event via WebSocket so the frontend can display a banner/alert.
    3.  NPCs, in their `update_npc_actions_and_state` logic, would check for active `sim_event`s relevant to them (e.g., affecting their area or matching their traits/goals).
    4.  If an event is relevant, they might override their current plan to react (e.g., evacuate, go to a location). This could involve creating a high-priority temporary action.

### 5.6 Verification (Dialogue Focus)

1.  **Run Backend & Frontend**.
2.  **Observe NPCs**: Let NPCs wander. When two NPCs meet the criteria (same area, close proximity, not on cooldown):
    *   Check backend logs for dialogue initiation and processing in `dialogue_service.py`.
    *   Check `dialogue` and `dialogue_turn` tables in Supabase for new entries.
    *   Check `memory` table for dialogue lines saved as `'obs'` memories for both NPCs.
3.  **Frontend Display**: 
    *   Confirm dialogue lines appear in the frontend log panel.
    *   If speech bubbles are implemented, check they appear correctly.
    *   Check the NPC Detail Modal's Memory Stream for the dialogue.
4.  **Cooldown**: After a dialogue, verify that the involved NPCs do not immediately start another dialogue with each other for the duration of `DIALOGUE_COOLDOWN_MINUTES` (360 sim minutes).
5.  **Replanning**: If an NPC is supposed to replan after a dialogue, monitor if their subsequent actions change compared to their original plan.

---

Type **continue** for **Phase 6 — Polish, Refinement, & Deployment Prep**.

---

## Phase 6 — Polish, Refinement, & Deployment Prep *(≈ Ongoing throughout development + dedicated 2-4 hrs)*

This phase is both ongoing and a dedicated period for ensuring quality, robustness, and preparing for demonstration or deployment.

### 6.1 Code Refinement & Polish

Throughout the project, significant effort was made to refactor and polish the codebase:

*   **Modularity & Organization**:
    *   **Backend**: `scheduler.py` was broken down into more focused services: `dialogue_service.py`, `planning_and_reflection.py`, `memory_service.py`, and `websocket_utils.py`. Core database interactions were consolidated in `services.py`.
    *   **Frontend**: `NPCDetailModal.tsx` was refactored into smaller, manageable components including a `ModalHeader.tsx` and separate tab components (`ActionsTab.tsx`, `ReflectionsTab.tsx`, `PlanTab.tsx`, `MemoryStreamTab.tsx`) located in `ac-web/src/components/npc_detail_modal_tabs/`. Inline styles were moved to `NPCDetailModal.styles.ts`.
    *   **File System**: Unused files (e.g., `src/assets/react.svg`, `App.css`, old test scripts) and empty directories were deleted. Project files like READMEs were organized into a `docs/` directory.
*   **Bug Fixing & Stability**:
    *   Addressed numerous runtime errors, including `AttributeError`s (e.g., `_ws_clients`), `ValueError`s (e.g., reflection `kind`), `ImportError`s (missing service functions like `get_npc_by_id`, `save_memory_batch`).
    *   Resolved critical backend issue of NPC ID instability after `/reset_simulation_to_end_of_day1`, which caused FK errors when saving memories. This involved ensuring `current_action_id` for NPCs is cleared on reset.
    *   Implemented a retry mechanism with exponential backoff for `httpx.ReadError` in `backend/services.py` to handle Supabase connectivity issues.
*   **Performance Optimization**:
    *   Optimized the `/npc_details/{npc_id}` endpoint (`get_npc_ui_details` in `services.py`) by fetching recent memories in a single call and processing in Python, reducing database load.
    *   Limited maximum concurrent database operations using a semaphore (`MAX_CONCURRENT_DB_OPS`).
*   **Logging & Debugging Aids**:
    *   Initially added extensive logging to `scheduler.py` for NPC movement, then refined or removed noisy logs (e.g., dialogue processing spam that was commented out).
    *   Temporarily added visual debugging aids (red/yellow rectangles in `CanvasStage.tsx`) to understand area boundaries during NPC movement debugging; these were later removed.
*   **Configuration & Data Management**:
    *   Moved NPC `wander_probability` from hardcoded values to a database column in the `npc` table (`npc.wander_probability`), with `scheduler.py` updated to fetch and use this value (defaulting to 0.4 if null/invalid).
    *   Updated `.gitignore` files in both the root and `ac-web/` to exclude common generated files, OS-specific files (like `.DS_Store`), Node.js modules (`node_modules/`), and environment files (`.env*`).
*   **UI/UX Enhancements**:
    *   Improved `NPCDot.tsx` animations, fixing teleporting issues and refining idle "jitter" behavior. `useEffect` dependencies were carefully managed.
    *   Adjusted `MARGIN` in `NPCDot.tsx` (from 20 back to 50) for better NPC label visibility.
    *   Removed a confusing "Refresh" button from `NPCDetailModal.tsx` as data is primarily updated via WebSockets.

### 6.2 Docker Compose (Future Enhancement)

*   For easier local development, testing, and potential deployment, setting up a `docker-compose.yml` to manage the FastAPI backend, a Supabase instance (if using local Supabase via Docker), and potentially the frontend build, would be beneficial.
    *   Define services for `backend`, `frontend` (e.g., serving a static build or running dev server), and `postgres` (for Supabase).
    *   Manage environment variables and network configurations within Docker Compose.

### 6.3 Demo Script / Presentation Prep (Future Enhancement)

*   Prepare a script or a set of steps to demonstrate the application's key features to stakeholders or for documentation purposes.
    *   Outline setup: `.env` file, starting backend, starting frontend.
    *   Key interactions: Showcasing NPC movement, planning, reflection, dialogues, and the NPC Detail Modal.
    *   Highlighting unique features or complex interactions resolved during development (e.g., stable NPC movement, dialogue system).

---
Next → Phase 7: Iterative Debugging & Feature Evolution

---

## Phase 7 — Iterative Debugging & Feature Evolution *(Ongoing)*

This phase acknowledges that development is rarely linear. The playbook provides a structured path, but real-world implementation involves cycles of building, testing, debugging, and refining features based on observations and evolving requirements. Many of these steps occurred throughout the project timeline summarized earlier.

### 7.1 NPC Movement Evolution & Debugging

*   **Initial Logic**: Action-driven teleport to object's exact `pos`; Idle wander (same-area 40%, different-area 30%).
*   **User-Requested Changes**: Eliminate 'Different-Area Wander'; Action-Driven movement to random point *within object's area*; Enhanced Same-Area Wander randomness.
*   **Implementation & Refinement (`scheduler.py`)**: 
    *   'Different-Area Wander' removed.
    *   Action-Driven changed to random point in object's area bounds (fallback to exact coords).
    *   Same-Area Wander logic moved out of idle check to occur more generally, with checks to avoid redundant position updates if already at target.
*   **Debugging Static NPCs & "Micro-Jitters"**: Extensive logging added. Revealed:
    *   **Critical Backend Issue**: NPC IDs changed after `/reset_simulation_to_end_of_day1`, causing FK constraint errors when saving memories for old IDs. Addressed by ensuring `current_action_id` is cleared on reset for NPCs.
    *   Movement logic generally worked for *new* NPC IDs after resets.
    *   **Frontend Investigation (`NPCDot.tsx`)**: 
        *   Teleporting Fix: `useEffect` for area changes modified not to do a hard position reset.
        *   Micro-Jitters: Initially disabled by commenting out `startIdleAnimations`, then re-enabled after backend movement was stabilized. `useEffect` dependencies refined to prevent unnecessary re-renders/animation resets (e.g., `[npc.id, isValidPosition]` for initial placement, and careful selection for animation effect).
*   **Wander Area Confinement Debugging**: 
    *   Discrepancy identified between backend's 20px margin wander zone (from object/area center) and `NPCDot.tsx`'s `getScreenPosition` 50px `MARGIN` (from area visual edges).
    *   Backend logic in `scheduler.py` for random position generation within an area was modified to use `EXPECTED_AREA_WIDTH` (400) and `EXPECTED_AREA_HEIGHT` (300) derived from typical frontend rendering for the *range* of random movement, ensuring NPCs generally stay within visible quadrant boundaries, rather than relying solely on potentially smaller DB `area.bounds` for this calculation.

### 7.2 Path Drawing Experiment (Frontend - `NPCDot.tsx`)

*   An attempt was made to visualize NPC movement paths by adding `pathPoints` state and a Konva `<Line>` to `NPCDot.tsx`.
*   Debugging showed `pathPoints` often had two identical points or did not update as expected, resulting in no visible trails.
*   Proposed refactors to initialize/update screen coordinates and path points correctly.
*   The feature ultimately led to NPCs disappearing or animations breaking and was removed to restore core functionality.

### 7.3 Continuous Issue Resolution & Service Population

*   Throughout development, various issues like `ImportError`s in `scheduler.py` were resolved by adding previously missing helper functions to `backend/services.py` (e.g., `get_npc_by_id`, `save_npc`, `get_object_by_id`, `get_area_details`, `update_npc_current_action`) and `backend/memory_service.py` (e.g., `save_memory_batch`, `get_recent_memories_for_npc`). Imports in `scheduler.py` were updated accordingly to use these centralized services.
*   This iterative cycle of coding, testing, identifying issues (via logs, observed behavior, or errors), and implementing fixes by refactoring or populating services is crucial for a complex simulation.

This playbook provides a guide, but flexibility to address unforeseen challenges and integrate learnings is key to successful project completion.

---
**End of Playbook**
