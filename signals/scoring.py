from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceResult:
    confidence_score: float
    verdict: str


def combine_signal_scores(signal_1_score: float, signal_2_score: float) -> float:
    """Combine the two signal scores using the planned 50/50 weighting."""
    combined_score = (signal_1_score * 0.5) + (signal_2_score * 0.5)
    return max(0.0, min(1.0, combined_score))


def score_to_verdict(confidence_score: float) -> str:
    if confidence_score <= 0.40:
        return "likely_human"
    if confidence_score < 0.70:
        return "uncertain"
    return "likely_ai"


def combine_scores(signal_1_score: float, signal_2_score: float) -> ConfidenceResult:
    confidence_score = combine_signal_scores(signal_1_score, signal_2_score)
    return ConfidenceResult(
        confidence_score=confidence_score,
        verdict=score_to_verdict(confidence_score),
    )