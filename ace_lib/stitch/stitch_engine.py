import re
import requests
from datetime import datetime
from typing import Optional

def generate_mockup(description: str, agent_id: str, api_key: Optional[str] = None) -> str:
    """Generate a UI mockup using Google Stitch (PRD-01 / Phase 4.5)."""
    mockup_id = f"stitch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    mockup_url = f"https://stitch.google.com/canvas/{mockup_id}"
    ui_code = None

    if api_key:
        try:
            response = requests.post(
                "https://api.stitch.google.com/v1/mockup",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"description": description, "agent_id": agent_id},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                ui_code = data.get("code")
                if data.get("url"):
                    mockup_url = data.get("url")
        except Exception:
            pass

    return mockup_url, ui_code or ""

def sync_mockup(url: str, api_key: Optional[str] = None) -> str:
    """Sync UI code from Google Stitch (PRD-01 / Phase 8.3)."""
    mockup_id = url.split("/")[-1]
    ui_code = None

    if api_key:
        try:
            response = requests.get(
                f"https://api.stitch.google.com/v1/mockup/{mockup_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30
            )
            if response.status_code == 200:
                ui_code = response.json().get("code")
        except Exception:
            pass

    return ui_code or ""

def extract_components(code: str) -> dict:
    """Extract individual components from Stitch code (PRD-01 / Phase 8.3)."""
    components = {}
    component_matches = re.finditer(
        r"export const (\w+) =.*?=>.*?;",
        code,
        re.DOTALL
    )
    for match in component_matches:
        components[match.group(1)] = match.group(0)
    return components
