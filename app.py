import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request
from dotenv import find_dotenv, load_dotenv

from signals.first_signal import classify_ai_probability

load_dotenv(find_dotenv(), override=False)

app = Flask(__name__)

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.jsonl"


def write_audit_log(content_id: str, signal_1_result: str) -> None:
    """Append one structured audit entry as JSONL."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_id": content_id,
        "signal_1_result": signal_1_result,
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
        attribution_result = "likely_ai" if signal_1_score >= 0.5 else "likely_human"
        signal_1_error = None
    except Exception as exc:
        signal_1_score = None
        attribution_result = "unknown"
        signal_1_error = str(exc)

    write_audit_log(content_id, attribution_result)

    return (
        jsonify(
            {
                "status": "accepted",
                "message": "submit route is working",
                "content_id": content_id,
                "creator_id": creator_id,
                "signal_1_attribution_result": attribution_result,
                "signal_1_score": signal_1_score,
                "signal_1_error": signal_1_error,
                "confidence_score": 0.5,
                "label": "placeholder_label",
            }
        ),
        200,
    )


if __name__ == "__main__":
    app.run(debug=True)
