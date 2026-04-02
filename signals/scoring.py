from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceResult:
    confidence_score: float
    verdict: str


def combine_signal_scores(signal_1_score: float, signal_2_score: float) -> float:
    """Combine signal scores with a 70/30 weighting favoring Signal 1."""
    combined_score = (signal_1_score * 0.7) + (signal_2_score * 0.3)
    return max(0.0, min(1.0, combined_score))


def score_to_verdict(confidence_score: float) -> str:
    if confidence_score <= 0.40:
        return "likely_human"
    if confidence_score < 0.68:
        return "uncertain"
    return "likely_ai"


def combine_scores(signal_1_score: float, signal_2_score: float) -> ConfidenceResult:
    confidence_score = combine_signal_scores(signal_1_score, signal_2_score)
    return ConfidenceResult(
        confidence_score=confidence_score,
        verdict=score_to_verdict(confidence_score),
    )