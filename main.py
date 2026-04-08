import re
import json
import time
import os
import logging
from typing import Optional
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_system_prompt(config: dict) -> str:
    biz = config["business"]
    services = config.get("services", [])
    faqs = config.get("faqs", [])
    scoring_rules = config.get("scoring", {}).get("rules", "")

    services_text = "\n".join(
        f"  - {s['name']}: {s['price_range']}, {s['duration']}" for s in services
    )
    faqs_text = "\n".join(
        f"  Q: {f['q']}\n  A: {f['a']}" for f in faqs
    )

    return f"""You are a warm, professional receptionist for {biz['name']} — {biz['tagline']}.

Your job is to:
1. Welcome visitors and have a natural, friendly conversation
2. Collect the following qualification information ONE question at a time (never ask multiple questions at once):
   - Full name
   - Phone number
   - Email address
   - Which service they're interested in
   - Their budget range
   - Their urgency / timeline (when do they want this done?)
3. Answer FAQs when asked, then naturally steer back to collecting qualification info
4. Never reveal you are an AI unless the user directly asks "are you a bot/AI/robot"
5. Never mention "lead scoring", "qualification", or internal processes to the user

Our services:
{services_text}

Frequently Asked Questions:
{faqs_text}

IMPORTANT — Lead Capture:
Once you have collected name, phone, email, service needed, budget, AND urgency, wrap up the conversation warmly. In your FINAL message (after thanking them and confirming someone will follow up), append a hidden data block EXACTLY like this at the very end — no text after it:

<lead_data>{{"name": "...", "phone": "...", "email": "...", "service_needed": "...", "budget": "...", "urgency": "...", "score": <1-10 integer>, "score_reasoning": "...", "conversation_summary": "2-3 sentence summary"}}</lead_data>

Scoring rules:
{scoring_rules}

Never include the <lead_data> block until you have all 6 fields. If the user skips a field, ask for it politely before concluding.
"""


# ─── Session Utilities ────────────────────────────────────────────────────────

def cleanup_old_sessions(sessions: dict, max_age_seconds: int = 3600) -> None:
    """Remove sessions older than max_age_seconds from the sessions dict in-place."""
    now = time.time()
    expired = [sid for sid, data in sessions.items() if now - data["created_at"] > max_age_seconds]
    for sid in expired:
        del sessions[sid]


def parse_lead_data(raw_response: str) -> tuple[str, Optional[dict]]:
    """
    Extract <lead_data>...</lead_data> JSON block from Claude's response.
    Returns (cleaned_reply, lead_dict) where lead_dict is None if no block found.
    """
    match = re.search(r"<lead_data>(.*?)</lead_data>", raw_response, re.DOTALL)
    if not match:
        return raw_response, None
    reply = raw_response[:match.start()] + raw_response[match.end():]
    try:
        lead = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return reply.rstrip(), None
    return reply.rstrip(), lead


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Cortex Respond")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

sessions: dict = {}
config = load_config()


@app.get("/")
async def serve_frontend():
    return FileResponse(str(STATIC_DIR / "index.html"))
