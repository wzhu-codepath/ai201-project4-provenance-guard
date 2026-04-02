import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request
from dotenv import find_dotenv, load_dotenv

from signals.first_signal import classify_ai_probability
from signals.scoring import combine_scores
from signals.second_signal import classify_stylometric_probability

load_dotenv(find_dotenv(), override=False)

app = Flask(__name__)

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.jsonl"


def write_audit_log(
    content_id: str,
    attribution_result: str,
    signal_1_score: float | None = None,
    signal_2_score: float | None = None,
    confidence_score: float | None = None,
) -> None:
    """Append one structured audit entry as JSONL with both signals and combined confidence."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_id": content_id,
        "signal_1_score": signal_1_score,
        "signal_2_score": signal_2_score,
        "combined_confidence_score": confidence_score,
        "combined_attribution_result": attribution_result,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry) + "\n")


@app.post("/submit")
def submit() -> tuple:
    """
    Submission endpoint stub.

    Request JSON:
      - text: str
      - creator_id: str

    Runs first signal and returns placeholder production fields.
    """
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    creator_id = payload.get("creator_id")
    content_id = payload.get("content_id")

    if not content_id or not isinstance(content_id, str):
        content_id = str(uuid4())

    if not text or not isinstance(text, str):
        write_audit_log(content_id, "not_evaluated")
        return jsonify({"error": "text is required"}), 400

    if not creator_id or not isinstance(creator_id, str):
        write_audit_log(content_id, "not_evaluated")
        return jsonify({"error": "creator_id is required"}), 400

    try:
        signal_1_score = classify_ai_probability(text)
        signal_1_error = None
    except Exception as exc:
        signal_1_score = None
        signal_1_error = str(exc)

    try:
        signal_2_score = classify_stylometric_probability(text)
        signal_2_error = None
    except Exception as exc:
        signal_2_score = None
        signal_2_error = str(exc)

    if signal_1_score is not None and signal_2_score is not None:
        confidence_result = combine_scores(signal_1_score, signal_2_score)
        attribution_result = confidence_result.verdict
        confidence_score = confidence_result.confidence_score
    else:
        confidence_score = None
        attribution_result = "unknown"

    write_audit_log(
        content_id,
        attribution_result,
        signal_1_score=signal_1_score,
        signal_2_score=signal_2_score,
        confidence_score=confidence_score,
    )

    return (
        jsonify(
            {
                "status": "accepted",
                "message": "submit route is working",
                "content_id": content_id,
                "creator_id": creator_id,
                "combined_attribution_result": attribution_result,
                "signal_1_attribution_result": None if signal_1_score is None else (
                    "likely_ai" if signal_1_score >= 0.5 else "likely_human"
                ),
                "signal_1_score": signal_1_score,
                "signal_1_error": signal_1_error,
                "signal_2_score": signal_2_score,
                "signal_2_error": signal_2_error,
                "confidence_score": confidence_score,
                "label": attribution_result,
            }
        ),
        200,
    )


if __name__ == "__main__":
    app.run(debug=True)
