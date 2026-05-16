"""Audit existing Summary content and score it against the rule set.

Score range: 0–100. Recommended action thresholds (see config):
    < AUDIT_REGENERATE_THRESHOLD       → REGENERATE
    ≥ AUDIT_REGENERATE_THRESHOLD and
      < AUDIT_MANUAL_REVIEW_THRESHOLD  → MANUAL_REVIEW
    ≥ AUDIT_MANUAL_REVIEW_THRESHOLD    → KEEP
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from tools.summary import config
from tools.summary.qa import qa_checks


@dataclass
class AuditScore:
    url: str
    score: float
    action: str  # "REGENERATE" | "MANUAL_REVIEW" | "KEEP"
    failed_checks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def audit_existing_summary(
    url: str,
    summary_markdown: str,
    primary_keyword: str,
    locale: str,
    link_inventory: Iterable[str],
    excluded_path_segments: Iterable[str] = ("vc", "sd", "sm"),
) -> AuditScore:
    """Run QA against an existing Summary; return a score + recommended action.

    If summary_markdown is empty, the score is 0 and the action is REGENERATE.
    """
    if not summary_markdown.strip():
        return AuditScore(
            url=url,
            score=0.0,
            action="REGENERATE",
            failed_checks=["empty_summary"],
            notes=["No existing summary to audit."],
        )

    report = qa_checks(
        summary_markdown,
        primary_keyword,
        locale,
        link_inventory,
        excluded_path_segments=excluded_path_segments,
    )

    failed = [name for name, ok in report.checks.items() if not ok]
    if report.score < config.AUDIT_REGENERATE_THRESHOLD:
        action = "REGENERATE"
    elif report.score < config.AUDIT_MANUAL_REVIEW_THRESHOLD:
        action = "MANUAL_REVIEW"
    else:
        action = "KEEP"

    return AuditScore(
        url=url,
        score=report.score,
        action=action,
        failed_checks=failed,
        notes=report.notes,
    )
