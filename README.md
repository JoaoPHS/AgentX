# MultiAgentX

Run tasks from Termux. One Python process takes the request. An orchestrator decides what the work needs, then hands each part to the cheapest worker that can finish it.

A link summary is one fixed routine, not the product. A page is downloaded only when the task needs it.

```text
multiagentx "plan a script that reads a CSV and writes a summary"
multiagentx "compare two ways to validate a form"
multiagentx "summarize https://example.com/article"
```

There is no graphical interface and no real browser. The local model is a separate `llama-server` process. It starts for a request and exits after it sits idle, so the phone does not keep the weights in RAM.

```mermaid
flowchart TD
  cli[CLI] --> rules[Rules without a model]
  rules -->|whole request is a routine| routine[Subagent]
  rules -->|mixed or open task| analyze[Short analysis]
  analyze --> plan[At most three steps]
  plan --> routine
  plan --> mainAgent[Main agent]
  routine --> router[Router]
  mainAgent --> router
  router --> local[llama-server]
  router --> remote[Your API key, only in the scope you chose]
```

## Install on Termux

Install Termux from F-Droid. The Play Store build is out of date.

```bash
pkg update && pkg upgrade -y
pkg install -y python llama-cpp
pip install .
```

Richer article extraction is optional and needs `libxml2`:

```bash
pip install ".[articles]"
```

Without that extra, the standard-library HTML parser still returns the article text.

Python 3.11 or newer. The only required dependency is `httpx`. No LangChain and no PyTorch.

### Build llama.cpp yourself

If the `llama-cpp` package is missing for your architecture, build the server for aarch64:

```bash
pkg install -y git cmake clang
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build -t llama-server
```

The binary is `build/bin/llama-server`. Put it on `PATH`, or set `local.binary` to its path. Python only talks to the local HTTP API.

## Local model

For a modest phone, use **Qwen2.5-1.5B-Instruct**, GGUF **Q4_K_M**. Download the file yourself and put its path in the config. The app does not fetch the GGUF.

## Configuration

```bash
multiagentx init
```

This writes `~/.config/multiagentx/config.toml` with mode `600` and no secrets. If an existing file is readable by group or others, the app warns on stderr and does not print the file.

```toml
[local]
model_path = "/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf"
binary = "llama-server"
port = 18080
context = 2048
idle_seconds = 120

[routing]
remote_provider = "openrouter"   # or anthropic
remote_scope = "local"           # local, all, orchestrator, or main

[openrouter]
base_url = "https://openrouter.ai/api/v1"
model = ""                       # any model id from that provider

[anthropic]
base_url = "https://api.anthropic.com"
model = ""
```

The remote model id stays in the config. There is no fixed slug in the code. OpenRouter can point at whatever model that key can call. Anthropic is the other built-in provider. The commands below do not name a vendor. They only choose where the configured key is allowed to run.

| Scope | Where the key is used |
| --- | --- |
| `local` | Nowhere. This is the default, even when a key is present. |
| `all` | Orchestrator, routines, and the main agent. `llama-server` stays off for that request. |
| `orchestrator` | Only the analysis that splits the task. Everything else stays on the phone. |
| `main` | Only the main agent. Analysis stays local, or falls back to rules. |

Keys come from `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, or `api_key` in the matching section. An environment variable wins over the file. Keys are not written to logs or error text.

Point `MULTIAGENTX_CONFIG` at another file when you need one.

## How a task is split

The orchestrator does not answer you. It splits the task so a larger model only sees what a routine cannot finish.

1. If the whole message is already a routine, no model is spent on routing. A bare `http(s)` URL, or a request that only asks for a summary, goes to `summarize_url`. Define, translate, and rewrite go to `quick_answer`.
2. A mixed or open task gets one short analysis, at most 80 tokens and three steps. Routines run first. The main agent, if needed, is last and receives the routine output instead of redoing the fetch or the summary.
3. With scope `orchestrator` or `all`, that analysis uses your remote key. With `local` or `main`, it uses the local model. If the orchestrator has no model, keyword rules choose the path. Another key is not spent just to decide.

`/engineer` followed by the task skips analysis and sends the whole task to the main agent.

The server you start listens only on `127.0.0.1`. Before it loads the model, MultiAgentX reads `MemAvailable` from `/proc/meminfo` and refuses to start below 700 MB. Threads are half the cores, capped at 2. If `termux-battery-status` exists and the battery is under 20% while unplugged, it drops to 1 thread and a context of 1024. The process runs at low priority. After 120 seconds without use it is stopped. One generation runs at a time.

Page downloads stop at 2 MB, time out, and reject URLs that resolve to private or link-local addresses.

## Chat

With no arguments, `multiagentx` opens a session. History lasts only for that session, and replies stream as they are generated. `/exit` or Ctrl-D quits and stops the server.

Replies are in English.

```text
/model
/model local
/model all
/model orchestrator
/model main
/engineer review this function and say what is missing
```

`/model` changes the session only. It does not rewrite the config. Alone, it prints the current scope and the configured provider, and never the key.

`/model all` uses whichever remote key is already in the config. To pick between two configured providers, name it: `/model openrouter main` or `/model anthropic all`.

If a summary routine has neither a local model nor a key, you still get the extracted text plus the reason. Other tasks stop with the reason instead of pretending the work was done.

## Not in this version

A real browser for pages that need JavaScript, a graphical interface, memory across sessions, and more than one local model at a time.
