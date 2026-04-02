"""Label generation function that maps confidence scores to transparency labels."""


def generate_label(confidence_score: float) -> dict:
    """
    Map a confidence score to a transparency label variant.
    
    Args:
        confidence_score: A float between 0.0 and 1.0
        
    Returns:
        A dictionary with variant (A, B, or C) and label text
        
    Thresholds:
        - 0.00 - 0.40 = Likely Human (Variant A)
        - 0.41 - 0.67 = Uncertain (Variant B)
        - 0.68 - 1.00 = Likely AI (Variant C)
    """
    if confidence_score <= 0.40:
        return {
            "variant": "A",
            "verdict": "likely_human",
            "label": "A human likely wrote this text. If something seems wrong, an appeal can be submitted.",
        }
    elif confidence_score < 0.68:
        return {
            "variant": "B",
            "verdict": "uncertain",
            "label": "Unsure if a human or an AI agent wrote it. If something seems wrong, an appeal can be submitted.",
        }
    else:
        return {
            "variant": "C",
            "verdict": "likely_ai",
            "label": "An AI agent likely wrote this text. If something seems wrong, an appeal can be submitted.",
        }
