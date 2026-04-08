import time
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cleanup_removes_old_sessions():
    from main import cleanup_old_sessions
    sessions = {
        "old": {"messages": [], "created_at": time.time() - 4000},  # older than 1 hour
        "new": {"messages": [], "created_at": time.time() - 100},   # recent
    }
    cleanup_old_sessions(sessions)
    assert "old" not in sessions
    assert "new" in sessions


def test_cleanup_keeps_fresh_sessions():
    from main import cleanup_old_sessions
    sessions = {
        "a": {"messages": [], "created_at": time.time() - 10},
        "b": {"messages": [], "created_at": time.time() - 3500},  # just under 1 hour
    }
    cleanup_old_sessions(sessions)
    assert "a" in sessions
    assert "b" in sessions


def test_parse_lead_data_extracts_json():
    from main import parse_lead_data
    raw = 'Thank you for your time! <lead_data>{"name": "Amara", "phone": "08012345678", "email": "amara@email.com", "service_needed": "Teeth Whitening", "budget": "\\u20a650,000", "urgency": "This week", "score": 8, "score_reasoning": "High urgency, budget aligns", "conversation_summary": "Amara wants teeth whitening this week."}</lead_data>'
    reply, lead = parse_lead_data(raw)
    assert reply.strip() == "Thank you for your time!"
    assert lead["name"] == "Amara"
    assert lead["score"] == 8
    assert "conversation_summary" in lead


def test_parse_lead_data_returns_none_when_absent():
    from main import parse_lead_data
    raw = "Hello! How can I help you today?"
    reply, lead = parse_lead_data(raw)
    assert reply == raw
    assert lead is None


def test_parse_lead_data_strips_whitespace_from_reply():
    from main import parse_lead_data
    lead_json = '{"name": "Test", "phone": "123", "email": "t@t.com", "service_needed": "Checkup", "budget": "\\u20a620,000", "urgency": "Soon", "score": 5, "score_reasoning": "Medium", "conversation_summary": "Test."}'
    raw = f"Great speaking with you!  <lead_data>{lead_json}</lead_data>"
    reply, lead = parse_lead_data(raw)
    assert reply.strip() == "Great speaking with you!"
    assert lead is not None
