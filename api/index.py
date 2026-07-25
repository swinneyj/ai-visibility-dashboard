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

from flask import Flask, jsonify, request

from scanner.technical import AIVisibilityScanner, scan_domain

# Use absolute path for static folder
_static_dir = str(_project_root / "static")
# On Vercel, use /tmp since the filesystem is readonly
_data_dir = Path("/tmp/data") if os.environ.get("VERCEL") else (_project_root / "data")
app = Flask(__name__)

DATA_DIR = _data_dir
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
    """Serve the dashboard frontend."""
    index_path = _project_root / "static" / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8"), 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Dashboard not found", 404


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Run a full visibility scan."""
    try:
        data = request.get_json(silent=True) or {}
        url = data.get("url", "").strip()
        business_name = data.get("business_name", "").strip() or url
        city = data.get("city", "").strip()

        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Read API keys: env vars first, request body overrides
        ai_keys = {
            "openai_key": data.get("openai_key") or os.environ.get("OPENAI_API_KEY", ""),
            "anthropic_key": data.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY", ""),
            "gemini_key": data.get("gemini_key") or os.environ.get("GEMINI_API_KEY", ""),
            "perplexity_key": data.get("perplexity_key") or os.environ.get("PERPLEXITY_API_KEY", ""),
            "deepseek_key": data.get("deepseek_key") or os.environ.get("DEEPSEEK_API_KEY", ""),
        }
        has_ai_keys = any(v for v in ai_keys.values())

        # Run technical scan
        scanner = AIVisibilityScanner(url, business_name, city)
        scanner.run_full_scan()
        scanner.results["recommendations"] = scanner.generate_recommendations()
        raw_results = scanner.to_json_safe()

        # Run AI visibility checks if any keys configured
        ai_result = None
        if has_ai_keys:
            from scanner.ai_checks import run_ai_visibility_check
            ai_report = run_ai_visibility_check(
                url=url,
                business_name=business_name,
                **ai_keys,
            )
            ai_result = ai_report.to_dict()
            # Add AI-based recommendations
            for r in ai_result.get("results", []):
                if r["status"] == "not_found":
                    raw_results.setdefault("recommendations", []).append({
                        "priority": "high",
                        "category": "ai_visibility",
                        "check": f"AI Visibility: {r['engine']}",
                        "message": f"Not found in {r['engine']} for: \"{r.get('prompt_used','')[:60]}\"",
                        "fix": f"Improve content and citations to appear in {r['engine']} responses.",
                    })
                elif r["status"] == "found" and r.get("competitors"):
                    for comp in r["competitors"][:3]:
                        raw_results.setdefault("competitors", []).append(comp)

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
            "ai_visibility": ai_result,
            "competitors": list(dict.fromkeys(raw_results.get("competitors", []))),
            "details": {
                "technical": raw_results.get("technical", {}),
                "schema": raw_results.get("schema", {}),
                "content": raw_results.get("content", {}),
                "crawlers": raw_results.get("crawlers", {}),
                "social": raw_results.get("social", {}),
                "performance": raw_results.get("performance", {}),
            },
        }
        result["previous_score"] = 0
        result["score_change"] = 0

        # Save for history/trends
        from urllib.parse import urlparse
        parsed = urlparse(url)
        slug = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
        slug = slug.replace(".", "_")
        try:
            history = _load_history(slug)
            if history:
                result["previous_score"] = history[-1].get("overall_score", 0)
                result["score_change"] = result["overall_score"] - result["previous_score"]
            _save_scan(slug, result)
        except Exception:
            pass  # non-critical

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/list")
def api_history_list():
    """List all domains with scan history."""
    entries = []
    for f in DATA_DIR.glob("*.json"):
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
    return jsonify({"entries": entries})


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


@app.route("/api/keys/status")
def api_keys_status():
    """Return which API keys are configured via environment variables (without exposing values)."""
    env_keys = {
        "openai": bool(os.environ.get("OPENAI_API_KEY", "")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY", "")),
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY", "")),
        "deepseek": bool(os.environ.get("DEEPSEEK_API_KEY", "")),
    }
    configured = [k for k, v in env_keys.items() if v]
    return jsonify({"env_configured": configured})


# Error handlers — return JSON, never HTML
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "detail": str(e)[:200]}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": "Server error", "detail": str(e)[:200]}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    app.run(host="0.0.0.0", port=port)
