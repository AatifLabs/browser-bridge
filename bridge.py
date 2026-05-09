import asyncio
import json
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from playwright.async_api import async_playwright
import uvicorn

app = FastAPI()

# ============================================================
# GLOBALS
# ============================================================

browser = None
page = None
playwright_instance = None

lock = asyncio.Lock()

CHATGPT_URL = "https://chatgpt.com/"


# ============================================================
# SETUP BROWSER
# ============================================================

async def setup_browser():

    global browser, page, playwright_instance

    print("-> Connecting to Chrome...")

    playwright_instance = await async_playwright().start()

    browser = await playwright_instance.chromium.connect_over_cdp(
        "http://localhost:9222"
    )

    context = (
        browser.contexts[0]
        if browser.contexts
        else await browser.new_context()
    )

    page = (
        context.pages[0]
        if context.pages
        else await context.new_page()
    )

    print("-> Browser ready")


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = re.sub(
        r'[\x00-\x08\x0B\x0C\x0E-\x1F]',
        '',
        text
    )

    return text.strip()


# ============================================================
# DYNAMIC WAIT
# ============================================================

async def dynamic_chatgpt_wait(
    page,
    max_deadline_ms=600000
):

    stop_selector = 'button[data-testid="stop-button"]'

    print("-> Waiting for generation start...")

    try:

        await page.wait_for_selector(
            stop_selector,
            state="attached",
            timeout=5000
        )

        print("-> Generation started")

    except:

        print("-> Fast response / no stop button")

    print("-> Waiting for generation finish...")

    try:

        await page.wait_for_selector(
            stop_selector,
            state="hidden",
            timeout=max_deadline_ms
        )

        print("-> Generation finished")

    except Exception as e:

        print("-> Generation timeout:", e)

    # tiny stabilization
    await asyncio.sleep(1)


# ============================================================
# EXTRACT RESPONSE
# ============================================================

async def extract_latest_response(page):

    selectors = [
        '.agent-turn .markdown',
        '[data-message-author-role="assistant"] .markdown',
        '.markdown'
    ]

    for selector in selectors:

        try:

            print(f"-> Trying selector: {selector}")

            locator = page.locator(selector)

            count = await locator.count()

            print(f"-> Found {count} nodes")

            if count == 0:
                continue

            text = await locator.last.inner_text()

            text = clean_text(text)

            print("\n=========== EXTRACTED ===========\n")
            print(repr(text[:2000]))
            print("\n=================================\n")

            if text and len(text) > 3:
                return text

        except Exception as e:

            print(f"-> Extraction failed: {e}")

    return ""


# ============================================================
# MAIN GPT REQUEST
# ============================================================

async def get_chatgpt_response(prompt: str):

    global page

    async with lock:

        try:

            print("\n======================================")
            print("NEW REQUEST")
            print("======================================\n")

            # ====================================================
            # FRESH CHAT EACH REQUEST
            # ====================================================

            print("-> Opening fresh chat...")

            await page.goto(CHATGPT_URL)

            prompt_selector = "#prompt-textarea"

            print("-> Waiting for prompt box...")

            await page.wait_for_selector(
                prompt_selector,
                timeout=30000
            )

            print("-> Filling prompt...")

            await page.fill(
                prompt_selector,
                prompt
            )

            print("-> Waiting for send button...")

            send_btn = page.locator(
                'button[data-testid="send-button"]'
            )

            await send_btn.wait_for(
                state="visible"
            )

            print("-> Clicking send...")

            await send_btn.click()

            print("-> Prompt sent")

            # ====================================================
            # DYNAMIC WAIT
            # ====================================================

            await dynamic_chatgpt_wait(page)

            # ====================================================
            # EXTRACT RESPONSE
            # ====================================================

            reply = await extract_latest_response(page)

            reply = clean_text(reply)

            print("\n=========== FINAL RESPONSE ===========\n")
            print(repr(reply[:3000]))
            print("\n======================================\n")

            if not reply:
                return "ERROR: EMPTY RESPONSE"

            return reply

        except Exception as e:

            print("-> MAIN ERROR:", e)

            return f"ERROR: {str(e)}"


# ============================================================
# FAKE STREAM GENERATOR
# ============================================================

def fake_stream_generator(content, model_name):

    chat_id = "chatcmpl-browserbridge"

    created_time = int(time.time())

    # chunk by words
    words = content.split(" ")

    for i, word in enumerate(words):

        chunk = word

        if i != len(words) - 1:
            chunk += " "

        data = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": chunk
                    },
                    "finish_reason": None
                }
            ]
        }

        yield f"data: {json.dumps(data)}\n\n"

    # final stop chunk
    final_data = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }

    yield f"data: {json.dumps(final_data)}\n\n"

    yield "data: [DONE]\n\n"


# ============================================================
# OPENAI ENDPOINT
# ============================================================

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):

    try:

        body = await request.json()

        messages = body.get("messages", [])

        prompt_parts = []

        for msg in messages:

            role = msg.get("role", "user")

            content = msg.get("content", "")

            if not content:
                continue

            # handle OpenAI multimodal/list-style content
            if isinstance(content, list):

                extracted_parts = []

                for item in content:

                    if isinstance(item, dict):

                        if item.get("type") == "text":

                            extracted_parts.append(
                                item.get("text", "")
                            )

                    elif isinstance(item, str):

                        extracted_parts.append(item)

                content = "\n".join(extracted_parts)

            prompt_parts.append(
                f"[{role.upper()}]\n{content}"
            )

        prompt = "\n\n".join(prompt_parts)

        stream_requested = body.get(
            "stream",
            False
        )

        model_name = body.get(
            "model",
            "openai/browser-model"
        )

        print("\n======================================")
        print("REQUEST FROM AIDER")
        print("======================================\n")

        print("MODEL:", model_name)
        print("STREAM:", stream_requested)

        reply_text = await get_chatgpt_response(prompt)

        reply_text = clean_text(reply_text)

        if not reply_text:
            reply_text = "ERROR: EMPTY RESPONSE"

        # ====================================================
        # STREAMING RESPONSE
        # ====================================================

        if stream_requested:

            print("-> Returning STREAM response")

            return StreamingResponse(
                fake_stream_generator(
                    reply_text,
                    model_name
                ),
                media_type="text/event-stream"
            )

        # ====================================================
        # NORMAL JSON RESPONSE
        # ====================================================

        response_data = {
            "id": "chatcmpl-browserbridge",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": max(
                    1,
                    len(prompt.split())
                ),
                "completion_tokens": max(
                    1,
                    len(reply_text.split())
                ),
                "total_tokens": (
                    max(1, len(prompt.split()))
                    +
                    max(1, len(reply_text.split()))
                )
            }
        }

        print("-> Returning JSON response")

        return JSONResponse(content=response_data)

    except Exception as e:

        print("-> API ERROR:", e)

        error_response = {
            "id": "error",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "openai/browser-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"ERROR: {str(e)}"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2
            }
        }

        return JSONResponse(content=error_response)


# ============================================================
# STARTUP / SHUTDOWN
# ============================================================

@app.on_event("startup")
async def startup_event():

    await setup_browser()


@app.on_event("shutdown")
async def shutdown_event():

    global browser, playwright_instance

    try:
        await browser.disconnect()
    except:
        pass

    try:
        await playwright_instance.stop()
    except:
        pass


@app.get("/health")
async def health():

    try:

        global page

        if not page:

            return {
                "status": "dead",
                "reason": "page_not_initialized"
            }

        # Ensure correct page
        if "chatgpt.com" not in page.url:

            print("-> Health check recovering page...")

            await page.goto(
                "https://chatgpt.com",
                wait_until="domcontentloaded"
            )

        # Verify ChatGPT input is ready
        await page.wait_for_selector(
            "#prompt-textarea",
            timeout=10000
        )

        return {
            "status": "ok",
            "chatgpt": "ready"
        }

    except Exception as e:

        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("\n======================================")
    print("BROWSER BRIDGE RUNNING")
    print("http://127.0.0.1:8080")
    print("======================================\n")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080
    )
