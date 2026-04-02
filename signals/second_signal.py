import math
import re


_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"\b[\w']+\b")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _split_sentences(text: str) -> list[str]:
    sentences = [segment.strip() for segment in _SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    return sentences or [text.strip()]


def _sentence_length_variance_score(text: str) -> float:
    sentences = _split_sentences(text)
    lengths = [len(_WORD_RE.findall(sentence)) for sentence in sentences if sentence]
    if len(lengths) < 2:
        return 0.5

    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5

    variance = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    cv = math.sqrt(variance) / mean

    # More uniform sentence lengths are treated as more AI-like.
    score = 1.0 - min(cv / 1.5, 1.0)
    return _clamp(score)


def _type_token_ratio_score(text: str) -> float:
    words = [word.lower() for word in _WORD_RE.findall(text)]
    if not words:
        return 0.5

    unique_ratio = len(set(words)) / len(words)

    # Lower lexical diversity is treated as more AI-like.
    score = 1.0 - unique_ratio
    return _clamp(score)


def _punctuation_density_score(text: str) -> float:
    non_space_chars = [char for char in text if not char.isspace()]
    if not non_space_chars:
        return 0.5

    punctuation_chars = sum(1 for char in non_space_chars if not char.isalnum())
    density = punctuation_chars / len(non_space_chars)

    # Higher punctuation density is treated as more AI-like.
    score = min(density / 0.20, 1.0)
    return _clamp(score)


def classify_stylometric_probability(text: str) -> float:
    """
    Signal 2: stylometric heuristics classifier.

    Returns:
        float: Probability in [0.0, 1.0] where 1.0 means likely AI-generated.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    sentence_length_score = _sentence_length_variance_score(text)
    type_token_ratio_score = _type_token_ratio_score(text)
    punctuation_density_score = _punctuation_density_score(text)

    return _clamp(
        (sentence_length_score + type_token_ratio_score + punctuation_density_score) / 3.0
    )