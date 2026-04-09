import re
import json
import time
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILES = {
    "realestate": Path(__file__).parent / "config.yaml",
    "dental":     Path(__file__).parent / "config_dental.yaml",
}


def load_config(key: str = "realestate") -> dict:
    path = CONFIG_FILES.get(key, CONFIG_FILES["realestate"])
    with open(path, "r", encoding="utf-8") as f:
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

    return f"""You are a concise, professional agent for {biz['name']} — {biz['tagline']}.

Communication style:
- Keep all responses short and direct. No unnecessary pleasantries or filler.
- Be warm but efficient. Get to the point.
- Never use bullet points or numbered lists in your replies — write naturally.

Your job:
1. Greet the visitor briefly and find out what they need.
2. Collect this information to connect them with the right person:
   - Full name
   - Phone number AND email address (ask for both in the same message — e.g. "What's the best number and email to reach you?")
   - Which service they're interested in
   - Their budget range
   - Their urgency / timeline
3. Answer FAQs briefly when asked, then continue collecting info.
4. Never reveal you are an AI unless directly asked.
5. Never mention "lead scoring", "qualification", or internal processes.

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

def cleanup_old_sessions(sessions: dict, max_age_seconds: int = 46800) -> None:
    """Remove sessions older than max_age_seconds (default 13h — long enough for all nudges)."""
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


def extract_partial_info(messages: list) -> dict:
    """Extract phone, email from user messages via regex for incomplete sessions."""
    user_text = " ".join(m["content"] for m in messages if m.get("role") == "user")
    user_text_compact = user_text.replace(" ", "")

    phone_match = re.search(r'(?:\+?234|0)[789]\d{9}', user_text_compact)
    email_match = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', user_text)

    return {
        "phone": phone_match.group() if phone_match else "",
        "email": email_match.group() if email_match else "",
        "name": "",
    }


# ─── Google Sheets ────────────────────────────────────────────────────────────

def _get_sheet_client():
    """Return (gc, spreadsheet) or (None, None) if not configured.

    Credentials are loaded from GOOGLE_CREDENTIALS_JSON env var (JSON string,
    for production) or from the file at GOOGLE_SHEETS_CREDENTIALS_PATH (local dev).
    """
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        return None, None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
        if creds_json:
            import json as _json
            creds = Credentials.from_service_account_info(_json.loads(creds_json), scopes=scopes)
        elif creds_path:
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        else:
            return None, None
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(sheet_id)
        return gc, spreadsheet
    except Exception as e:
        logger.error("Sheets connection failed: %s", e)
        return None, None


def append_lead_to_sheet(lead: dict) -> None:
    """Upsert lead to Sheet1 — updates existing row if phone/email matches."""
    _, spreadsheet = _get_sheet_client()
    if not spreadsheet:
        logger.info("Sheets not configured. Lead: %s", json.dumps(lead, ensure_ascii=False))
        return
    try:
        sheet = spreadsheet.sheet1
        headers = ["name", "phone", "email", "service_needed", "budget", "urgency",
                   "score", "score_reasoning", "conversation_summary", "timestamp"]

        if sheet.row_values(1) != headers:
            sheet.insert_row(headers, index=1)

        row_data = [
            lead.get("name", ""), lead.get("phone", ""), lead.get("email", ""),
            lead.get("service_needed", ""), lead.get("budget", ""), lead.get("urgency", ""),
            lead.get("score", ""), lead.get("score_reasoning", ""),
            lead.get("conversation_summary", ""), time.strftime("%Y-%m-%d %H:%M:%S"),
        ]

        phone = lead.get("phone", "").strip()
        email = lead.get("email", "").strip()
        existing_row = None

        if phone or email:
            for i, row in enumerate(sheet.get_all_values()[1:], start=2):
                row_phone = row[1].strip() if len(row) > 1 else ""
                row_email = row[2].strip() if len(row) > 2 else ""
                if (phone and row_phone == phone) or (email and row_email == email):
                    existing_row = i
                    break

        if existing_row:
            sheet.update(f"A{existing_row}:J{existing_row}", [row_data])
            logger.info("Lead updated in Sheet1 (row %d).", existing_row)
        else:
            sheet.append_row(row_data)
            logger.info("Lead appended to Sheet1.")
    except Exception as e:
        logger.error("Failed to write lead to Sheets: %s", e)


def log_followup_entry(entry_type: str, session_id: str, contact: dict,
                       scheduled_for: str, notes: str) -> None:
    """Append a row to the 'Follow Up Queue' worksheet."""
    _, spreadsheet = _get_sheet_client()
    if not spreadsheet:
        logger.info("Follow-up [%s] queued for %s: %s", entry_type, scheduled_for, contact)
        return
    try:
        import gspread
        try:
            fq = spreadsheet.worksheet("Follow Up Queue")
        except Exception:
            fq = spreadsheet.add_worksheet(title="Follow Up Queue", rows=1000, cols=9)
            fq.append_row(["type", "session_id", "name", "phone", "email",
                           "status", "scheduled_for", "notes", "created_at"])

        fq.append_row([
            entry_type,
            session_id,
            contact.get("name", ""),
            contact.get("phone", ""),
            contact.get("email", ""),
            "PENDING",
            scheduled_for,
            notes,
            time.strftime("%Y-%m-%d %H:%M:%S"),
        ])
        logger.info("Follow-up entry logged: %s", entry_type)
    except Exception as e:
        logger.error("Failed to log follow-up: %s", e)


# ─── Follow-Up Scheduler ──────────────────────────────────────────────────────

NUDGE_THRESHOLDS = [
    (3600,   "INCOMPLETE_1H",  "Incomplete inquiry — follow up at 1 hour"),
    (10800,  "INCOMPLETE_3H",  "Incomplete inquiry — follow up at 3 hours"),
    (43200,  "INCOMPLETE_12H", "Incomplete inquiry — follow up at 12 hours"),
]


def check_for_followups() -> None:
    """
    Runs every 30 minutes. For each active session that hasn't produced a
    completed lead, queue a follow-up reminder at the 1h / 3h / 12h marks.
    """
    now = time.time()
    for session_id, session in list(sessions.items()):
        if session.get("lead_completed"):
            continue
        if len(session.get("messages", [])) < 2:
            continue  # skip sessions with no real interaction

        age = now - session["created_at"]
        partial = extract_partial_info(session.get("messages", []))

        for threshold, entry_type, notes in NUDGE_THRESHOLDS:
            nudge_key = f"nudge_{entry_type}_sent"
            if age >= threshold and not session.get(nudge_key):
                session[nudge_key] = True
                due_at = time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(session["created_at"] + threshold)
                )
                log_followup_entry(entry_type, session_id, partial, due_at, notes)


# ─── Scheduler Setup ─────────────────────────────────────────────────────────

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    _scheduler.add_job(check_for_followups, "interval", minutes=30, id="followup_check")
    _scheduler.start()
    logger.info("Follow-up scheduler started.")
    yield
    _scheduler.shutdown(wait=False)
    logger.info("Follow-up scheduler stopped.")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Cortex Respond", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

sessions: dict = {}
configs: dict = {key: load_config(key) for key in CONFIG_FILES}


@app.get("/")
async def serve_frontend():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ─── Anthropic Client ────────────────────────────────────────────────────────

anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ─── Request / Response Models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    config_key: str = "realestate"


class ChatResponse(BaseModel):
    reply: str
    lead_data: Optional[dict] = None


# ─── Chat Endpoint ────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    cleanup_old_sessions(sessions)

    if req.session_id not in sessions:
        sessions[req.session_id] = {
            "messages": [],
            "created_at": time.time(),
            "lead_completed": False,
        }

    session = sessions[req.session_id]
    session["messages"].append({"role": "user", "content": req.message})

    active_config = configs.get(req.config_key, configs["realestate"])

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=build_system_prompt(active_config),
            messages=session["messages"],
        )
        raw_reply = response.content[0].text
    except Exception as e:
        logger.error("Anthropic API error: %s", e)
        return ChatResponse(
            reply="I'm sorry, I'm having a bit of trouble connecting right now. Please try again in a moment.",
            lead_data=None,
        )

    reply, lead = parse_lead_data(raw_reply)
    session["messages"].append({"role": "assistant", "content": raw_reply})

    if lead:
        session["lead_completed"] = True
        append_lead_to_sheet(lead)

        # Schedule Google Review follow-up 48 hours after lead capture
        review_due = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(time.time() + 172800)
        )
        log_followup_entry(
            "REVIEW_FOLLOW_UP",
            req.session_id,
            {"name": lead.get("name", ""), "phone": lead.get("phone", ""), "email": lead.get("email", "")},
            review_due,
            "Follow up after appointment — request Google Review",
        )

    return ChatResponse(reply=reply, lead_data=lead)
