import re
import json
import time
from typing import Optional


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
