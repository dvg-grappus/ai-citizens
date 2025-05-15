# Artificial Citizens – NPC Simulation Platform

## 0. Executive Brief — *Artificial Citizens* OS

Artificial Citizens is a micro‑scale agent simulator: a living sandbox where every dot on the canvas is an LLM‑driven resident with needs, quirks, memories, and a daily plan. The goal of this proof‑of‑concept is to show how believable behaviour can emerge from simple building blocks in a single weekend hack.

### Why it’s interesting

* **LLM‑powered cognition** — planning, reflection, dialogue all come from GPT.
* **Vectorised episodic memory** — agents recall the right facts without context bloat.
* **Realtime reactivity** — random events or NPC encounters rewrite the day on the fly.
* **Visual heartbeat** — one glance at the canvas shows who’s sleeping, chatting, or panicking.

### Core Mechanics

1. **World Clock** – 1 real second = 5 sim‑minutes. A top‑right HUD shows *Day N – HH\:MM*.
2. **Areas & Objects** – Four starter zones (Bedroom · Office · Bathroom · Lounge) populated with stateful objects (Bed, PC, Coffee Machine, etc.).
3. **NPC DNA**

   * Backstory & personality tags (friendly, lazy…)
   * Relationships map (friend, rival)
   * Spawn position & default routine (array of `ActionDef` IDs)
4. **Action System** – Each `ActionDef` has emoji, base duration, pre‑conditions, post‑effects.
5. **Memory Stream** – Continuous append‑only log of:

   * **Plan** — daily schedule created at 00:00
   * **Observation** — timestamped events (“08:15 — Saw Bob enter Lounge”)
   * **Reflection** — nightly 3‑line digest with importance scores
6. **Retrieval Scoring** – `score = 0.2·Recency + 0.4·Importance + 0.4·Similarity` (weights vary by query type) → top‑20 memories feed the next prompt.
7. **Encounter Loop**

   * Proximity check (<30 px or same area) triggers an *Encounter* record.
   * Agent decides to greet / ignore / flee.
   * Optional dialogue: 3–5 GPT‑generated turns; both agents may re‑plan after.
8. **Random Challenges** – 5 % chance per tick of a global event (fire alarm, pizza drop). Agents can abandon current action if priority is higher.

### Front‑of‑House (UI)

* **Canvas Stage** – black background, white‑lined quadrants; coloured dots with floating emoji.
* **Clock Overlay** – always‑visible day & time counter.
* **Controls Panel** – pause, resume, speed slider, spawn new NPC.
* **Log Panel** – autoscroll feed of observations & challenges.

---

## 1. Purpose & Scope Purpose & Scope

A weekend‑scale proof‑of‑concept that demonstrates personality‑driven agents moving through a minimal 2‑D environment, persisting memories, reacting to events, conversing with each other and visibly updating their plans.

## 2. Tech Stack (MVP)

| Layer           | Choice                              | Rationale                                    |
| --------------- | ----------------------------------- | -------------------------------------------- |
| Frontend        | **React + Vite + Zustand**          | Fast boot‑up, global state simple to manage. |
| Canvas / Render | **Konva** (2‑D canvas lib)          | Lightweight for dot‑style animation.         |
| Backend         | **FastAPI (Python)**                | Async endpoints, easy LLM / vector hooks.    |
| LLM             | **OpenAI GPT‑4o**                   | Planning, reflection, dialogue.              |
| Embeddings      | **OpenAI `text-embedding-3‑small`** | Memory vector search.                        |
| Vector Store    | **SQLite + Chroma-lite**            | Zero‑infra local vector DB.                  |
| Realtime        | **Socket.IO**                       | Push tick events to client.                  |
| Build/Deploy    | **Docker compose**                  | One command, portable.                       |

## 3. High‑Level Flow

1. **Init → /seed**: POST JSON describing areas, objects, NPC list.
2. **Sim Loop (server)**: every real second → 5 sim‑minutes.
3. **NPC cycle** (per tick):

   1. *Observe* env + encounters.
   2. *React* (maybe) -> action queue.
   3. *Execute* next action step.
   4. *Log* observation to Memory Stream.
4. **Daily cron (sim‑midnight)**: Plan + Reflect prompts run; reflections appended.
5. **Client** subscribes to `/tick` socket → redraw dots & emojis.

## 4. Data Model — Entities & Relationships

Below is the complete entity set for v0.1.  Each interface name doubles as the table name in the relational store and the TypeScript type in the API layer.

### 4.1 Entity Overview

| Entity             | Purpose                                                          | Key Relationships                                                                 |
| ------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| **Environment**    | Global singleton storing sim‑wide settings (day counter, speed). | ONE-to-MANY → `Event`; ONE-to-ONE → `SimClock`                                    |
| **Area**           | Logical room/zone.                                               | ONE-to-MANY → `Object`, `NPC` (via `NPC.state.position.areaId`)                   |
| **Object**         | Interactive item inside an `Area`.                               | ONE-to-MANY ← `ActionInstance`                                                    |
| **NPC**            | Core agent record (personality, state).                          | MANY-to-ONE → `Area`; ONE-to-MANY → `Memory`, `Plan`, `DialogueTurn`, `Encounter` |
| **ActionDef**      | Master list of possible actions.                                 | ONE-to-MANY → `ActionInstance`                                                    |
| **ActionInstance** | A concrete, scheduled or in-progress action for one NPC.         | MANY-to-ONE → `NPC`, `Object?`                                                    |
| **Plan**           | Daily ordered list of `ActionInstance` refs.                     | ONE-to-MANY → `ActionInstance`                                                    |
| **Memory**         | Atomic memory row (plan/observation/reflection).                 | MANY-to-ONE → `NPC`                                                               |
| **Encounter**      | One-off proximity event between two NPCs.                        | MANY-to-ONE → `NPC` (actor) + `NPC` (target)                                      |
| **Dialogue**       | Parent record for a two-NPC conversation.                        | ONE-to-MANY → `DialogueTurn`                                                      |
| **DialogueTurn**   | Single utterance within a `Dialogue`.                            | MANY-to-ONE → `Dialogue`, `NPC` (speaker)                                         |
| **Event**          | Global random or system event (fire alarm).                      | MANY-to-ONE → `Environment`                                                       |
| **SimClock**       | Singleton tracking current sim time & speed.                     | ONE-to-ONE ← `Environment`                                                        |

### 4.2 Detailed Schemas Detailed Schemas (TypeScript‑style)

```ts
export type UUID = string;

export interface NPC {
  id: UUID;
  name: string;
  backstory: string;
  traits: string[];            // e.g. ["friendly","lazy"]
  relationships: Record<UUID, string>; // npcId -> "friend" | "rival" | …
  spawn: Position;
  state: NPCState;
}

export interface Position { x: number; y: number; areaId: UUID; }

export interface NPCState {
  position: Position;
  energy: number;             // 0‑100
  currentActionId?: UUID;     // FK ActionInstance
}

export interface Area {
  id: UUID;
  name: string;               // "Bedroom"
  bounds: { x: number; y: number; w: number; h: number };
}

export interface Object {
  id: UUID;
  areaId: UUID;               // FK Area
  name: string;               // "Bed"
  state: string;              // "occupied" | "free" | …
  position: { x: number; y: number };
}

export interface ActionDef {
  id: UUID;
  title: string;              // "Brush Teeth"
  emoji: string;              // "🪥"
  baseDuration: number;       // minutes
  preconditions?: string[];   // rule ids
  postEffects: string[];      // state tags
}

export interface ActionInstance {
  id: UUID;
  npcId: UUID;                // FK NPC
  defId: UUID;                // FK ActionDef
  objectId?: UUID;            // optional FK Object
  startSimMin: number;        // scheduled start
  durationMin: number;        // may differ after modifiers
  status: "queued" | "active" | "done";
}

export interface Plan {
  id: UUID;
  npcId: UUID;                // FK NPC
  simDate: string;            // YYYY‑MM‑DD
  actionInstanceIds: UUID[];  // ordered
}

export type MemoryKind = "plan" | "obs" | "reflect";
export interface Memory {
  id: UUID;
  npcId: UUID;
  simMin: number;
  kind: MemoryKind;
  content: string;
  importance: number;         // from reflection (1‑5)
  embedding: number[];        // vector dims 1536
}

export interface Encounter {
  id: UUID;
  tick: number;
  actorId: UUID;              // NPC who noticed
  targetId: UUID;             // NPC or Object
  description: string;
}

export interface Dialogue {
  id: UUID;
  npcA: UUID;
  npcB: UUID;
  startSimMin: number;
  endSimMin?: number;
}

export interface DialogueTurn {
  id: UUID;
  dialogueId: UUID;
  speakerId: UUID;
  simMin: number;
  text: string;
}

export interface Event {
  id: UUID;
  type: string;               // "fireAlarm" | "pizzaDrop"
  startSimMin: number;
  endSimMin?: number;
  metadata: Record<string, any>;
}

export interface Environment {
  id: 1;                      // enforced singleton
  day: number;                // starts at 1, increments at 24h sim time
  speed: number;              // real‑sec per sim‑min
}

export interface SimClock {
  id: 1;
  simMin: number;             // monotonically increases
  speed: number;              // mirror of Environment.speed (cache)
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
* **Random Challenges**: 5 % chance per tick → emits challenge event (fire, power cut, snack drop). Handled like any other encountered object with `priority=high`.

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
• ClockOverlay updates every tick: *“Day 3 — 14:25”* (5 sim‑min / real‑sec).

---
