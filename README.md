# MultiAgentX

Run tasks from Termux. One Python process takes the request. An orchestrator decides what the work needs, then hands each part to the cheapest worker that can finish it.

This is a task runner. A page is fetched only when the task needs that text.

```text
agentx "plan a script that reads a CSV and writes a summary"
agentx "compare two ways to validate a form"
agentx "write a shell function that backs up a directory"
```

There is no graphical interface. The local model is a separate `llama-server` process. It starts for a request and exits after it sits idle, so the phone does not keep the weights in RAM.

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

Python 3.11 or newer. The only required dependency is `httpx`. No LangChain and no PyTorch. Script-rendered pages can use the optional `browser` extra. That extra is not part of the base install.

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
agentx init
```

This writes `~/.config/agentx/config.toml` with mode `600` and no secrets. If an existing file is readable by group or others, the app warns on stderr and does not print the file.

```toml
[local]
model_path = "/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf"
binary = "llama-server"
port = 18080
context = 2048
idle_seconds = 120

[routing]
remote_provider = "openrouter"   # openrouter, anthropic, or openai
remote_scope = "local"           # local, all, orchestrator, or main

[openrouter]
base_url = "https://openrouter.ai/api/v1"
model = ""                       # any model id from that provider

[anthropic]
base_url = "https://api.anthropic.com"
model = ""

[openai]
base_url = "https://api.openai.com/v1"
model = ""
```

The remote model id stays in the config. There is no fixed slug in the code. Each provider calls whichever model its key can use. The commands below do not pick a vendor. They only choose where the configured key is allowed to run.

| Scope | Where the key is used |
| --- | --- |
| `local` | Nowhere. This is the default, even when a key is present. |
| `all` | Orchestrator, routines, and the main agent. `llama-server` stays off for that request. |
| `orchestrator` | Only the analysis that splits the task. Everything else stays on the phone. |
| `main` | Only the main agent. Analysis stays local, or falls back to rules. |

Keys come from `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `api_key` in the matching section. An environment variable wins over the file. Keys are not written to logs or error text.

Point `MULTIAGENTX_CONFIG` at another file when you need one.

## Mobile scripts

Put a Python file in the script directory when a task should run on the phone instead of going to a model. The orchestrator reads the docstring and runs the one script that matches the request. It does not run a file outside that directory.

```bash
agentx script examples
agentx script list
agentx script add my_task.py
```

`script examples` copies three Termux helpers: a toast, a notification, and a battery reading. They call `termux-toast`, `termux-notification`, and `termux-battery-status`.

A script needs a docstring and a keywords line. The file name is the id the orchestrator uses.

```python
"""Save a note on the phone.

keywords: note, reminder
"""
```

The task text is the first argument. Print the result to stdout. In chat, `/scripts` lists what is installed. A request such as `show a toast that the backup finished` runs `toast` and does not spend a model call when that script is the clear match.

## How a task is split

The orchestrator does not answer you. It splits the task so a larger model only sees what a routine cannot finish.

1. If the whole message is already a routine, no model is spent on routing. A bare `http(s)` URL, or a request that only asks for a summary, goes to `summarize_url`. Define, translate, and rewrite go to `quick_answer`. A request that clearly names one installed script goes to `run_script`.
2. A mixed or open task gets one short analysis, at most 80 tokens and three steps. Routines run first. The main agent, if needed, is last and receives the routine output instead of redoing the fetch or the summary.
3. With scope `orchestrator` or `all`, that analysis uses your remote key. With `local` or `main`, it uses the local model. If the orchestrator has no model, keyword rules choose the path. Another key is not spent just to decide.

`/engineer` followed by the task skips analysis and sends the whole task to the main agent.

The server you start listens only on `127.0.0.1`. Before it loads the model, MultiAgentX reads `MemAvailable` from `/proc/meminfo` and refuses to start below 700 MB. Threads are half the cores, capped at 2. If `termux-battery-status` exists and the battery is under 20% while unplugged, it drops to 1 thread and a context of 1024. The process runs at low priority. After 120 seconds without use it is stopped. One generation runs at a time.

Page downloads stop at 2 MB, time out, and reject URLs that resolve to private or link-local addresses. That static download is the default for `summarize_url`.

## JavaScript pages

`summarize_url` reads a page with a plain HTTP download. That path does not run JavaScript and does not start a browser. Most static articles finish there.

If the extract is empty, or the page is only a script shell such as a `noscript` message or an empty app root, and the optional browser extra is installed, the same URL is rendered once. Rendering repeats the URL checks: `http` or `https` only, no username or password, no private or link-local address, and each redirect is checked again. The render uses the same timeout and size cap.

```bash
pip install 'agentx[browser]'
```

Install a browser runtime yourself if you want rendering. MultiAgentX does not download one and does not shell out to install one. On Termux a desktop browser often is not available. In that case, or when the extra is missing, you get the static text and a short note that the page looks script-rendered. That note is not a summary.

This fallback is only for `summarize_url`. It is not a graphical browser, and other tasks do not start it.

## Chat

With no arguments, `agentx` opens a session. History lasts only for that session, and replies stream as they are generated. `/exit` or Ctrl-D quits and stops the server.

Replies are in English.

```text
/model
/model local
/model all
/model orchestrator
/model main
/engineer review this function and say what is missing
/scripts
```

`/model` changes the session only. It does not rewrite the config. Alone, it prints the current scope and the configured provider, and never the key.

`/model all` uses whichever remote key is already in the config. To pick a provider, name it: `/model openrouter main`, `/model anthropic all`, or `/model openai orchestrator`.

If the chosen model cannot run, the task stops with the reason instead of pretending the work was done.

## Not in this version

A graphical interface, memory across sessions, and more than one local model at a time.
