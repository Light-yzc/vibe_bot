# AGENTS.md

## Project Overview

**未郁 (Wèiyù)** is a Python-based AI chatbot agent with a detailed character persona — a quiet, gentle greenhouse companion. The project implements an LLM-powered conversational agent that connects to the **Volcengine Ark API** (OpenAI-compatible chat completions) and can operate in two modes:

1. **CLI mode** (`app.py`) — interactive terminal chat loop.
2. **QQ group chat mode** (`qq_app.py`) — listens to QQ group messages via a NapCat WebSocket adapter and decides whether to reply or stay silent based on context, relationship state, and routing rules.

The agent features a rich tool-use loop, lazy skill loading, per-user relationship tracking (with intimacy scores and auto-derived tags), character profile management, persona state, recent event memory, and session continuity summaries.

### Key Technologies

- **Language:** Python 3.12+ (uses `str | None` union syntax)
- **LLM Backend:** Volcengine Ark API (OpenAI-compatible), default model `minimax-m2.5`
- **HTTP Client:** `requests`
- **WebSocket:** NapCat WebSocket adapter (`adapters/qq_ws.py`) for QQ integration
- **Testing:** `pytest` (`.pytest_cache/` present)
- **No dependency manifest:** There is no `requirements.txt` or `pyproject.toml`. Dependencies are `requests` and standard library modules.

### Architecture

```
app.py / qq_app.py          ← Entry points (CLI / QQ)
├── agent/
│   ├── core.py              ← CatgirlAgent: main conversation loop, tool dispatch, passive listening
│   ├── client.py            ← ArkClient: HTTP wrapper for Ark chat completions API
│   ├── skills.py            ← SkillStore: lazy skill loading from skills/ directory
│   ├── state.py             ← StateStore: JSON-file persistence for persona, relationships, events, profiles
│   ├── logger.py            ← Logging setup
│   └── qq_router.py         ← QQ message routing / cooldown logic
├── tools/
│   └── registry.py          ← ToolRegistry: defines all tool schemas, dispatches tool calls
├── adapters/
│   └── qq_ws.py             ← NapCat WebSocket adapter for QQ
├── skills/                  ← Skill content directories (persona, safety, relationship rules, etc.)
├── data/                    ← Runtime JSON state files (gitignored)
├── logs/                    ← Runtime logs (gitignored)
└── config.py                ← Environment variable loading, path constants, validation
```

### Data Flow

1. User input arrives (CLI text or QQ WebSocket event).
2. `CatgirlAgent` builds messages with system prompt, skill catalog summary, and per-message relationship context.
3. Messages are sent to the Ark API with tool schemas.
4. If the model returns `tool_calls`, `ToolRegistry.execute()` dispatches them (skill loading, state reads/writes, relationship events, reply/ignore actions).
5. Tool results are appended and the loop continues until a final answer (CLI) or a final action tool (`reply_group_message` / `ignore_group_message`) is called (QQ passive mode).

## Building and Running

### Prerequisites

- Python 3.12+
- `requests` library (`pip install requests`)
- A valid Volcengine Ark API key

### Environment Setup

```bash
cp .env.example .env
# Edit .env and fill in ARK_API_KEY (required) and QQ_WS_TOKEN (for QQ mode)
```

### CLI Mode

```bash
python app.py
```

Type messages at the `you>` prompt. Use `/user <user_id> [user_name]` to switch user context. Type `quit` or `exit` to stop.

### QQ Mode

```bash
python qq_app.py
```

Requires a running NapCat WebSocket server and `QQ_WS_TOKEN` set in `.env`.

### Running Tests

```bash
pytest
```

The `test_ark.py` file is a standalone integration test for the Ark API and lazy skill loading — it requires a valid `ARK_API_KEY` environment variable.

## Development Conventions

### Code Style

- **Pure Python, no frameworks.** No web framework, no ORM. Just `requests` for HTTP and standard library for everything else.
- **Type hints** are used throughout (Python 3.12+ union syntax: `str | None`).
- **`pyright: basic`** type checking is referenced in `core.py`.
- **Naming:** snake_case for functions/variables, PascalCase for classes. Method names are descriptive (`handle_user_input`, `handle_passive_message`, `apply_relationship_event`).
- **JSON file persistence.** All state (persona, relationships, events, character profile, group whitelist) is stored as JSON files in the `data/` directory. No database.
- **Logging** uses a custom logger setup (`agent/logger.py`). Log messages use key=value format for structured logging.

### Skills System

- Skills live in `skills/` as subdirectories, each containing markdown content with sections.
- The system uses **lazy skill loading**: only skill summaries are sent to the LLM initially. Full sections are loaded on demand via `list_skill_sections` and `load_skill_section` tools.
- `skill.md` in the project root is an older flat catalog used by `test_ark.py`.

### Tool-Use Pattern

- Tools are defined as OpenAI-compatible function schemas in `ToolRegistry.schemas`.
- The agent loop sends tool schemas with every API call and processes `tool_calls` in the response.
- Two "final action" tools (`reply_group_message`, `ignore_group_message`) terminate the passive message loop.
- State-modifying tools (`apply_relationship_event`, `update_relationship_state`, `mutate_character_profile`, etc.) are called before the final action tool.

### State Management

- **Relationship state** is per-group, per-user. Intimacy (0–100) auto-derives `relationship_tag` and `interaction_style` unless manually overridden.
- **Relationship events** (`supportive`, `affectionate`, `hostile`, etc.) apply fixed deltas to intimacy.
- **Character profile** is a single JSON document with structured fields (appearance, interests, habits, etc.).
- **Persona state** tracks current mood, tone, and speaking style.
- **Recent events** are per-group, capped at 20 entries.

### Configuration

All configuration is via environment variables (see `.env.example`). Key variables:

| Variable | Purpose | Default |
|---|---|---|
| `ARK_API_KEY` | Volcengine Ark API key | *required* |
| `ARK_API_URL` | API endpoint | `https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions` |
| `CATGIRL_DEBUG` | Enable debug logging | `1` |
| `CATGIRL_USER_ID` | Default CLI user ID | `local-user` |
| `CATGIRL_USER_NAME` | Default CLI user name | `对方` |
| `QQ_WS_URL` | NapCat WebSocket URL | `ws://127.0.0.1:3001` |
| `QQ_WS_TOKEN` | NapCat auth token | *required for QQ mode* |
| `QQ_REPLY_COOLDOWN_SECONDS` | Reply cooldown | `45` |
| `QQ_LLM_COOLDOWN_SECONDS` | LLM call cooldown | `30` |

### Important Notes for Contributors

- The `data/` and `logs/` directories are gitignored and created at runtime with sensible defaults.
- The character persona and system prompt are in Chinese — this is intentional. The bot's primary language is Chinese.
- The model name is hardcoded to `minimax-m2.5` in `config.py` (not read from env despite `.env.example` showing `ARK_MODEL`).
- There is an optional `agent.memory` module for session summary persistence, with a graceful `NullMemoryStore` fallback if not installed.
