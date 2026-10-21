# Drift

**A soundscape you shape by talking to it.**

Drift starts with a gentle binaural beat. Type things like *"add rain"*, *"make it heavier"*, *"fireplace on the left"*, *"slower"* or *"make it feel like a cabin in a storm"*, and the sound changes live, crossfading smoothly with no clicks or jumps.

Every sound (rain, thunder, wind, ocean, fire, stream, birds, crickets, wind chimes, drone, colored noise) is **synthesized procedurally in the browser** with Tone.js. There are no audio files, so every parameter can change continuously.

## How it works

```
"add rain, a bit softer"
        │
        ▼
Next.js ──WebSocket──▶ FastAPI
                         │  LLM tool calling (Gemini / Groq, free tiers)
                         │    └─ falls back to a rule-based parser
                         │  → [{op: "add_layer", sound: "rain", volume: 0.4}]
                         │  Pydantic validates every op against the scene schema
                         ▼
                      new Scene (server is source of truth)
        ◀──WebSocket── scene
        │
Tone.js engine diffs the scene and ramps every parameter smoothly
```

- **The LLM never touches audio.** It can only emit typed operations (`add_layer`, `adjust_layer`, `remove_layer`, `set_binaural`, `set_master`, `clear_layers`). Invalid ops are dropped, and values are clamped by the schema.
- **Works with no API key.** A built-in parser handles common phrasings, presets ("storm", "cabin", "beach", "forest", "night", "focus", "sleep") and context ("too much" means the last thing you touched). It's also the automatic fallback if the LLM is rate-limited or down.
- **Sliders and voice share one protocol.** Manual edits send the same ops over the WebSocket and are applied optimistically on the client.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Tone.js, Canvas visualizer |
| Backend | FastAPI, WebSockets, Pydantic v2, OpenAI-compatible SDK (Gemini / Groq) |
| Tooling | uv, Ruff, pytest, ESLint, Docker Compose, GitHub Actions |

## Running locally

**Backend** (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
cp .env.example .env        # optional: add a free Gemini or Groq key
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 22+):

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Or run both with Docker: `docker compose up --build`.

Headphones are recommended, because binaural beats need a separate tone in each ear.

### Getting a free LLM key

- **Gemini:** create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and set `LLM_API_KEY`.
- **Groq:** create a key at [console.groq.com/keys](https://console.groq.com/keys) and set `LLM_API_KEY`, `LLM_BASE_URL=https://api.groq.com/openai/v1` and `LLM_MODEL=llama-3.3-70b-versatile`.

Free-tier models and limits change; if a model name is retired, update `LLM_MODEL`.

## Tests

```bash
cd backend && uv run pytest      # rule parser, LLM op validation, WebSocket round trip
cd frontend && npm run lint && npx tsc --noEmit
```

## Project layout

```
backend/app/
  scene.py          Scene schema, ops, apply_ops, presets
  parsers/rules.py  keyword parser (no key needed, also the fallback)
  parsers/llm.py    tool-calling parser for any OpenAI-compatible API
  session.py        per-connection state + interpreter with fallback
  main.py           REST + WebSocket endpoints
frontend/src/
  lib/audio/voices.ts   procedural synth voices (rain, fire, birds...)
  lib/audio/engine.ts   scene → audio graph diffing, binaural beat, master bus
  hooks/useDriftSocket.ts  WebSocket client with reconnect + optimistic updates
  components/           DriftApp, LayerCard, Visualizer, Slider
```

## Roadmap

- [x] Procedural sound engine with smooth transitions
- [x] FastAPI WebSocket scene server
- [x] Natural-language control (LLM tool calling + rule fallback)
- [ ] Auth + saved scenes and presets (Postgres)
- [ ] Shared rooms: co-create one soundscape with friends (Redis pub/sub)
- [ ] AI-generated sounds for anything not in the library (text-to-audio)
- [ ] Voice commands (Whisper)
- [ ] Deploy (Vercel + Fly.io/Railway)

*Binaural beats are offered for relaxation and focus. Drift makes no health claims.*
