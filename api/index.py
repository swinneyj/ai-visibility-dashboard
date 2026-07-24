"""Flask API for AI Visibility Dashboard."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure the project root is on the path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from flask import Flask, jsonify, request, send_from_directory

from scanner.technical import AIVisibilityScanner, scan_domain

app = Flask(__name__, static_folder="static", static_url_path="")

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _save_scan(slug: str, data: dict) -> None:
    """Save scan result to disk."""
    filepath = DATA_DIR / f"{slug}.json"
    history = []
    if filepath.exists():
        try:
            with open(filepath) as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    history = existing
                else:
                    history = [existing]
        except (json.JSONDecodeError, OSError):
            history = []
    history.append(data)
    if len(history) > 30:
        history = history[-30:]
    with open(filepath, "w") as f:
        json.dump(history, f, indent=2)


def _load_history(slug: str) -> list[dict]:
    """Load scan history for a domain."""
    filepath = DATA_DIR / f"{slug}.json"
    if filepath.exists():
        try:
            with open(filepath) as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            return []
    return []


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Run a full visibility scan."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    business_name = data.get("business_name", "").strip() or url
    city = data.get("city", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Run technical scan using the class-based scanner
    scanner = AIVisibilityScanner(url, business_name, city)
    scanner.run_full_scan()
    scanner.results["recommendations"] = scanner.generate_recommendations()

    # Use the scanner's safe JSON method to strip all non-serializable objects
    raw_results = scanner.to_json_safe()

    # Build clean output
    result = {
        "url": url,
        "business_name": business_name,
        "timestamp": raw_results.get("summary", {}).get("scan_timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "overall_score": raw_results.get("scores", {}).get("overall", 0),
        "grade": raw_results.get("scores", {}).get("grade", "N/A"),
        "scores": raw_results.get("scores", {}),
        "summary": raw_results.get("summary", {}),
        "checks": raw_results.get("passes", []) + raw_results.get("warnings", []) + raw_results.get("issues", []),
        "passes": raw_results.get("passes", []),
        "warnings": raw_results.get("warnings", []),
        "issues": raw_results.get("issues", []),
        "recommendations": raw_results.get("recommendations", []),
        "ai_visibility": None,
        "competitors": [],
        "details": {
            "technical": raw_results.get("technical", {}),
            "schema": raw_results.get("schema", {}),
            "content": raw_results.get("content", {}),
            "crawlers": raw_results.get("crawlers", {}),
            "social": raw_results.get("social", {}),
            "performance": raw_results.get("performance", {}),
        },
    }

    # Save for history/trends
    from urllib.parse import urlparse
    parsed = urlparse(url)
    slug = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
    slug = slug.replace(".", "_")
    _save_scan(slug, result)

    return jsonify(result)


@app.route("/api/history", methods=["GET"])
def api_history():
    """Get scan history for a domain."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    from urllib.parse import urlparse
    parsed = urlparse(url)
    slug = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
    slug = slug.replace(".", "_")
    history = _load_history(slug)
    return jsonify({"url": url, "history": history, "count": len(history)})


@app.route("/api/trends", methods=["GET"])
def api_trends():
    """Get trend data (scores over time) for a domain."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    from urllib.parse import urlparse
    parsed = urlparse(url)
    slug = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
    slug = slug.replace(".", "_")
    history = _load_history(slug)

    trends = []
    for entry in history:
        scores = entry.get("scores", {})
        trends.append({
            "timestamp": entry.get("timestamp", ""),
            "overall_score": entry.get("overall_score", 0),
            "technical_score": scores.get("technical_readiness"),
            "schema_score": scores.get("schema_readiness"),
            "content_score": scores.get("content_quality"),
        })
    return jsonify({"url": url, "trends": trends})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    app.run(host="0.0.0.0", port=port, debug=True)
