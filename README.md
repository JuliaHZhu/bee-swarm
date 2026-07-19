# Bee Swarm 🐝

> **File-as-Bus agent swarm. Zero infra. Zero message queue. Just files, rename, and pull.**

---

## What is it?

Bee Swarm is a minimal, production-grade multi-agent system where bees (agents) collaborate through the **file system** instead of HTTP, RPC, or message queues.

It runs three layers of heterogeneous agents — **PM**, **Centurion**, and **Worker** — backed by a nanobot-inspired memory bridge with Git-versioned long-term recall.

---

## Technical Highlights

### 1. File-as-Bus Protocol

No Redis, no RabbitMQ, no Kafka. Agents communicate via **atomic file rename** on a shared workspace:

```
workspace/
├── task_pool/      # pending tasks
├── in_progress/    # claimed tasks
├── done/           # completed / failed
├── artifacts/      # outputs per task
└── memory/         # per-bee Git-versioned memory
```

- **Claim**: `rename(task_pool/x_pending.json, in_progress/x_claimed.json)` — atomic, race-safe
- **Complete**: move to `done/`, update status
- **Observable**: `ls workspace/` shows entire swarm state

### 2. Three-Layer Swarm

| Layer | Role | Trigger | Output |
|-------|------|---------|--------|
| **PM Bee** | Translate goals into executable plans | Manual / CLI | `pm_*` task cards |
| **Centurion Bee** | Decompose, dispatch, monitor, aggregate | Poll `task_pool/` | `worker_*` subtasks + summaries |
| **Worker Bee** | Execute tools (read/write/search) | Poll `task_pool/` | Artifacts + completion marks |

All bees share the same lean kernel (agent loop + tool calling + LLM backend), differentiated by system prompts and tool scopes.

### 3. Memory Bridge (nanobot-inspired)

Each bee owns an isolated Git repository under `workspace/memory/{bee_name}/`:

- **Short-term**: `history.jsonl` — per-task turn-by-turn logs via `MemoryStore`
- **Long-term**: `SOUL.md` + `MEMORY.md` — versioned via `GitStore` (dulwich)
- **Compression**: `dream()` stub for LLM-driven history→long-term condensation

Commit history is inspectable; rollback to any prior state is one `git checkout` away.

### 4. Zero-Infra Concurrency

- No scheduler process, no database server, no network ports
- Pull-based polling with configurable intervals
- Atomic filesystem operations guarantee at-most-once task assignment
- Idempotent by design — safe to restart, replicate, or run on multiple machines sharing an NFS folder

### 5. Minimal Dependencies

```
nanobot-ai>=0.1.0   # MemoryStore + GitStore
aiohttp>=3.14       # LLM HTTP backend
dulwich>=0.25       # Pure-Python Git
pytest>=8.0         # Tests (dev)
```

Total transitive footprint intentionally small. No Docker, no Kubernetes, no CUDA.

---

## Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Create a workspace
mkdir -p workspace

# 3. Launch a goal
pm-bee --goal "Write a Fibonacci function in Python" --title "fib"

# 4. Run the swarm (in separate terminals)
centurion-bee --name centurion_01
worker-bee --name worker_01

# 5. Watch the state
ls workspace/task_pool/ workspace/in_progress/ workspace/done/
```

---

## CLI Commands

| Command | Role | Key Flags |
|---------|------|-----------|
| `pm-bee` | Planner | `--goal` (required), `--title`, `--workspace` |
| `centurion-bee` | Dispatcher | `--once`, `--workspace`, `--poll-interval` |
| `worker-bee` | Executor | `--once`, `--workspace`, `--max-tasks` |

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full File-as-Bus protocol spec, task card format, and state machine.

Design notes for individual bee roles live in [`docs/design-notes/`](docs/design-notes/).

---

## Test

```bash
pytest tests/  # 32 passed
```

- 18 baseline tests (File-as-Bus protocol, artifact store, graph store, E2E pipeline)
- 14 memory-layer tests (history lifecycle, Git commit isolation, dream prompt generation)

---

## License

MIT. Core agent loop derives from nanobot (MIT) with attribution preserved.
