# OpenRA-RL (modified branch)

A modified fork of [OpenRA-RL](https://github.com/yxc20089/OpenRA-RL) focused on
real-time **visible-mode** gameplay with a **vision-language model** driving
the agent. On top of the upstream text-only MCP agent, this branch adds:

- **Visible / non-headless local mode** — runs OpenRA in a real SDL2 window
  so you can watch matches live.
- **Rendered frame capture** via a new `GetFrame` path in the gRPC bridge
  and the modified OpenRA engine (submodule).
- **Optional VLM image input** — per-turn rendered frames are attached to the
  LLM request as an OpenAI-compatible `image_url` multimodal content part.
- **Actionable-state / prerequisite guidance** — each turn briefing is
  prepended with owned structures, power/economy status, BLOCKED actions
  with machine-readable reasons, and numbered next legal steps; tool
  returns expose flags like `requires_deployed_construction_yard`,
  `no_production_buildings`, `no_unit_selected`, `missing_prerequisite`.

For background on the upstream project (Docker flow, leaderboard, replays,
MCP tools in depth, RL harness), see the upstream
[README](https://github.com/yxc20089/OpenRA-RL/blob/main/README.md).

---

## Requirements

- **OS**: Linux, macOS, or Windows 10/11. Visible mode requires a real
  desktop session (SDL2 window + GPU). Headless mode works anywhere.
- **Python**: 3.10 or newer.
- **.NET 8 SDK** (for building the modified OpenRA submodule).
- **Native libs** (desktop/visible mode only): SDL2, OpenAL, FreeType,
  LuaJIT. Linux/macOS install via package manager; Windows gets them
  alongside the OpenRA build output.
- **LLM endpoint** — any OpenAI-compatible Chat Completions API:
  - **Ollama** for local (e.g. `qwen3-vl:8b` for VLM, `qwen3:32b` for text-only).
  - **OpenRouter / OpenAI / LM Studio** for cloud or other local servers.
  - For vision runs: the model **must** support image inputs (`image_url`).

### Environment variables

| Variable | Purpose |
|---|---|
| `OPENRA_PATH` | Absolute path to the built `OpenRA/` directory. **Required** in `--local` mode. |
| `OPENRA_HEADLESS` | `true` / `false`. Overrides `game.headless` for spawned servers. |
| `OPENROUTER_API_KEY` / `LLM_API_KEY` | API key for the LLM endpoint. |
| `LLM_BASE_URL`, `LLM_MODEL` | Override `llm.base_url` / `llm.model`. |

---

## Repository / submodule setup

This branch depends on a **forked, modified OpenRA engine** (not upstream
OpenRA). The submodule is pinned to a commit that includes the gRPC
bridge, `GetFrame` support, and interrupt-handling fixes.

```bash
git clone --recurse-submodules https://github.com/Elise776/OpenRA-RL
cd OpenRA-RL

# Or, if already cloned without --recurse-submodules:
git submodule update --init --recursive
```

`.gitmodules` points at `https://github.com/yxc20089/OpenRA.git`. If you
need to modify the engine yourself, fork that repo, update the URL in
`.gitmodules`, and run `git submodule sync`.

---

## Build

### 1. Build the modified OpenRA engine

```bash
cd OpenRA
make            # Linux/macOS
# Windows: use `make.cmd` in a Developer PowerShell, or `dotnet build OpenRA.sln -c Release`
cd ..
```

This produces `OpenRA/bin/` with `OpenRA.dll`, mod assets, and SDL2/OpenAL
runtime libraries. Remember the absolute path — that's your `OPENRA_PATH`.

> macOS: after `make`, copy SDL2, openal, freetype, luajit from Homebrew
> into `OpenRA/bin/` (see upstream README step 6).

### 2. Install Python dependencies

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -e ".[dev]"
```

### 3. Point `config.yaml` at your OpenRA build

Open `config.yaml` and set the absolute path:

```yaml
game:
  openra_path: "/absolute/path/to/OpenRA-RL/OpenRA"
  headless: false           # true for text-only agents; false enables vision
  window_width: 1280
  window_height: 960
  window_mode: "Windowed"
```

---

## Run

All commands assume `OPENRA_PATH` is exported or `config.yaml` already
points at the built engine. Use `--local` to skip Docker and run the
engine natively (this is the focus of this branch).

### Text-only local play

```bash
openra-rl play --local --provider ollama --model qwen3:32b
```

### Visible local play (no vision)

Opens an SDL2 window you can watch. Vision disabled, purely text agent.

```bash
openra-rl play --local --visible --provider ollama --model qwen3:32b
```

`--visible` sets `game.headless=false` and switches the server to
**single-session** launch (the only mode compatible with a visible
window — see troubleshooting).

### Visible local play with VLM (recommended MVP)

```bash
openra-rl play --local --visible --provider ollama --model qwen3-vl:8b
```

Vision is auto-enabled when the model name matches a VL marker
(`-vl`, `llava`, `pixtral`, `gpt-4o`, `claude-3/4`, `gemini`, etc.).
You can also force it in `config.yaml`:

```yaml
llm:
  vision:
    enabled: true
    every_n_turns: 1        # attach a frame every turn
    max_width: 1024         # downsample to this width (0 = native)
    format: "png"
    detail: "auto"          # auto | low | high
```

A ready-to-edit example config lives at [examples/config-live.yaml](examples/config-live.yaml).

### Cloud VLM via OpenRouter

```bash
export OPENROUTER_API_KEY=sk-or-...
openra-rl play --local --visible \
  --provider openrouter \
  --model qwen/qwen2.5-vl-72b-instruct
```

---

## Vision / VLM notes

- **Visible mode is required for real rendered-frame capture.** The Null
  renderer used in headless mode does not produce framebuffers for
  `GetFrame`. If `vision.enabled=true` but `game.headless=true`, the
  agent logs a `[VISION]` warning and falls back to text.
- Each turn the agent calls `env.get_frame()` (gRPC → engine), receives
  a PNG, converts it to `data:image/png;base64,...`, and attaches it to
  the outgoing Chat Completions payload as an `image_url` content part.
- Vision is enabled by **either**: `llm.vision.enabled: true` in config,
  **or** a model name matching a VL marker (auto-detect).
- Per-turn logs: `[TURN] n=... vision=True image_attached=True tool_calls=N`.
- The agent never *relies* on vision alone — prerequisite checks and
  next-legal-step guidance come from structured state, so a text model
  still works correctly in visible mode with vision off.

---

## Troubleshooting

**`OPENRA_PATH not found` / `/opt/openra` errors.** The built-in default
is `/opt/openra` (container path). When running `--local`, set
`game.openra_path` in `config.yaml` to the absolute path of your built
`OpenRA/` directory, or export `OPENRA_PATH=...`.

**`--visible` doesn't open a window.** Confirm `game.headless=false` made
it into the server config (log line: `headless=False`). On Linux without
a desktop session you need `xvfb-run` + GLX; on WSL you need an X server
or WSLg. Windowed launches need SDL2 on the OS dynamic-loader path — the
built `OpenRA/bin/` should already contain it.

**Engine freezes at load screen in visible mode.** Upstream multi-session
mode blocks the main thread on `grpcThread.Join()` in
`BlankLoadScreen.cs`, which breaks SDL2 rendering. This branch switches
to **single-session** launch whenever `headless=false` (`[server]
skipping daemon launch (single-session visible mode)`). If you still
freeze, confirm you aren't launching the daemon manually.

**`ImportError: rl_bridge_pb2` / protobuf mismatch.** The generated stubs
live in `openra_env/generated/`. If you edit `proto/rl_bridge.proto`,
regenerate:

```bash
python -m grpc_tools.protoc -Iproto --python_out=openra_env/generated \
  --grpc_python_out=openra_env/generated proto/rl_bridge.proto
```

**Outgoing request is text-only despite `vision.enabled=true`.** Look
for `[VISION]` lines at startup and each turn. Common causes:
`headless=true` (blocks capture), model doesn't report VL (auto-detect
miss — set `vision.enabled: true` explicitly), or `every_n_turns > 1`
on a short match. The pre-POST payload dump prints `(image_url
present = True/False)`.

**Model "supports vision" but tool calling is unreliable.** Many small VL
models (e.g. `llava:7b`, `minicpm-v`) produce weak / malformed tool
calls. The agent detects repeated no-tool-call turns (`[LOOP-WATCH]`)
and repeated failed tool calls
(`[TOOL-REPEAT] ... missing_prerequisite=...`) and breaks out with a
`[HINT]` message. If this fires constantly, switch to a stronger VL
model (`qwen3-vl:8b` / `qwen2.5-vl-72b` / GPT-4o class).

---

## Upstream / original project

Full docs (Docker flow, Hugging Face leaderboard, replay viewer, MCP
client integration, RL harness, project structure, 48-tool catalog):

- Upstream repo: https://github.com/yxc20089/OpenRA-RL
- Website & docs: https://openra-rl.dev
- Upstream OpenRA engine fork: https://github.com/yxc20089/OpenRA
- Original OpenRA game: https://www.openra.net/

License: [GPL-3.0](LICENSE).
