from ace_lib.sop.sop_engine import (
    generate_onboarding_sop,
    generate_pr_review_sop,
    generate_audit_sop
)
from ace_lib.stitch.stitch_engine import (
    generate_mockup,
    sync_mockup,
    extract_components
)

def test_onboarding_sop_generation():
    sop = generate_onboarding_sop(
        agent_id="agent-1",
        name="Agent One",
        role="developer",
        responsibilities=["src/auth"],
        memory_file=".cursor/rules/developer.mdc",
        status="active"
    )
    assert "# SOP: Agent Onboarding - Agent One (agent-1)" in sop
    assert "- **Role**: developer" in sop
    assert "src/auth" in sop

def test_pr_review_sop_generation():
    sop = generate_pr_review_sop("PR-100", "reviewer-1")
    assert "# SOP: PR Review - PR-100" in sop
    assert "- **Reviewer**: reviewer-1" in sop

def test_audit_sop_generation():
    sop = generate_audit_sop("agent-1", "Agent One")
    assert "# SOP: Agent Audit - Agent One (agent-1)" in sop

def test_stitch_mockup_generation(monkeypatch):
    import requests
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"url": "https://stitch.google.com/canvas/test", "code": "export const App = () => <div>App</div>;"}
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: mock_response)

    url, code = generate_mockup("Test app", "agent-1", api_key="test-key")
    assert url == "https://stitch.google.com/canvas/test"
    assert "export const App" in code

def test_stitch_sync(monkeypatch):
    import requests
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "export const Synced = () => <div>Synced</div>;"}
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: mock_response)

    code = sync_mockup("https://stitch.google.com/canvas/test", api_key="test-key")
    assert "export const Synced" in code

def test_extract_components():
    code = """
export const Header = () => <header>Header</header>;
export const Footer = () => <footer>Footer</footer>;
"""
    components = extract_components(code)
    assert "Header" in components
    assert "Footer" in components
    assert "export const Header" in components["Header"]
