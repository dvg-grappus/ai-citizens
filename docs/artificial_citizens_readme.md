# Artificial Citizens – NPC Simulation Platform

## 0. Executive Brief — *Artificial Citizens* OS

Artificial Citizens is a micro‑scale agent simulator: a living sandbox where every dot on the canvas is an LLM‑driven resident with needs, quirks, memories, and a daily plan. The goal of this proof‑of‑concept is to show how believable behaviour can emerge from simple building blocks in a single weekend hack.

### Why it's interesting

* **LLM‑powered cognition** — planning, reflection, dialogue all come from GPT.
* **Vectorised episodic memory** — agents recall the right facts without context bloat using pgvector.
* **Realtime reactivity** — random events or NPC encounters rewrite the day on the fly.
* **Visual heartbeat** — one glance at the canvas shows who's sleeping, chatting, or panicking.

### Core Mechanics

1. **World Clock** – 1 real second = configurable sim‑minutes (e.g., 5 min). A top‑right HUD shows *Day N – HH:MM*.
2. **Areas & Objects** – Four starter zones (Bedroom · Office · Bathroom · Lounge) populated with stateful objects (Bed, PC, Toothbrush, etc.). NPCs move within an area's expected full local coordinate space (e.g., 400x300 units), respecting a configurable margin.
3. **NPC DNA**

   * Backstory & personality tags (friendly, lazy…)
   * Relationships map (friend, rival) - *Currently conceptual, not fully implemented in interactions.*
   * Spawn position (`x`, `y`, `areaId`).
   * `wander_probability` (float, 0.0-1.0) determining chance to make a random move within their current area each tick.
4. **Action System** – Each `ActionDef` has emoji, base duration, pre‑conditions, post‑effects. Actions are managed as `ActionInstance` records.
5. **Memory Stream** – Continuous append‑only log of:

   * **Plan** — daily schedule created around 5 AM.
   * **Observation** — timestamped events (“08:15 — Saw Bob enter Lounge”) including dialogue lines.
   * **Reflection** — nightly 3‑line digest with importance scores.
   * Embeddings for memories are stored directly in the `memory` table using `pgvector`.
6. **Retrieval Scoring** – `score = w_recency * Recency + w_importance * Importance + w_similarity * Similarity` (weights vary by query type: planning, reflection, dialogue) → top‑20 memories feed the next prompt.
7. **Encounter & Dialogue System**
   * NPCs changing areas or being in the same area can trigger an *Encounter*.
   * Encounters lead to pending dialogue requests processed by a dedicated `dialogue_service`.
   * Dialogues are GPT‑generated (3-5 turns), and each turn is logged as an observation memory.
   * NPCs may re‑plan their day after a dialogue.
8. **Random Challenges** – Configurable probability per tick of a global event (fire alarm, pizza drop). Agents can abandon current action if priority is higher.

### Front‑of‑House (UI)

* **Canvas Stage** – black background, four named quadrants; coloured NPC dots with floating emoji, animated movement.
* **Clock Overlay** – always‑visible day & time counter.
* **Controls Panel** – *Currently conceptual, manual tick via API endpoint if needed.*
* **Log Panel** – *Currently basic client-side logging; backend events/dialogues can be observed via WebSocket messages or database.*
* **NPC Detail Modal** - Click an NPC to see their recent actions, plans, reflections, and memory stream.

---

## 1. Purpose & Scope Purpose & Scope

A weekend‑scale proof‑of‑concept that demonstrates personality‑driven agents moving through a minimal 2‑D environment, persisting memories, reacting to events, conversing with each other and visibly updating their plans.

## 2. Tech Stack (MVP)

| Layer           | Choice                              | Rationale                                       |
| --------------- | ----------------------------------- | ----------------------------------------------- |
| Frontend        | **React + Vite + Zustand**          | Fast boot‑up, global state simple to manage.    |
| Canvas / Render | **Konva** (2‑D canvas lib)          | Lightweight for dot‑style animation.            |
| Backend         | **FastAPI (Python)**                | Async endpoints, easy LLM / vector hooks.       |
| LLM             | **OpenAI GPT‑4o (or similar)**      | Planning, reflection, dialogue.                 |
| Embeddings      | **OpenAI `text-embedding-3‑small`** | Memory vector search.                           |
| Vector Store    | **Supabase (pgvector extension)**   | Integrated vector DB with PostgreSQL.           |
| Realtime        | **FastAPI WebSockets**              | Push tick events and other updates to client.   |
| Build/Deploy    | **Local (uvicorn + pnpm dev)**      | Docker Compose planned for future portability.  |

## 3. High‑Level Flow

1.  **Seed Data (Optional/Initial Setup)**: A script (`scripts/seed.ts`) can be run to populate initial areas, objects, action definitions, and NPCs into the Supabase database.
2.  **Backend Server Starts**: The FastAPI application initializes. The `scheduler.start_loop()` function is called, which begins the main simulation loop (`advance_tick`) running periodically (e.g., every 1 real second).
3.  **Frontend Connects**: The React frontend establishes a WebSocket connection to the backend for receiving tick updates.
4.  **Simulation Tick (`advance_tick` in `scheduler.py`):
    *   **Increment Time**: The global simulation time (`sim_min` in `sim_clock`, `day` in `environment`) is advanced.
    *   **Fetch State**: Current data for all NPCs and areas is fetched from the database.
    *   **Update NPC Actions & State (`update_npc_actions_and_state` function for each NPC):
        *   **Action Completion**: Checks if the NPC's current action has finished based on its duration.
        *   **New Action Selection**: If idle or action completed, selects the next scheduled `action_instance` from the NPC's `plan` for the current day.
        *   **Action-Driven Movement**: If the new action involves an object in a specific area, the NPC's `spawn` coordinates are updated to a random point within that object's area (using full expected area dimensions like 400x300, minus a margin).
        *   **Same-Area Wander**: Each NPC has an independent probability (read from `npc.wander_probability` in DB, defaults to 0.4) to make a random move within their current area's full expected dimensions (minus margin). This occurs if no new action caused a move, or if an action started but didn't involve a move.
        *   **Database Updates**: NPC's `current_action_id` and `spawn` (position) are saved to the database if changed.
        *   **Area Change Observations**: If an NPC moves to a new area, `create_area_change_observations` is called, which can trigger dialogue requests via `dialogue_service.add_dialogue_request_ext` if other NPCs are present.
    *   **Process Dialogues**: `dialogue_service.process_pending_dialogues` is called. This checks pending requests, generates dialogue turns using an LLM if conditions are met (cooldowns, etc.), saves dialogue turns, and creates observation memories for each turn. NPCs involved in new dialogues might be marked for replanning.
    *   **Replanning (Post-Dialogue)**: NPCs marked for replanning by the dialogue service will have `run_daily_planning` triggered for them to adjust their current day's plan.
    *   **Scheduled Planning/Reflection & Other Events**:
        *   **Nightly Reflection** (`run_nightly_reflection`): Triggers around sim-midnight (e.g., 00:00) for the day just ended. NPCs reflect on their memories, generating new `reflect` memories with importance scores.
        *   **Daily Planning** (`run_daily_planning`): Triggers around 5 AM sim-time. NPCs generate a plan for the current day, creating `action_instance` and `plan` records, and a `plan` memory.
        *   **Plan Adherence Observations**: At set times (e.g., noon, midnight), observations about plan adherence are created.
        *   **Random Challenges** (`spawn_random_challenge`): A chance each tick to trigger a global event (e.g., fire alarm), creating a `sim_event` record. NPCs may react to these events based on their logic.
    *   **WebSocket Broadcast**: A `tick_update` message with the new sim time and day is broadcast to all connected clients.
5.  **Frontend Updates**:
    *   Receives `tick_update` via WebSocket.
    *   Fetches full `/state` from the API (includes NPCs with current positions, emojis, areas, clock).
    *   Re-renders the `CanvasStage` with updated NPC positions and emojis.
    *   Updates the `ClockOverlay`.
    *   Displays new dialogue turns or event messages (can be enhanced from current basic logging).

## 4. Data Model — Entities & Relationships

Below is the complete entity set for v0.1. Each interface name generally corresponds to a table name in the relational store (Supabase/PostgreSQL) and is represented here in a TypeScript-like style for clarity.

### 4.1 Entity Overview

| Entity             | Purpose                                                          | Key Relationships                                                                 |
| ------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| **environment**    | Global singleton storing sim‑wide settings (day counter, speed). | ONE-to-MANY → `sim_event`; ONE-to-ONE → `sim_clock` (conceptually linked)       |
| **area**           | Logical room/zone with defined boundaries.                       | ONE-to-MANY → `object`, `npc` (via `npc.spawn.areaId`)                   |
| **object**         | Interactive item inside an `area`.                               | ONE-to-MANY ← `action_instance`                                                    |
| **npc**            | Core agent record (personality, state, position).                | MANY-to-ONE → `area` (via `spawn.areaId`); ONE-to-MANY → `memory`, `plan`, `dialogue_turn`, `encounter` (actor/target), `action_instance` |
| **action_def**     | Master list of possible actions with their properties.           | ONE-to-MANY → `action_instance`                                                    |
| **action_instance**| A concrete, scheduled or in-progress action for one NPC.         | MANY-to-ONE → `npc`, `action_def`, `object` (optional)                        |
| **plan**           | Daily ordered list of `action_instance` UUIDs for an NPC.        | ONE-to-MANY → `action_instance` (conceptually, via UUID array)                   |
| **memory**         | Atomic memory row (plan/observation/reflection/dialogue).        | MANY-to-ONE → `npc`                                                               |
| **encounter**      | One-off proximity event between two NPCs (used to trigger dialogue). | MANY-to-ONE → `npc` (actor) + `npc` (target)                                      |
| **dialogue**       | Parent record for a two-NPC conversation.                        | ONE-to-MANY → `dialogue_turn`                                                      |
| **dialogue_turn**  | Single utterance within a `dialogue`.                            | MANY-to-ONE → `dialogue`, `npc` (speaker)                                         |
| **sim_event**      | Global random or system event (fire alarm, pizza drop).          | MANY-to-ONE → `environment` (conceptually linked)                                 |
| **sim_clock**      | Singleton tracking current simulation time (minute of day).        | ONE-to-ONE ← `environment` (conceptually linked)                                  |

### 4.2 Detailed Schemas (TypeScript‑style, reflecting Supabase structure)

```ts
export type UUID = string; // Typically a string representation of a UUID
export type JsonB = any; // Represents JSONB type in Supabase
export type Vector = number[]; // Represents pgvector type

export interface NPC {
  id: UUID;
  name: string;
  traits: string[];            // e.g. ["friendly","lazy"]
  backstory?: string;           // Nullable
  relationships?: JsonB;        // Default: {}
  // spawn contains current position and area. x,y are local to the areaId.
  spawn: { x: number; y: number; areaId: UUID; }; 
  energy?: number;              // Default: 100, Nullable
  current_action_id?: UUID;   // FK action_instance, Nullable
  wander_probability?: number;  // Float, Nullable, e.g., 0.4
}

// Position is implicitly part of npc.spawn
// export interface Position { x: number; y: number; areaId: UUID; }

// NPCState is represented by fields directly on NPC and current_action_id

export interface Area {
  id: UUID;
  name: string;
  bounds: { x: number; y: number; w: number; h: number }; // Defines visual quadrant in frontend, not strictly used by backend for NPC local coords
}

export interface SupabaseObject { // Renamed to avoid conflict with JavaScript Object
  id: UUID;
  area_id: UUID;              // FK area
  name: string;
  state?: string;             // Default: 'free', Nullable
  pos: { x: number; y: number }; // x,y are local to the area_id
}

export interface ActionDef {
  id: UUID;
  title?: string;             // Nullable
  emoji?: string;             // Nullable
  base_minutes?: number;      // Nullable (used as base_duration in some contexts)
  preconds?: string[];        // Nullable
  post_effects?: string[];    // Nullable
}

export interface ActionInstance {
  id: UUID;
  npc_id: UUID;               // FK npc
  def_id: UUID;               // FK action_def
  object_id?: UUID;           // Nullable, FK object
  start_min?: number;         // Nullable (sim minutes into the current day for the plan)
  duration_min?: number;      // Nullable
  status?: "queued" | "active" | "done"; // Nullable, CHECK constraint in DB
}

export interface Plan {
  id: UUID;
  npc_id: UUID;               // FK npc
  sim_day?: number;           // Nullable
  actions?: UUID[];           // Nullable (array of action_instance UUIDs)
}

export type MemoryKind = "plan" | "obs" | "reflect" | "dialogue_summary"; // Expanded based on usage
export interface Memory {
  id: UUID;
  npc_id: UUID;
  sim_min?: number;           // Nullable (absolute sim minutes from start of sim)
  kind?: MemoryKind;          // Nullable, CHECK constraint in DB
  content?: string;           // Nullable
  importance?: number;        // Nullable (1‑5)
  embedding?: Vector;         // Nullable, pgvector type (e.g., 1536 dimensions)
}

export interface Encounter {
  id: UUID;
  tick?: number;              // Nullable (sim_min at time of encounter)
  actor_id?: UUID;            // Nullable, FK npc
  target_id?: UUID;           // Nullable, FK npc
  description?: string;       // Nullable
}

export interface Dialogue {
  id: UUID;
  npc_a?: UUID;               // Nullable, FK npc
  npc_b?: UUID;               // Nullable, FK npc
  start_min?: number;         // Nullable
  end_min?: number;           // Nullable
}

export interface DialogueTurn {
  id: UUID;
  dialogue_id: UUID;          // FK dialogue
  speaker_id?: UUID;          // Nullable, FK npc
  sim_min?: number;           // Nullable
  text?: string;              // Nullable
}

export interface SimEvent { // Renamed from Event to match DB table
  id: UUID;
  type?: string;              // Nullable, e.g. "fireAlarm"
  start_min?: number;         // Nullable
  end_min?: number;           // Nullable
  metadata?: JsonB;           // Nullable, Default: null
}

export interface Environment {
  id: 1;                      // Enforced singleton (PRIMARY KEY CHECK (id=1))
  day?: number;               // Nullable
  speed?: number;             // Nullable (controls sim-minutes per real-second tick)
}

export interface SimClock {
  id: 1;                      // Enforced singleton (PRIMARY KEY CHECK (id=1))
  sim_min?: number;           // Nullable (current minute of the current simulation day, 0-1439)
  speed?: number;             // Nullable (DEPRECATED - speed is read from Environment table)
}
```

### 4.3 Relationship Cardinalities

```text
NPC 1‑‑* Memory
NPC 1‑‑* Plan
NPC 1‑‑* ActionInstance
NPC 1‑‑* Encounter (actor)
NPC 1‑‑* DialogueTurn
Dialogue 1‑‑* DialogueTurn
Plan 1‑‑* ActionInstance
Area 1‑‑* Object
Area 1‑‑* NPC (via Position)
ActionDef 1‑‑* ActionInstance
Event 0‑‑* Encounter (optional) 
```

### 4.4 Indexes & Performance Notes

* **Memory**: index `(npcId, simMin DESC)` for fast recency search.
* **Memory embeddings** stored in `Chroma` sidecar; row id kept for joins.
* **ActionInstance**: composite `(npcId, status)` to fetch active queue quickly.
* **DialogueTurn**: index `dialogueId` for playback.

---

## 5. Memory Retrieval Algorithm

Memory Retrieval Algorithm

```python
score = w1*recency(ts) + w2*importance + w3*similarity(query)
# recency(ts) = e^{-Δt/τ}
# importance stored from reflection (1‑5)
# similarity = cosine(query_emb, row_emb)
return top_k(20)
```

Weights per query type:

| Query          | w1  | w2  | w3  |
| -------------- | --- | --- | --- |
| **Planning**   | 0.2 | 0.4 | 0.4 |
| **Dialogue**   | 0.1 | 0.2 | 0.7 |
| **Reflection** | 0.3 | 0.5 | 0.2 |

## 6. Prompt Templates (concise)

### 6.1 Daily Plan

```txt
SYSTEM: You control NPC {{name}}. Today is {{sim_date}}.
CONTEXT (memories):
{{retrieved_memories}}
TASK: Produce an ordered list of actions (max 8) for the day.
FORMAT:
1. HH:MM — <ACTION_ID>
...
```

### 6.2 Observation Log Row

Straight string e.g., `07:25 — Saw {{other}} enter {{area}}.`

### 6.3 Reflection

```txt
SYSTEM: Summarise key events for {{sim_date}} in <=3 lines.
CONTEXT: {{retrieved_memories}}
OUTPUT: • … • …
Also assign Importance 1‑5 to each line.
```

### 6.4 Dialogue Generation

```txt
SYSTEM: Generate {{turns}} lines of dialogue between
{{npcA}} ({{traits}}) & {{npcB}} ({{traits}})
CONTEXT: {{retrieved_memories}}
TOPIC: {{trigger}}
FORMAT:
NPC_A: …
NPC_B: …
```

## 7. Event / Encounter Rules

* **Proximity**: Euclidean < 30 px OR same area.
* **Dialogue exit**: after 3–5 turns or new higher‑priority action.
* **Random Challenges**: 5 % chance per tick → emits challenge event (fire, power cut, snack drop). Handled like any other encountered object with `priority=high`.

## 8. API Endpoints

| Verb | Path   | Purpose                                   |
| ---- | ------ | ----------------------------------------- |
| POST | /seed  | Init world JSON.                          |
| GET  | /state | Dump full sim state (debug).              |
| POST | /tick  | Advance one real tick (internal cron).    |
| WS   | /ws    | Pushes {tick, changedNPCs\[]} to clients. |

## 9. Frontend Anatomy & UI Notes

```
App
 ├─ ControlsPanel   (pause • speed • spawn)
 ├─ CanvasStage     (Konva Stage)
 │    ├─ AreasLayer (static rectangles / quadrants)
 │    └─ NPCDotsLayer  (dots + action‑emoji)
 ├─ ClockOverlay    (top‑right; shows Day N — HH:MM)
 ├─ LogPanel        (scrolling observation feed)
 └─ StatsBar        (FPS, #NPC)
```

**Canvas Details**
• Black background; white outlines for each `Area`.
• Dots default to white; colour‑coded per NPC after >1 agent.
• Tiny emoji floats above a dot while an action is active.
• ClockOverlay updates every tick: *"Day 3 — 14:25"* (5 sim‑min / real‑sec).

---
