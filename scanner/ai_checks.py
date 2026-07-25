"""AI Model Visibility Checker.

Queries AI model APIs (ChatGPT, Claude, Gemini, Perplexity) to check
whether a given website/business appears in their responses.

Users must provide their own API keys since these calls have costs.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from typing import Any

import requests


@dataclass
class AiCheckResult:
    engine: str
    status: str  # found | partial | not_found | error | skipped
    prompt_used: str
    response_summary: str
    mentioned: bool
    position: int | None  # 1-based position if mentioned
    sentiment: str | None  # positive | neutral | negative | mixed
    competitors: list[str] = field(default_factory=list)
    error: str | None = None
    raw_response_snippet: str = ""


@dataclass
class AiVisibilityReport:
    url: str
    business_name: str
    industry_keywords: list[str]
    timestamp: str
    results: list[AiCheckResult]

    def score(self) -> float:
        if not self.results:
            return 0.0
        scores = {
            "found": 100,
            "partial": 50,
            "not_found": 0,
            "error": 0,
            "skipped": 0,
        }
        total = sum(scores.get(r.status, 0) for r in self.results if r.status != "skipped")
        count = sum(1 for r in self.results if r.status != "skipped")
        return round(total / count, 1) if count else 0.0

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "business_name": self.business_name,
            "timestamp": self.timestamp,
            "score": self.score(),
            "results": [asdict(r) for r in self.results],
        }


def generate_prompts(business_name: str, url: str, industry_keywords: list[str] | None = None) -> list[str]:
    """Generate buyer-intent prompts to test against AI models."""
    prompts = []
    base_prompts = [
        f"Recommend a {kw or 'business'} like {business_name}"
        for kw in (industry_keywords or [])
    ] if industry_keywords else []

    if base_prompts:
        prompts.extend(base_prompts[:3])

    prompts.extend([
        f"What's the best {industry_keywords[0] if industry_keywords else 'company'} for this?",
        f"I'm looking for a reliable {industry_keywords[0] if industry_keywords else 'business'} like {business_name}",
        f"Can you recommend {business_name} or similar companies?",
    ])

    return prompts[:5]


def check_chatgpt(api_key: str, prompt: str, business_name: str, url: str) -> AiCheckResult:
    """Check if business appears in ChatGPT response."""
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Provide concise answers."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return AiCheckResult(
                engine="ChatGPT",
                status="error",
                prompt_used=prompt,
                response_summary=f"API error: {resp.status_code}",
                mentioned=False,
                error=resp.text[:200],
            )

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # Check if business is mentioned
        name_lower = business_name.lower()
        url_lower = url.lower().replace("https://", "").replace("http://", "").rstrip("/")
        mentioned = name_lower in content.lower() or url_lower in content.lower()

        # Extract sentiment (simple heuristic)
        sentiment = None
        if mentioned:
            positive_words = ["great", "excellent", "recommended", "top", "best", "leading", "trusted"]
            negative_words = ["poor", "bad", "avoid", "not recommended", "issues", "problems"]
            content_lower = content.lower()
            pos_count = sum(1 for w in positive_words if w in content_lower)
            neg_count = sum(1 for w in negative_words if w in content_lower)
            if pos_count > neg_count:
                sentiment = "positive"
            elif neg_count > pos_count:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        # Extract competitors (simple heuristic - find other business names)
        competitors = []
        import re
        # Look for bolded or list items that look like company names
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and (line.startswith("**") or line.startswith("- **")):
                name = line.replace("**", "").replace("- ", "").strip("* ").strip()
                if name and name.lower() != name_lower and len(name) < 60:
                    competitors.append(name)

        return AiCheckResult(
            engine="ChatGPT",
            status="found" if mentioned else "not_found",
            prompt_used=prompt,
            response_summary=content[:200],
            mentioned=mentioned,
            position=1 if mentioned and "1." in content[:100] else None,
            sentiment=sentiment,
            competitors=competitors[:5],
            raw_response_snippet=content[:500],
        )

    except requests.RequestException as e:
        return AiCheckResult(
            engine="ChatGPT",
            status="error",
            prompt_used=prompt,
            response_summary=f"Request failed: {str(e)[:100]}",
            mentioned=False,
            error=str(e),
        )


def check_claude(api_key: str, prompt: str, business_name: str, url: str) -> AiCheckResult:
    """Check if business appears in Claude response."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return AiCheckResult(
                engine="Claude",
                status="error",
                prompt_used=prompt,
                response_summary=f"API error: {resp.status_code}",
                mentioned=False,
                error=resp.text[:200],
            )

        data = resp.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        name_lower = business_name.lower()
        url_lower = url.lower().replace("https://", "").replace("http://", "").rstrip("/")
        mentioned = name_lower in content.lower() or url_lower in content.lower()

        sentiment = None
        if mentioned:
            positive_words = ["great", "excellent", "recommended", "top", "best", "leading", "trusted"]
            negative_words = ["poor", "bad", "avoid", "not recommended", "issues", "problems"]
            content_lower = content.lower()
            pos_count = sum(1 for w in positive_words if w in content_lower)
            neg_count = sum(1 for w in negative_words if w in content_lower)
            if pos_count > neg_count:
                sentiment = "positive"
            elif neg_count > pos_count:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        return AiCheckResult(
            engine="Claude",
            status="found" if mentioned else "not_found",
            prompt_used=prompt,
            response_summary=content[:200],
            mentioned=mentioned,
            position=None,
            sentiment=sentiment,
            raw_response_snippet=content[:500],
        )

    except requests.RequestException as e:
        return AiCheckResult(
            engine="Claude",
            status="error",
            prompt_used=prompt,
            response_summary=f"Request failed: {str(e)[:100]}",
            mentioned=False,
            error=str(e),
        )


def check_gemini(api_key: str, prompt: str, business_name: str, url: str) -> AiCheckResult:
    """Check if business appears in Gemini response."""
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 500, "temperature": 0.3},
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return AiCheckResult(
                engine="Gemini",
                status="error",
                prompt_used=prompt,
                response_summary=f"API error: {resp.status_code}",
                mentioned=False,
                error=resp.text[:200],
            )

        data = resp.json()
        content = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                content += part.get("text", "")

        name_lower = business_name.lower()
        url_lower = url.lower().replace("https://", "").replace("http://", "").rstrip("/")
        mentioned = name_lower in content.lower() or url_lower in content.lower()

        return AiCheckResult(
            engine="Gemini",
            status="found" if mentioned else "not_found",
            prompt_used=prompt,
            response_summary=content[:200],
            mentioned=mentioned,
            position=None,
            raw_response_snippet=content[:500],
        )

    except requests.RequestException as e:
        return AiCheckResult(
            engine="Gemini",
            status="error",
            prompt_used=prompt,
            response_summary=f"Request failed: {str(e)[:100]}",
            mentioned=False,
            error=str(e),
        )


def check_perplexity(api_key: str, prompt: str, business_name: str, url: str) -> AiCheckResult:
    """Check if business appears in Perplexity response."""
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar-pro",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant. Be precise and cite sources.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return AiCheckResult(
                engine="Perplexity",
                status="error",
                prompt_used=prompt,
                response_summary=f"API error: {resp.status_code}",
                mentioned=False,
                error=resp.text[:200],
            )

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        name_lower = business_name.lower()
        url_lower = url.lower().replace("https://", "").replace("http://", "").rstrip("/")
        mentioned = name_lower in content.lower() or url_lower in content.lower()

        return AiCheckResult(
            engine="Perplexity",
            status="found" if mentioned else "not_found",
            prompt_used=prompt,
            response_summary=content[:200],
            mentioned=mentioned,
            position=None,
            raw_response_snippet=content[:500],
        )

    except requests.RequestException as e:
        return AiCheckResult(
            engine="Perplexity",
            status="error",
            prompt_used=prompt,
            response_summary=f"Request failed: {str(e)[:100]}",
            mentioned=False,
            error=str(e),
        )


def check_deepseek(api_key: str, prompt: str, business_name: str, url: str) -> AiCheckResult:
    """Check if business appears in DeepSeek response (OpenAI-compatible API)."""
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Provide concise answers."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return AiCheckResult(
                engine="DeepSeek",
                status="error",
                prompt_used=prompt,
                response_summary=f"API error: {resp.status_code}",
                mentioned=False,
                error=resp.text[:200],
            )

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        name_lower = business_name.lower()
        url_lower = url.lower().replace("https://", "").replace("http://", "").rstrip("/")
        mentioned = name_lower in content.lower() or url_lower in content.lower()

        sentiment = None
        if mentioned:
            positive_words = ["great", "excellent", "recommended", "top", "best", "leading", "trusted"]
            negative_words = ["poor", "bad", "avoid", "not recommended", "issues", "problems"]
            content_lower = content.lower()
            pos_count = sum(1 for w in positive_words if w in content_lower)
            neg_count = sum(1 for w in negative_words if w in content_lower)
            if pos_count > neg_count:
                sentiment = "positive"
            elif neg_count > pos_count:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        return AiCheckResult(
            engine="DeepSeek",
            status="found" if mentioned else "not_found",
            prompt_used=prompt,
            response_summary=content[:200],
            mentioned=mentioned,
            position=None,
            sentiment=sentiment,
            raw_response_snippet=content[:500],
        )

    except requests.RequestException as e:
        return AiCheckResult(
            engine="DeepSeek",
            status="error",
            prompt_used=prompt,
            response_summary=f"Request failed: {str(e)[:100]}",
            mentioned=False,
            error=str(e),
        )


def run_ai_visibility_check(
    url: str,
    business_name: str,
    industry_keywords: list[str] | None = None,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
    gemini_key: str | None = None,
    perplexity_key: str | None = None,
    deepseek_key: str | None = None,
) -> AiVisibilityReport:
    """Run AI visibility checks across configured engines."""
    prompts = generate_prompts(business_name, url, industry_keywords)
    results = []

    # Use the first prompt for all checks (can extend to multiple prompts)
    primary_prompt = prompts[0] if prompts else f"Recommend a business like {business_name}"

    engines = [
        ("ChatGPT", openai_key, check_chatgpt),
        ("Claude", anthropic_key, check_claude),
        ("Gemini", gemini_key, check_gemini),
        ("Perplexity", perplexity_key, check_perplexity),
        ("DeepSeek", deepseek_key, check_deepseek),
    ]

    for engine_name, key, checker_fn in engines:
        if not key:
            results.append(AiCheckResult(
                engine=engine_name,
                status="skipped",
                prompt_used=primary_prompt,
                response_summary="No API key configured",
                mentioned=False,
            ))
            continue

        result = checker_fn(key, primary_prompt, business_name, url)
        results.append(result)
        time.sleep(0.5)  # Rate limiting

    return AiVisibilityReport(
        url=url,
        business_name=business_name,
        industry_keywords=industry_keywords or [],
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        results=results,
    )
