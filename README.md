# Browser Bridge

> Makes Aider/Zed treat ChatGPT web as a real OpenAI-compatible backend.
> No API key. No billing dashboard. Just a browser and a bridge.

---

FastAPI + Playwright inference bridge that intercepts local OpenAI-style requests and routes them through a locally authenticated ChatGPT browser session — then streams the response back as fake SSE chunks so your tooling never knows the difference.

Built in a few hours. Works embarrassingly well.

---

## How it works

```
Aider / Zed
    ↓
FastAPI  (/v1/chat/completions)
    ↓
Playwright → ChatGPT Web UI
    ↓
Synthetic SSE stream back
```

Generation timing uses **DOM-state synchronization** on the ChatGPT stop-button lifecycle:

- stop button appears → generation started
- stop button disappears → generation finished

No fixed sleeps. Short prompts return instantly. Huge repo-context prompts sit as long as they need to — without touching the code.

The extracted response is chunked into OpenAI-style SSE events so Aider/LiteLLM treats it as a legitimate streaming provider. The hardest part wasn't browser automation — it was transport compatibility. Aider kept returning `0 tokens received` until the SSE format + usage fields matched what LiteLLM actually validates against.

---

## Features

- OpenAI-compatible `/v1/chat/completions`
- Dynamic DOM-state waiting — no `sleep()` anywhere
- Synthetic SSE streaming (word-by-word chunking)
- Persistent Chrome profile — handles login, cookies, session
- Aider `/add` + `/ask` context forwarding
- Health endpoint
- Background launcher scripts (`aibridge` / `stopbridge`)

---

## Installation

```bash
git clone <repo-url>
cd browser-bridge

python -m venv bridge-env
source bridge-env/bin/activate

pip install -r requirements.txt
playwright install
```

---

## Usage

**Start the bridge:**

```bash
aibridge
```

Or manually:

```bash
./start_bridge.sh
```

**Point Aider at it:**

```bash
aider \
  --openai-api-base http://127.0.0.1:8080/v1 \
  --openai-api-key dummy \
  --model openai/browser-model
```

**Stop:**

```bash
stopbridge
```

Or manually:

```bash
./stop_bridge.sh
```

---

## Known limitations

- **DOM fragility** — ChatGPT UI updates can break selector logic. Multiple fallback selectors help, but a major redesign could break extraction. Long-term fix: intercept backend websocket responses directly via Playwright's network layer instead of scraping rendered DOM.
- **CAPTCHA / verify interrupts** — persistent profile keeps trust high but doesn't fully solve this. If ChatGPT asks you to verify mid-session, the bridge will hang silently.
- **Synthetic streaming** — response is chunked post-generation, not in real-time. Feels live, isn't.

---

## Disclaimer

This project is intended for educational and research purposes only.  
Users are responsible for complying with the terms of service of any platforms they interact with.  
This project is not affiliated with or endorsed by OpenAI.

---

*Browser-native inference is a real problem. This is one way to solve it.*
