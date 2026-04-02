import json
import os
from typing import Any

from dotenv import find_dotenv, load_dotenv
from groq import Groq

load_dotenv(find_dotenv(), override=False)


def _extract_probability(raw_text: str) -> float:
    """Extract and clamp ai_probability from the model response text."""
    try:
        data: Any = json.loads(raw_text)
        value = float(data["ai_probability"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unable to parse ai_probability from model output: {raw_text}") from exc

    return max(0.0, min(1.0, value))


def classify_ai_probability(text: str) -> float:
    """
    Signal 1: LLM-based classifier.

    Returns:
        float: Probability in [0.0, 1.0] where 1.0 means likely AI-generated.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a text-authorship classifier. Analyze whether a passage is likely "
        "human-written or AI-generated. Return ONLY valid JSON with this schema: "
        "{\"ai_probability\": <float between 0 and 1>}"
    )

    user_prompt = (
        "Classify the following text. Higher values indicate more likely AI-generated.\n\n"
        f"TEXT:\n{text}"
    )

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw_content = completion.choices[0].message.content or "{}"
    return _extract_probability(raw_content)
