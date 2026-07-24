"""Scoring Engine: Combines technical scan + AI visibility into unified scores."""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict, field
from typing import Any

from scanner.technical import ScanReport
from scanner.ai_checks import AiVisibilityReport


@dataclass
class AiVisibilityDashboard:
    """Complete dashboard state combining all scan types."""
    url: str
    business_name: str
    overall_score: float
    technical_audit: dict | None
    ai_visibility: dict | None
    timestamp: str
    trend_data: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "business_name": self.business_name,
            "overall_score": self.overall_score,
            "technical_audit": self.technical_audit,
            "ai_visibility": self.ai_visibility,
            "timestamp": self.timestamp,
            "trend_data": self.trend_data,
            "recommendations": self.recommendations,
            "competitors": self.competitors,
            "errors": self.errors,
        }


def compute_overall_score(tech_score: float, ai_score: float | None) -> float:
    """Compute combined overall score weighting both dimensions."""
    if ai_score is None:
        return tech_score
    # Weight: 40% technical readiness, 60% actual AI visibility
    return round(tech_score * 0.4 + ai_score * 0.6, 1)


def generate_recommendations(
    tech_report: ScanReport | None,
    ai_report: AiVisibilityReport | None,
) -> list[dict]:
    """Generate prioritized fix recommendations."""
    recs = []

    if tech_report:
        # Add fix recommendations for failed checks (highest priority)
        for check in tech_report.checks:
            if check.status == "fail":
                recs.append({
                    "priority": "high",
                    "category": check.category,
                    "check": check.name,
                    "message": check.message,
                    "fix": check.fix,
                })

        # Add warnings (medium priority)
        for check in tech_report.checks:
            if check.status == "warn" and check.fix:
                recs.append({
                    "priority": "medium",
                    "category": check.category,
                    "check": check.name,
                    "message": check.message,
                    "fix": check.fix,
                })

    if ai_report:
        for result in ai_report.results:
            if result.status == "not_found":
                recs.append({
                    "priority": "high",
                    "category": "ai_visibility",
                    "check": f"AI Visibility on {result.engine}",
                    "message": f"Not found in {result.engine} for: \"{result.prompt_used}\"",
                    "fix": (
                        f"Improve content and authority signals for {result.engine}. "
                        "Ensure your site is crawlable, has structured data, "
                        "and create content targeting the questions your customers ask AI."
                    ),
                })
            elif result.status == "partial":
                recs.append({
                    "priority": "medium",
                    "category": "ai_visibility",
                    "check": f"Partial Visibility on {result.engine}",
                    "message": f"Only partially visible in {result.engine}",
                    "fix": "Strengthen content relevance and citation signals.",
                })

    # Sort: high first, then medium, then low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 99))

    return recs


def build_dashboard(
    url: str,
    business_name: str,
    tech_report: ScanReport | None = None,
    ai_report: AiVisibilityReport | None = None,
    trend_data: list[dict] | None = None,
) -> AiVisibilityDashboard:
    """Build the complete dashboard from scan results."""
    tech_score = tech_report.score() if tech_report else 0.0
    ai_score = ai_report.score() if ai_report else None

    overall = compute_overall_score(tech_score, ai_score)

    competitors = []
    if ai_report:
        for result in ai_report.results:
            if result.competitors:
                competitors.extend(result.competitors)
        competitors = list(dict.fromkeys(competitors))[:10]  # deduplicate, max 10

    recommendations = generate_recommendations(tech_report, ai_report)

    return AiVisibilityDashboard(
        url=url,
        business_name=business_name,
        overall_score=overall,
        technical_audit=tech_report.to_dict() if tech_report else None,
        ai_visibility=ai_report.to_dict() if ai_report else None,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        trend_data=trend_data or [],
        recommendations=recommendations,
        competitors=competitors,
        errors=(tech_report.errors if tech_report else []) or [],
    )
