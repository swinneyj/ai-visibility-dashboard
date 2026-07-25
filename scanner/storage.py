"""Storage adapter: uses Vercel KV (Upstash Redis) in production, JSON files fallback locally."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

_DATA_DIR = Path(__file__).parent.parent / "data"


def _is_kv_configured() -> bool:
    """Check if Vercel KV environment variables are set."""
    return bool(os.environ.get("KV_REST_API_URL") and os.environ.get("KV_REST_API_TOKEN"))


def _kv_rest(method: str, command: str, *args: Any) -> dict | list | None:
    """Execute a Redis command via Vercel KV REST API."""
    url = os.environ["KV_REST_API_URL"]
    token = os.environ["KV_REST_API_TOKEN"]
    try:
        resp = requests.post(
            f"{url}/{command}",
            json={"args": list(args)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result")
        return None
    except Exception:
        return None


def save_scan(slug: str, data: dict) -> None:
    """Save a scan result. KV in production, JSON file fallback locally."""
    if _is_kv_configured():
        # Store in KV: key = "scan:{slug}", value = list of scans (JSON string)
        key = f"scan:{slug}"
        existing_raw = _kv_rest("GET", "get", key)
        history = []
        if existing_raw:
            try:
                history = json.loads(existing_raw) if isinstance(existing_raw, str) else existing_raw
            except (json.JSONDecodeError, TypeError):
                history = []
        if isinstance(history, list):
            history.append(data)
        else:
            history = [data]
        if len(history) > 30:
            history = history[-30:]
        _kv_rest("SET", "set", key, json.dumps(history))

        # Also update the scan list index
        scans_raw = _kv_rest("GET", "get", "scan:index")
        scans = json.loads(scans_raw) if isinstance(scans_raw, str) else (scans_raw or [])
        if isinstance(scans, list):
            if slug not in scans:
                scans.append(slug)
                _kv_rest("SET", "set", "scan:index", json.dumps(scans))
    else:
        # Fallback: JSON file
        _DATA_DIR.mkdir(exist_ok=True)
        filepath = _DATA_DIR / f"{slug}.json"
        history = []
        if filepath.exists():
            try:
                with open(filepath) as f:
                    existing = json.load(f)
                    history = existing if isinstance(existing, list) else [existing]
            except (json.JSONDecodeError, OSError):
                history = []
        history.append(data)
        if len(history) > 30:
            history = history[-30:]
        with open(filepath, "w") as f:
            json.dump(history, f, indent=2)


def load_history(slug: str) -> list[dict]:
    """Load scan history for a domain. KV in production, file fallback locally."""
    if _is_kv_configured():
        raw = _kv_rest("GET", "get", f"scan:{slug}")
        if raw:
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return []
            if isinstance(raw, list):
                return raw
        return []
    else:
        filepath = _DATA_DIR / f"{slug}.json"
        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else [data]
            except (json.JSONDecodeError, OSError):
                return []
        return []


def list_scans() -> list[dict]:
    """List all domains with scan history."""
    if _is_kv_configured():
        scans_raw = _kv_rest("GET", "get", "scan:index")
        scans = json.loads(scans_raw) if isinstance(scans_raw, str) else (scans_raw or [])
        if not isinstance(scans, list):
            return []
        entries = []
        for slug in scans:
            history = load_history(slug)
            if history:
                latest = history[-1]
                entries.append({
                    "domain": slug.replace("_", "."),
                    "last_scan": latest.get("timestamp", ""),
                    "score": latest.get("overall_score", 0),
                    "grade": latest.get("grade", ""),
                    "count": len(history),
                })
        entries.sort(key=lambda e: e.get("last_scan", ""), reverse=True)
        return entries
    else:
        entries = []
        for f in _DATA_DIR.glob("*.json"):
            if f.name == "history.json":
                continue
            try:
                with open(f) as fh:
                    data = json.load(fh)
                    if isinstance(data, list) and data:
                        latest = data[-1]
                        entries.append({
                            "domain": f.stem.replace("_", "."),
                            "last_scan": latest.get("timestamp", ""),
                            "score": latest.get("overall_score", 0),
                            "grade": latest.get("grade", ""),
                            "count": len(data),
                        })
            except (json.JSONDecodeError, OSError):
                pass
        entries.sort(key=lambda e: e.get("last_scan", ""), reverse=True)
        return entries
