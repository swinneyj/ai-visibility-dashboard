"""Storage adapter: uses Vercel KV (Upstash Redis) in production, JSON files fallback locally.
Always saves to local files as backup, so history survives redeploys."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

# Use /tmp/data on Vercel (readonly fs), project data/ dir locally
if os.environ.get("VERCEL"):
    _DATA_DIR = Path("/tmp/ai-visibility-data")
else:
    _DATA_DIR = Path(__file__).parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


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


def _save_local(slug: str, data: dict) -> None:
    """Save scan to local JSON file (always works, both on Vercel /tmp and locally)."""
    try:
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

        # Also update local index
        index_path = _DATA_DIR / "_index.json"
        index = []
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text())
            except (json.JSONDecodeError, OSError):
                index = []
        if slug not in index:
            index.append(slug)
        index_path.write_text(json.dumps(index))
    except Exception:
        pass  # non-critical


def _load_local(slug: str) -> list[dict]:
    """Load scan history from local JSON file."""
    filepath = _DATA_DIR / f"{slug}.json"
    if filepath.exists():
        try:
            with open(filepath) as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_scan(slug: str, data: dict) -> None:
    """Save a scan result. Always saves locally as backup, plus KV in production."""
    # Always save locally
    _save_local(slug, data)

    # Also save to KV if configured
    if _is_kv_configured():
        try:
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

            # Also update the scan list index in KV
            scans_raw = _kv_rest("GET", "get", "scan:index")
            scans = json.loads(scans_raw) if isinstance(scans_raw, str) else (scans_raw or [])
            if isinstance(scans, list):
                if slug not in scans:
                    scans.append(slug)
                    _kv_rest("SET", "set", "scan:index", json.dumps(scans))
        except Exception:
            pass  # KV save is best-effort, local fallback covers us


def load_history(slug: str) -> list[dict]:
    """Load scan history for a domain. Checks KV first, then local files."""
    kv_history = []
    if _is_kv_configured():
        raw = _kv_rest("GET", "get", f"scan:{slug}")
        if raw:
            if isinstance(raw, str):
                try:
                    kv_history = json.loads(raw)
                except json.JSONDecodeError:
                    kv_history = []
            elif isinstance(raw, list):
                kv_history = raw

    local_history = _load_local(slug)

    # Merge: prefer KV (most recent), but use local if KV is empty
    if kv_history:
        return kv_history
    return local_history


def list_scans() -> list[dict]:
    """List all domains with scan history. Merges KV and local entries."""
    all_slugs = set()

    # Collect slugs from local index
    index_path = _DATA_DIR / "_index.json"
    local_slugs = []
    if index_path.exists():
        try:
            local_slugs = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    all_slugs.update(local_slugs)

    # Collect slugs from KV
    if _is_kv_configured():
        scans_raw = _kv_rest("GET", "get", "scan:index")
        kv_slugs = json.loads(scans_raw) if isinstance(scans_raw, str) else (scans_raw or [])
        if isinstance(kv_slugs, list):
            all_slugs.update(kv_slugs)

    # Also scan files on disk directly
    for f in _DATA_DIR.glob("*.json"):
        if f.name in ("_index.json", "history.json"):
            continue
        slug = f.stem
        all_slugs.add(slug)

    entries = []
    for slug in all_slugs:
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
