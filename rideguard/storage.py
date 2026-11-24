"""Small JSON history store for completed demo trips."""
from __future__ import annotations

import json
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "trip_history.json"


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_completed_trip(record: dict) -> list[dict]:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = load_history()
    history.insert(0, record)
    HISTORY_FILE.write_text(json.dumps(history[:100], ensure_ascii=False, indent=2), encoding="utf-8")
    return history[:100]
