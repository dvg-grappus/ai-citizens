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
  current_action_id uuid
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
  { name:'Alice', traits:['friendly','curious'], backstory:'Likes coffee.', relationships:{}, spawn:{x:20,y:20,areaId:id('Bedroom')} },
  { name:'Bob', traits:['lazy','grumpy'], backstory:'Hates Mondays.', relationships:{}, spawn:{x:240,y:30,areaId:id('Office')} }
]);
```

### 1.4 Generate Supabase Types for TypeScript

```bash
npx supabase gen types typescript --project-id <project-id> > src/types/supabase.ts
```

Commit the generated file to version control (or keep in Bolt workspace).

---

## Next → Phase 2 — FastAPI Backend Skeleton

*Reply **continue** for exact step‑by‑step FastAPI setup.*

---

## Phase 2 — Backend Skeleton (FastAPI) *(≈3 hrs)*

**Goal:** run an API that exposes `/seed`, `/tick`, `/state`, and streams ticks via WebSocket.

### 2.1 Initialise Python Project

| Step  | Command / Action                                                                            |
| ----- | ------------------------------------------------------------------------------------------- |
| 2.1.1 | `python -m venv venv && source venv/bin/activate`                                           |
| 2.1.2 | `pip install fastapi uvicorn[standard] supabase openai python-dotenv pydantic httpx`        |
| 2.1.3 | `mkdir backend && cd backend && touch main.py models.py services.py scheduler.py config.py` |

### 2.2 `config.py` — Env Loader

```py
from functools import lru_cache
from pydantic import BaseSettings
class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    OPENAI_API_KEY: str
    TICK_REAL_SEC: float = 1.0  # 1 real‑sec
    TICK_SIM_MIN: int = 5       # 5 sim‑min
    class Config:
        env_file = '.env'
@lru_cache
def get_settings():
    return Settings()
```

### 2.3 `models.py` — Pydantic Schemas (MVP)

```py
from pydantic import BaseModel
from typing import List
class Position(BaseModel):
    x: int; y: int; areaId: str
class NPCSeed(BaseModel):
    name: str; traits: List[str]; backstory: str; spawn: Position
class SeedPayload(BaseModel):
    npcs: List[NPCSeed]
```

### 2.4 Supabase Client Wrapper `services.py`

```py
from supabase import create_client
from config import get_settings
setts = get_settings()
supa = create_client(setts.SUPABASE_URL, setts.SUPABASE_SERVICE_KEY)

def insert_npcs(npcs):
    supa.table('npc').insert(npcs).execute()

def get_state():
    # quick&dirty; optimise later
    return supa.from_('npc').select('*').execute()
```

### 2.5 FastAPI App `main.py`

```py
from fastapi import FastAPI, WebSocket
from models import SeedPayload
from services import insert_npcs, get_state
import scheduler

app = FastAPI(title='Artificial Citizens API')

@app.post('/seed')
async def seed(payload: SeedPayload):
    insert_npcs([npc.dict() for npc in payload.npcs])
    return {'status': 'seeded', 'count': len(payload.npcs)}

@app.get('/state')
async def state():
    return get_state().data

@app.post('/tick')
async def manual_tick():
    await scheduler.advance_tick()
    return {'status': 'ticked'}

@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    scheduler.register_ws(ws)
    while True:
        await ws.receive_text()  # keepalive

scheduler.start_loop()
```

### 2.6 Tick Scheduler `scheduler.py`

```py
import asyncio, json
from typing import List
from services import supa
from config import get_settings
settings = get_settings()
_ws: List[any] = []

async def advance_tick():
    # increment sim_min
    supa.table('sim_clock').update({'sim_min': 'sim_min + %s' % settings.TICK_SIM_MIN}).eq('id',1).execute()
    payload = {'tick':'update'}
    for ws in _ws:
        await ws.send_text(json.dumps(payload))

async def _loop():
    while True:
        await asyncio.sleep(settings.TICK_REAL_SEC)
        await advance_tick()

def start_loop():
    asyncio.create_task(_loop())

def register_ws(ws):
    _ws.append(ws)
```

### 2.7 Run the API Locally

```bash
uvicorn backend.main:app --reload --port 8000
```

Verify `http://localhost:8000/docs` and connect to `ws://localhost:8000/ws` using a WS client to watch the tick stream.

---

Type **continue** to append **Phase 3 — Frontend Canvas (React + Konva)**.

---

## Phase 3 — Frontend Canvas (React + Konva) *(≈4 hrs)*

**Goal:** render a black canvas with four room quadrants, two sample dots moving, top‑right clock, and a live log panel.  No styling polish yet—just functional.

### 3.1 Project Init

| Step  | Command                                                                  |
| ----- | ------------------------------------------------------------------------ |
| 3.1.1 | `pnpm create vite ac-web --template react-ts`                            |
| 3.1.2 | `cd ac-web && pnpm add zustand konva react-konva socket.io-client dayjs` |
| 3.1.3 | Add `.env` → `VITE_API_URL=http://localhost:8000`                        |

### 3.2 Folder Structure

```
src/
 ├─ components/
 │    ├─ CanvasStage.tsx
 │    ├─ ControlsPanel.tsx
 │    ├─ ClockOverlay.tsx
 │    ├─ LogPanel.tsx
 │    └─ NPCDot.tsx
 ├─ hooks/
 │    └─ useWS.ts
 ├─ store/
 │    └─ simStore.ts
 └─ types/
      └─ supabase.ts (generated earlier)
```

### 3.3 Global State (Zustand) `simStore.ts`

* `npcs: NPC[]` – live positions & action emoji.
* `areas: Area[]` – static bounds.
* `clock: { day:number; hh:number; mm:number }`.
* `log: string[]` – most recent 100 lines.
* `actions:` `setNPCs`, `setClock`, `pushLog`.

### 3.4 WebSocket Hook `useWS.ts`

1. Connect to `${import.meta.env.VITE_API_URL.replace('http','ws')}/ws` on mount.
2. Parse incoming JSON `{tick:'update'}`.
3. On each message, `fetch(`\${API}/state`)` → update store (keep polling simple for hack).
4. Push `ClockOverlay` update by converting `sim_clock.sim_min` to day+time using `dayjs.duration`.

### 3.5 Canvas Stage `CanvasStage.tsx`

* Use `Stage` (width 420, height 420, black background).
* **AreasLayer**: loop through `areas` → `Rect` (stroke="#fff" strokeWidth={1}).
* **NPCDotsLayer**: for each NPC → `Group` with

  * `Circle` radius 4 fill="#fff" x/y from store.
  * `Text` fontSize 6 text={npc.emoji}
  * Optional name label beneath (fontSize 6, offsetY 10).
* Re-render when `npcs` array changes.

### 3.6 Clock Overlay `ClockOverlay.tsx`

* Position: absolute top‑right (`position:fixed; top:8px; right:12px; color:#0f0; font-family:monospace; font-size:12px`).
* Show: `Day {day} — {hh.toString().padStart(2,'0')}:{mm.toString().padStart(2,'0')}`.

### 3.7 Controls Panel `ControlsPanel.tsx`

* Buttons: **Pause**, **Resume**, **x1**, **x2** speed.
* On click POST `API/tick` manually when paused.
* For speed: PATCH `sim_clock.speed` via Supabase RPC.

### 3.8 Log Panel `LogPanel.tsx`

* Simple `div` bottom‑right 200 px wide, 300 px tall, black bg, white monospace text, overflow‑y scroll.
* Render last 100 strings from `store.log` newest at bottom.

### 3.9 Wiring Sample Dots

* After seed script runs, start backend; page loads; `useWS` fetches `/state`; canvas should display two dots.
* In backend (`scheduler.advance_tick`) append observation strings to `sim_event` table for testing. WS handler pushes them to clients via separate channel later—skip for now; just log client‑side: `pushLog('Tick ' + Date.now())`.

### 3.10 Smoke Test

1. `pnpm dev` (frontend) + `uvicorn` (backend) running.
2. Refresh page: see four white boxes (rooms) on black field.
3. Two white dots labelled “💤” etc. move every second.
4. Clock increments Day 1 — 00:05, 00:10 …
5. Log panel scrolling.

If all five checks pass, Phase 3 is complete.

---

Type **continue** for **Phase 4 — GPT Integration (Planning & Reflection Prompts)**.

---

## Phase 4 — GPT Integration: Planning, Observation, Reflection *(≈4 hrs)*

Goal: NPCs generate a daily plan at sim‑midnight, log observations each tick, and write a nightly reflection that feeds importance scores into memory.

### 4.1 Install OpenAI SDK (if not already)

```bash
pip install openai==1.13.3 tiktoken
```

### 4.2 Helper Module `llm.py`

* Wrap `openai.ChatCompletion.create` with retry + timeout.
* Accept `system`, `user`, `max_tokens`, `model='gpt-4o-mini'`.

### 4.3 Prompt Templates (store as multi‑line strings in `prompts.py`)

1. **plan\_prompt** – takes NPC name, date, retrieved memories, returns max 8 bulleted actions (HH\:MM — <ActionTitle>).
2. **obs\_template** – simple f‑string for observations.
3. **reflection\_prompt** – takes day’s memories, returns ≤3 lines each with explicit **Importance:1‑5** suffix.

### 4.4 Retrieval Function `retrieve_memories(npc_id, query_type)`

* SQL select latest 400 rows for that NPC.
* For each row, compute `score = w1*recency + w2*importance + w3*similarity`.
* Use OpenAI embeddings once per new memory row; cache in table.
* Return top 20 `content` strings joined by `
  `.
* Weight sets:

  * planning: `(0.2, 0.4, 0.4)`
  * reflection: `(0.3, 0.5, 0.2)`

### 4.5 Daily Plan Cron

* In `scheduler.py` add async `run_daily()` that fires when `sim_clock.sim_min % (24*60) == 0`.
* For each NPC:

  1. `mem = retrieve_memories(npc.id, 'planning')`
  2. `plan_text = llm(plan_prompt(mem, today))`
  3. Parse bullet lines → create `action_instance` rows & insert `plan` row.
* Store original plan prompt & llm output into `memory` kind=`plan` with importance = 3.

### 4.6 Observation Logging Each Tick

* When `advance_tick()` loops NPCs, write observation rows like `08:25 — Saw Bob enter Bathroom` with importance = 1.
* Embed text immediately and store vector.

### 4.7 Nightly Reflection

* After final tick of the day (`sim_clock.sim_min % 1440 == 1435`):

  1. `mem = retrieve_memories(npc.id,'reflection')`
  2. `reflection = llm(reflection_prompt(mem))`
  3. Split lines, extract importance score, insert into `memory` as kind=`reflect` importance=`parsed`.

### 4.8 Frontend Tick Log

* Modify `useWS` → after each `/state` fetch, diff `memory` table for new rows where `kind='obs'` and `npc_id IN focus`.
* Push latest observation strings to `store.log`.

### 4.9 Local End‑to‑End Test

1. Seed two NPCs.
2. Start backend; let sim run until first sim‑midnight (\~5 real min with default speed).
3. Confirm `plan` table populated for Day 2 and action instances queued.
4. Observe nightly `reflection` entries with importance 1‑5 in `memory`.
5. Canvas shows dots executing new plan.

If all pass, Phase 4 is ✅.

---

Type **continue** for **Phase 5 — Dialogue Workflow & Random Challenges**.

---

## Phase 5 — Dialogue Workflow & Random Challenges *(≈4 hrs)*

### 5.0 Objectives

* **Dialogue** – when two NPCs cross paths they may chat for 3‑5 turns, producing a visible transcript and new memories.
* **Random Challenges** – 5 % probability each tick to spawn a global event (e.g., fire alarm, pizza drop) that forces NPCs to reprioritise.

### 5.1 Encounter Detection

1. In `advance_tick()` after movement, for each NPC **A** compare to every other NPC **B** (simple O(n²) for ≤50 agents).
2. **Encounter criteria:** same `area_id` **AND** distance < 30 px.
3. If pair not already in `dialogue` and RNG < 0.3 → initiate chat.

### 5.2 Start Dialogue (Backend)

| Step            | Action                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------- |
| 5.2.1           | Insert row in `dialogue` with `npc_a`,`npc_b`,`start_min` = current `sim_min`.                     |
| 5.2.2           | Build `retrieved = retrieve_memories(a,b,'dialogue')` using high relevance weight `(0.1,0.2,0.7)`. |
| 5.2.3           | Prompt LLM with 3‑turn template (\`NPC\_A:…                                                        |
| NPC\_B:…\` ×3). |                                                                                                    |
| 5.2.4           | Insert each line as `dialogue_turn` rows plus matching `memory` kind=`obs` (importance 2).         |
| 5.2.5           | After last turn, mark `dialogue.end_min` = `sim_min`.                                              |

### 5.3 NPC Reaction Post‑Dialogue

* 20 % chance each speaker `replan` immediately: call plan prompt for remainder of day (truncate after current tick).

### 5.4 Random Challenge Generator

Add to `scheduler._loop()`:

```py
if random.random() < 0.05:
    spawn_challenge()
```

**`spawn_challenge()`** picks one event from list:

| Code         | Label                | Immediate Effect                                         |
| ------------ | -------------------- | -------------------------------------------------------- |
| `fire_alarm` | Fire alarm rings     | Every NPC in any area → high‑priority action `Evacuate`. |
| `pizza_drop` | Free pizza in Lounge | NPCs with `trait='greedy'` add `Grab Pizza` into queue.  |
| `wifi_down`  | Office Wi‑Fi outage  | NPCs currently `Work` pause; switch to `Complain`.       |

* Insert row in `sim_event` table with metadata.
* Broadcast event via WebSocket `{event:'fire_alarm', tick}`.

### 5.5 NPC High‑Priority Action Injection

* When event arrives, each NPC evaluates:

  * Does event target my current area or match my trait filter?
  * If **yes** → push new `ActionInstance` at `currentAction.position+1` with status `active` & duration set (e.g., 30 sim‑min).
  * Set `current_action_id` accordingly.

### 5.6 Frontend Updates

1. **LogPanel** – display `"🔥 Fire alarm triggered!"` or `"🍕 Pizza dropped in Lounge"` on event WS.
2. **NPC Emoji Map** – add `🚶` for `Evacuate`, `🍕` for `Grab Pizza`, `🙅‍♂️` for `Complain`.
3. **Dialogue Highlight** – when a new `dialogue_turn` row fetched, push string `"Alice → Bob: …"` to log; optionally draw temporary speech bubble above both dots for 2 seconds.

### 5.7 Smoke Test Checklist

| Scenario                                                                 | Expected                                                       |
| ------------------------------------------------------------------------ | -------------------------------------------------------------- |
| Trigger `fire_alarm` manually via POST to `/spawn_event?code=fire_alarm` | All NPCs move toward area bounds, emoji `🚶`, log shows alarm. |
| Place two NPCs within 20 px                                              | LLM chat of 3 lines appears in log, dialogue rows in DB.       |
| `wifi_down` while NPC is `Work`                                          | Emoji swaps to `🙅‍♂️`, work action pauses, memory row logged. |

If each checklist item passes, Phase 5 is complete.

---

Type **continue** for **Phase 6 — Polish, Docker Compose & Demo Script**.

---

## Phase 5 — Dialogue Workflow & Random Challenges *(≈3 hrs)*

Purpose: give agents the ability to talk and to react to unexpected global events, making the world feel alive and slightly chaotic.

### 5.1 Encounter Detection

| Step  | Detail                                                                                                             |
| ----- | ------------------------------------------------------------------------------------------------------------------ |
| 5.1.1 | In `scheduler.advance_tick()` loop over **all pairs in same `area`** where euclidean distance `< 30px`.            |
| 5.1.2 | If neither NPC is already in an active dialogue, insert an `encounter` row and push to a `pending_dialogue_queue`. |

### 5.2 Dialogue Handshake Logic

| Rule              | Implementation Hint                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------ |
| Initiation chance | Base 60 %. Modify ±15 % if trait includes `friendly` or `grumpy`.                          |
| Dialogue turns    | Fixed at 3 exchanges (6 lines) to keep token cost low.                                     |
| Cool‑down         | After a dialogue ends, both NPCs ignore further dialogues for the next **20 sim‑minutes**. |

### 5.3 Dialogue Generation Flow

1. **Retrieve context** via `retrieve_memories(npcA, 'dialogue')` & same for `npcB`; merge lists.
2. Call LLM with `dialogue_prompt` (provide both trait sets + recent memories).
3. Parse returned text into `{speaker, text}` lines.
4. Insert a `dialogue` row and corresponding `dialogue_turn` rows.
5. Upsert a new `memory` for each line (`kind='obs'`, importance = 2).

### 5.4 Post‑Dialogue Behaviour

* 30 % chance each NPC **replans** day (call daily plan function immediately but keep date identical).
* Otherwise they resume queued `action_instance` list.

### 5.5 Random Challenge Generator

| Item         | Effect on World                                                                        | Display Text                                |
| ------------ | -------------------------------------------------------------------------------------- | ------------------------------------------- |
| `fire_alarm` | All NPCs in building evacuate to `Lounge`.                                             | "🔥 Fire alarm! Everyone out."              |
| `pizza_drop` | Free pizza appears in `Kitchen` (spawn object). First NPC to reach gains `energy +20`. | "🍕 Pizza arrived—first come first served!" |
| `power_cut`  | `Office` computers unusable for 4 sim‑hrs. NPCs in `Office` relocate.                  | "⚡ Power outage in Office."                 |

*Probability:* each tick `rand() < 0.05` then pick one event at random.

**Implementation Steps**

1. Add `random_challenge()` in `scheduler._loop()` **after** advance\_tick call.
2. When triggered:

   * Insert `sim_event` row with `type`, `start_min`, `metadata`.
   * Broadcast via WebSocket: `{event:'fire_alarm', tick:current}`.
3. NPC reaction rule inside `advance_tick`: if active `sim_event` intersects their current `area`, set `currentAction` to high‑priority evacuation or pizza run.

### 5.6 Frontend Hooks

* **WS Handler**: if payload has `.event`, push banner text to `store.log` and show top‑center toast for 3 s.
* **Speech Bubble**: when store receives a new `dialogue_turn` for an NPC currently rendered, display the first utterance above their dot for 2 real‑sec (fade out).

### 5.7 Verification Checklist

1. Trigger manual `/tick` loop; confirm `encounter` rows inserting when two dots overlap.
2. See dialogue bubbles float briefly above dots; log panel records lines.
3. Observe at least one random challenge firing within \~60 real‑sec; banner appears and dots change route accordingly.

If all pass, Phase 5 is complete.

---
