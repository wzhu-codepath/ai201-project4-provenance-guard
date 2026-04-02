import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request
from dotenv import find_dotenv, load_dotenv
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address

from signals.first_signal import classify_ai_probability
from signals.scoring import combine_scores
from signals.second_signal import classify_stylometric_probability
from signals.labels import generate_label

load_dotenv(find_dotenv(), override=False)

app = Flask(__name__)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.jsonl"
CONTENT_STORE_PATH = Path(__file__).resolve().parent / "content_store.json"


def submission_rate_limit_key() -> str:
    """Prefer creator_id for fair per-writer limits, then fall back to the client IP."""
    payload = request.get_json(silent=True) or {}
    creator_id = payload.get("creator_id")

    if isinstance(creator_id, str) and creator_id.strip():
        return f"creator:{creator_id.strip()}"

    return get_remote_address()


@app.errorhandler(RateLimitExceeded)
def handle_rate_limit_exceeded(exc: RateLimitExceeded) -> tuple:
    return jsonify({"error": "rate limit exceeded", "message": str(exc)}), 429


def load_content_store() -> dict[str, dict]:
    """Load the current content status store from disk."""
    if not CONTENT_STORE_PATH.exists():
        return {}

    try:
        with CONTENT_STORE_PATH.open("r", encoding="utf-8") as store_file:
            data = json.load(store_file)
    except (json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def save_content_store(content_store: dict[str, dict]) -> None:
    """Persist the content status store to disk."""
    with CONTENT_STORE_PATH.open("w", encoding="utf-8") as store_file:
        json.dump(content_store, store_file, indent=2, sort_keys=True)
        store_file.write("\n")


def update_content_status(
    content_id: str,
    status: str,
    *,
    creator_id: str | None = None,
    original_decision: dict | None = None,
    appeal_statement: str | None = None,
) -> dict:
    """Update the stored status for a piece of content."""
    content_store = load_content_store()
    record = content_store.get(content_id, {})

    record["content_id"] = content_id
    record["status"] = status
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    if creator_id:
        record["creator_id"] = creator_id
    if original_decision:
        record["original_decision"] = original_decision
    if appeal_statement:
        record["appeal_statement"] = appeal_statement

    content_store[content_id] = record
    save_content_store(content_store)
    return record


def write_audit_log(
    content_id: str,
    attribution_result: str,
    signal_1_score: float | None = None,
    signal_2_score: float | None = None,
    confidence_score: float | None = None,
    status: str = "classified",
    appeal_filed: bool = False,
    appeal_statement: str | None = None,
    creator_id: str | None = None,
    original_decision: dict | None = None,
) -> None:
    """Append one structured audit entry as JSONL with both signals, combined confidence, and status tracking."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_id": content_id,
        "signal_1_score": signal_1_score,
        "signal_2_score": signal_2_score,
        "combined_confidence_score": confidence_score,
        "combined_attribution_result": attribution_result,
        "status": status,
        "appeal_filed": appeal_filed,
    }
    if appeal_statement:
        entry["appeal_statement"] = appeal_statement
    if creator_id:
        entry["creator_id"] = creator_id
    if original_decision:
        entry["original_decision"] = original_decision
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def get_content_original_decision(content_id: str) -> dict | None:
    """
    Retrieve the original classification decision for a content_id from the audit log.
    Returns the most recent classified entry for the content_id, or None if not found.
    """
    if not AUDIT_LOG_PATH.exists():
        return None
    
    original_decision = None
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            try:
                entry = json.loads(line)
                if entry.get("content_id") == content_id and entry.get("status") == "classified":
                    original_decision = entry
            except json.JSONDecodeError:
                continue
    
    return original_decision


@app.post("/submit")
@limiter.limit("30 per hour", key_func=submission_rate_limit_key)
@limiter.limit("5 per minute", key_func=submission_rate_limit_key)
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
        label_info = generate_label(confidence_score)
    else:
        confidence_score = None
        attribution_result = "unknown"
        label_info = None

    write_audit_log(
        content_id,
        attribution_result,
        signal_1_score=signal_1_score,
        signal_2_score=signal_2_score,
        confidence_score=confidence_score,
        status="classified",
        appeal_filed=False,
        creator_id=creator_id,
    )

    update_content_status(
        content_id,
        "classified",
        creator_id=creator_id,
        original_decision={
            "combined_attribution_result": attribution_result,
            "combined_confidence_score": confidence_score,
            "signal_1_score": signal_1_score,
            "signal_2_score": signal_2_score,
        },
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
                "transparency_label": {
                    "variant": label_info.get("variant"),
                    "verdict": label_info.get("verdict"),
                    "text": label_info.get("label"),
                } if label_info else None,
            }
        ),
        200,
    )


@app.post("/appeal")
def appeal() -> tuple:
    """Record an appeal, update the stored status, and preserve the original decision."""
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id")
    statement = payload.get("statement")
    creator_id = payload.get("creator_id")

    if not content_id or not isinstance(content_id, str):
        return jsonify({"error": "content_id is required"}), 400

    if not statement or not isinstance(statement, str):
        return jsonify({"error": "statement is required"}), 400

    original_decision = get_content_original_decision(content_id)

    if not original_decision:
        return jsonify({"error": f"Content with ID {content_id} not found"}), 404

    original_attribution = original_decision.get("combined_attribution_result")
    original_confidence = original_decision.get("combined_confidence_score")
    original_timestamp = original_decision.get("timestamp")

    update_content_status(
        content_id,
        "under_review",
        creator_id=creator_id,
        original_decision=original_decision,
        appeal_statement=statement,
    )

    write_audit_log(
        content_id=content_id,
        attribution_result=original_attribution,
        signal_1_score=original_decision.get("signal_1_score"),
        signal_2_score=original_decision.get("signal_2_score"),
        confidence_score=original_confidence,
        status="under_review",
        appeal_filed=True,
        appeal_statement=statement,
        creator_id=creator_id,
        original_decision=original_decision,
    )
    
    return (
        jsonify(
            {
                "status": "accepted",
                "message": "Appeal submitted for review",
                "content_id": content_id,
                "appeal_status": "under_review",
                "original_decision": original_attribution,
                "original_confidence_score": original_confidence,
                "original_decision_timestamp": original_timestamp,
            }
        ),
        202,
    )


if __name__ == "__main__":
    app.run(debug=True)
