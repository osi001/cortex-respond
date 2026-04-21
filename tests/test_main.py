import time
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cleanup_removes_old_sessions():
    from main import cleanup_old_sessions
    sessions = {
        "old": {"messages": [], "created_at": time.time() - 50000},  # older than 13h default
        "new": {"messages": [], "created_at": time.time() - 100},    # recent
    }
    cleanup_old_sessions(sessions)
    assert "old" not in sessions
    assert "new" in sessions


def test_cleanup_keeps_fresh_sessions():
    from main import cleanup_old_sessions
    sessions = {
        "a": {"messages": [], "created_at": time.time() - 10},
        "b": {"messages": [], "created_at": time.time() - 46000},  # just under 13h
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


def test_parse_lead_data_handles_malformed_json():
    from main import parse_lead_data
    raw = "Thanks for chatting! <lead_data>this is not valid json at all{{{</lead_data>"
    reply, lead = parse_lead_data(raw)
    assert lead is None
    assert "<lead_data>" not in reply


def test_chat_endpoint_returns_reply(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    class FakeTextBlock:
        text = "Hello! How can I help you today?"

    class FakeMessage:
        content = [FakeTextBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            return FakeMessage()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    client = TestClient(main.app)
    response = client.post("/chat", json={"session_id": "test-session-1", "message": "Hi there", "region": "lagos"})
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["reply"] == "Hello! How can I help you today?"
    assert data["lead_data"] is None


def test_chat_endpoint_parses_lead_data(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    lead_json = '{"name": "Amara", "phone": "08012345678", "email": "a@a.com", "service_needed": "Checkup", "budget": "\\u20a620,000", "urgency": "This week", "score": 7, "score_reasoning": "High urgency", "conversation_summary": "Amara wants a checkup."}'
    fake_response = f"Thank you Amara! Someone will follow up soon. <lead_data>{lead_json}</lead_data>"

    class FakeTextBlock:
        text = fake_response

    class FakeMessage:
        content = [FakeTextBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            return FakeMessage()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())
    monkeypatch.setattr(main, "append_lead_to_sheet", lambda lead: None)

    client = TestClient(main.app)
    response = client.post("/chat", json={"session_id": "test-session-2", "message": "That covers everything", "region": "lagos"})
    assert response.status_code == 200
    data = response.json()
    assert "Thank you Amara" in data["reply"]
    assert "<lead_data>" not in data["reply"]
    assert data["lead_data"]["name"] == "Amara"
    assert data["lead_data"]["score"] == 7


def test_system_prompt_includes_region_context():
    from main import build_system_prompt
    cfg = {
        "business": {"name": "Apex Properties London", "tagline": "Premium London lettings"},
        "region": {
            "city": "London",
            "currency_symbol": "£",
            "phone_format_example": "+44 20 7946 0123",
            "example_areas": ["Camden", "Shoreditch", "Islington"],
        },
        "services": [{"name": "Rental", "price_range": "£1,800", "duration": "1 week"}],
        "faqs": [{"q": "Where?", "a": "Central London"}],
        "scoring": {"rules": "standard"},
    }
    prompt = build_system_prompt(cfg)
    assert "London" in prompt
    assert "£" in prompt
    assert "Camden" in prompt
    assert "+44 20 7946 0123" in prompt


def test_system_prompt_works_without_region_block():
    from main import build_system_prompt
    cfg = {
        "business": {"name": "Test Co", "tagline": "Testing"},
        "services": [],
        "faqs": [],
        "scoring": {"rules": ""},
    }
    prompt = build_system_prompt(cfg)
    assert "Test Co" in prompt


def test_chat_endpoint_handles_api_error(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    class FakeMessages:
        def create(self, **kwargs):
            raise Exception("API unavailable")

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    client = TestClient(main.app)
    response = client.post("/chat", json={"session_id": "test-session-3", "message": "Hello", "region": "lagos"})
    assert response.status_code == 200
    data = response.json()
    assert data["lead_data"] is None
    assert "trouble" in data["reply"].lower() or "sorry" in data["reply"].lower()


def test_chat_uses_london_config(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    captured = {}

    class FakeTextBlock:
        text = "Hi! How can I help?"

    class FakeMessage:
        content = [FakeTextBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            captured["system"] = kwargs.get("system", "")
            return FakeMessage()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    client = TestClient(main.app)
    response = client.post(
        "/chat",
        json={
            "session_id": "london-session",
            "message": "looking for a flat",
            "region": "london",
            "business_type": "realestate",
        },
    )
    assert response.status_code == 200
    assert "£" in captured["system"]
    assert "Camden" in captured["system"] or "Shoreditch" in captured["system"]


def test_api_region_returns_region_metadata_for_override():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    response = client.get("/api/region?region=london")
    assert response.status_code == 200
    data = response.json()
    assert data["region"] == "london"
    assert data["city"] == "London"
    assert data["currency_symbol"] == "£"
    assert "Camden" in data["example_areas"]
    assert "realestate" in data["business_types"]
    assert "dental" in data["business_types"]


def test_api_region_defaults_to_lagos_for_local_ip():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    response = client.get("/api/region")
    data = response.json()
    # TestClient uses 127.0.0.1, which is private -> lagos
    assert data["region"] == "lagos"
    assert data["currency_symbol"] == "₦"


def test_api_region_invalid_override_falls_through_to_detection():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    response = client.get("/api/region?region=mars")
    # Invalid override ignored -> IP detection -> local IP -> lagos
    assert response.json()["region"] == "lagos"


def test_chat_session_pins_region(monkeypatch):
    """Second message in same session reuses the first request's region."""
    from fastapi.testclient import TestClient
    import main

    captured_systems = []

    class FakeTextBlock:
        text = "Reply"

    class FakeMessage:
        content = [FakeTextBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            captured_systems.append(kwargs.get("system", ""))
            return FakeMessage()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    client = TestClient(main.app)
    client.post("/chat", json={"session_id": "pin-1", "message": "hi", "region": "london"})
    client.post("/chat", json={"session_id": "pin-1", "message": "more"})

    assert "£" in captured_systems[0]
    assert "£" in captured_systems[1]


def test_full_flow_london_override(monkeypatch):
    """GET /api/region?region=london then POST /chat reuses that region."""
    from fastapi.testclient import TestClient
    import main

    captured_system = {}

    class FakeTextBlock:
        text = "Hi, how can I help?"

    class FakeMessage:
        content = [FakeTextBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            captured_system["text"] = kwargs.get("system", "")
            return FakeMessage()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    client = TestClient(main.app)

    r = client.get("/api/region?region=london")
    assert r.status_code == 200
    region_payload = r.json()
    assert region_payload["region"] == "london"

    r2 = client.post("/chat", json={
        "session_id": "e2e-london",
        "message": "hi",
        "region": region_payload["region"],
        "business_type": "realestate",
    })
    assert r2.status_code == 200
    assert "£" in captured_system["text"]
    assert "London" in captured_system["text"]
