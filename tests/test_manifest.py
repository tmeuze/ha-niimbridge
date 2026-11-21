"""The manifest must stay valid JSON with the keys HACS and hassfest require."""

import json
from pathlib import Path

MANIFEST = Path(__file__).parent.parent / "custom_components" / "niimbridge" / "manifest.json"


def test_manifest_is_valid_and_complete():
    data = json.loads(MANIFEST.read_text())
    for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
        assert data.get(key), key
    assert data["domain"] == "niimbridge"
