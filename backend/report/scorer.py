from __future__ import annotations

"""Production readiness scorer for code-review findings."""


# ---------------------------------------------------------------------------
# Weights (penalty per finding of each type)
# ---------------------------------------------------------------------------

_PENALTIES: dict[tuple[str, str], float] = {
    ("critical", "security"): 20.0,
    ("critical", "bug"): 15.0,
    ("high", "security"): 10.0,
    ("high", "bug"): 8.0,
    ("high", "coverage"): 5.0,
}

_MEDIUM_PENALTY = 3.0
_LOW_PENALTY = 1.0

# If any CRITICAL security finding exists, score is capped here.
_CRITICAL_SECURITY_CAP = 30.0


def calculate_production_score(findings: list[dict]) -> tuple[float, str]:
    """Return a (score, verdict) tuple.

    Score is 0–100 calculated as:
        base = 100
        subtract weighted penalties for each finding
        clamp to [0, 100]
        if any CRITICAL security finding exists, cap at 30

    Verdict thresholds:
        score < 50   -> NOT PRODUCTION READY
        50 <= score < 75 -> NEEDS IMPROVEMENT
        score >= 75  -> PRODUCTION READY
    """
    score: float = 100.0
    has_critical_security = False

    for f in findings:
        severity = (f.get("severity") or "info").lower()
        agent = (f.get("agent") or "bug").lower()

        # Check for CRITICAL security early so we can cap later.
        if severity == "critical" and agent == "security":
            has_critical_security = True

        # Look up a specific penalty first.
        key = (severity, agent)
        if key in _PENALTIES:
            score -= _PENALTIES[key]
        elif severity == "medium":
            score -= _MEDIUM_PENALTY
        elif severity == "low":
            score -= _LOW_PENALTY
        # INFO findings carry no penalty.

    # Clamp to [0, 100]
    score = max(0.0, min(100.0, score))

    # Cap when CRITICAL security finding exists
    if has_critical_security:
        score = min(score, _CRITICAL_SECURITY_CAP)

    score = round(score, 2)

    if score < 50.0:
        verdict = "NOT PRODUCTION READY"
    elif score < 75.0:
        verdict = "NEEDS IMPROVEMENT"
    else:
        verdict = "PRODUCTION READY"

    return score, verdict


def severity_summary(findings: list[dict]) -> dict[str, int]:
    """Return counts keyed by severity level."""
    counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }
    for f in findings:
        key = (f.get("severity") or "info").lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def agent_summary(findings: list[dict]) -> dict[str, int]:
    """Return counts keyed by agent type."""
    counts: dict[str, int] = {
        "bug": 0,
        "security": 0,
        "coverage": 0,
    }
    for f in findings:
        key = (f.get("agent") or "bug").lower()
        counts[key] = counts.get(key, 0) + 1
    return counts
