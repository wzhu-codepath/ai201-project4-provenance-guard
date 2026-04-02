import unittest
from unittest.mock import MagicMock, patch

from signals.first_signal import classify_ai_probability
from signals.second_signal import classify_stylometric_probability
from signals.scoring import combine_scores, combine_signal_scores, score_to_verdict
from signals.labels import generate_label


HUMAN_TEXT = (
    "I went to the store after work. I bought milk, bread, and apples. "
    "Then I went home and cooked dinner."
)

AI_LIKE_TEXT = (
    "The report was completed. The report was reviewed. The report was approved. "
    "The report was filed."
)

# Highly polished, uniform AI-like paragraph
POLISHED_UNIFORM_TEXT = (
    "The implementation of advanced methodologies and structured frameworks represents a "
    "critical component in the optimization of operational efficiency. The systematic approach "
    "to knowledge management facilitates enhanced organizational capacity. Furthermore, the integration "
    "of comprehensive strategies demonstrates a commitment to excellence and sustainable development."
)

# Casual, irregular human-like text
CASUAL_IRREGULAR_TEXT = (
    "So I went to the store right? and like... I didn't even have a list lol. "
    "Grabbed milk. then bread. wait, also apples?? went home and was like... "
    "dinner time I guess. made some pasta idk what else. it was good tho!"
)


class SecondSignalTests(unittest.TestCase):
    def test_classify_stylometric_probability_is_bounded(self) -> None:
        for text in (HUMAN_TEXT, AI_LIKE_TEXT):
            score = classify_stylometric_probability(text)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_classify_stylometric_probability_is_higher_for_repetitive_text(self) -> None:
        human_score = classify_stylometric_probability(HUMAN_TEXT)
        ai_like_score = classify_stylometric_probability(AI_LIKE_TEXT)

        self.assertGreater(ai_like_score, human_score)


class SignalComparisonTests(unittest.TestCase):
    def test_first_and_second_signals_both_rank_the_same_texts(self) -> None:
        def make_completion(score: float) -> MagicMock:
            message = MagicMock(content=f'{{"ai_probability": {score}}}')
            choice = MagicMock(message=message)
            return MagicMock(choices=[choice])

        def fake_create(*args, **kwargs):
            user_prompt = kwargs["messages"][1]["content"]
            text = user_prompt.split("TEXT:\n", 1)[1]

            if text == HUMAN_TEXT:
                return make_completion(0.12)
            if text == AI_LIKE_TEXT:
                return make_completion(0.88)

            raise AssertionError(f"Unexpected text passed to mocked Groq client: {text!r}")

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create

        with patch("signals.first_signal.os.getenv", side_effect=lambda key, default=None: {
            "GROQ_API_KEY": "test-api-key",
            "GROQ_MODEL": "test-model",
        }.get(key, default)), patch("signals.first_signal.Groq", return_value=fake_client):
            human_first_score = classify_ai_probability(HUMAN_TEXT)
            ai_like_first_score = classify_ai_probability(AI_LIKE_TEXT)

        human_second_score = classify_stylometric_probability(HUMAN_TEXT)
        ai_like_second_score = classify_stylometric_probability(AI_LIKE_TEXT)

        self.assertLess(human_first_score, ai_like_first_score)
        self.assertLess(human_second_score, ai_like_second_score)


class ScoringTests(unittest.TestCase):
    def test_combine_signal_scores_uses_signal_1_heavy_weighting(self) -> None:
        self.assertEqual(combine_signal_scores(0.0, 1.0), 0.3)
        self.assertEqual(combine_signal_scores(1.0, 0.0), 0.7)
        self.assertEqual(combine_signal_scores(0.2, 0.8), 0.38)

    def test_score_to_verdict_matches_documented_thresholds(self) -> None:
        self.assertEqual(score_to_verdict(0.40), "likely_human")
        self.assertEqual(score_to_verdict(0.41), "uncertain")
        self.assertEqual(score_to_verdict(0.67), "uncertain")
        self.assertEqual(score_to_verdict(0.68), "likely_ai")

    def test_combine_scores_returns_confidence_result(self) -> None:
        result = combine_scores(0.10, 0.90)

        self.assertEqual(result.confidence_score, 0.34)
        self.assertEqual(result.verdict, "likely_human")


class TransparencyLabelTests(unittest.TestCase):
    def test_generate_label_variant_a_likely_human(self) -> None:
        """Test Variant A: score 0.00-0.40 returns 'Likely Human' label."""
        # Test lower boundary
        result = generate_label(0.00)
        self.assertEqual(result["variant"], "A")
        self.assertEqual(result["verdict"], "likely_human")
        self.assertIn("human likely wrote", result["label"])
        
        # Test mid-range
        result = generate_label(0.20)
        self.assertEqual(result["variant"], "A")
        self.assertIn("human likely wrote", result["label"])
        
        # Test upper boundary
        result = generate_label(0.40)
        self.assertEqual(result["variant"], "A")
        self.assertIn("human likely wrote", result["label"])

    def test_generate_label_variant_b_uncertain(self) -> None:
        """Test Variant B: score 0.41-0.67 returns 'Uncertain' label."""
        # Test lower boundary
        result = generate_label(0.41)
        self.assertEqual(result["variant"], "B")
        self.assertEqual(result["verdict"], "uncertain")
        self.assertIn("human or an AI", result["label"])
        
        # Test mid-range
        result = generate_label(0.55)
        self.assertEqual(result["variant"], "B")
        self.assertIn("human or an AI", result["label"])
        
        # Test upper boundary
        result = generate_label(0.67)
        self.assertEqual(result["variant"], "B")
        self.assertIn("human or an AI", result["label"])

    def test_generate_label_variant_c_likely_ai(self) -> None:
        """Test Variant C: score 0.68-1.00 returns 'Likely AI' label."""
        # Test lower boundary
        result = generate_label(0.68)
        self.assertEqual(result["variant"], "C")
        self.assertEqual(result["verdict"], "likely_ai")
        self.assertIn("AI agent likely wrote", result["label"])
        
        # Test mid-range
        result = generate_label(0.85)
        self.assertEqual(result["variant"], "C")
        self.assertIn("AI agent likely wrote", result["label"])
        
        # Test upper boundary
        result = generate_label(1.00)
        self.assertEqual(result["variant"], "C")
        self.assertIn("AI agent likely wrote", result["label"])

    def test_generate_label_includes_appeal_message(self) -> None:
        """Test that all variants include the appeal statement."""
        for score in [0.20, 0.55, 0.85]:
            result = generate_label(score)
            self.assertIn("appeal", result["label"].lower())


class VerificationTests(unittest.TestCase):
    """Verify that the combined scoring varies meaningfully and covers all three categories."""

    def test_combined_score_produces_varied_outputs(self) -> None:
        """Different inputs should produce different stylometric scores."""
        scores = []
        for text in [HUMAN_TEXT, AI_LIKE_TEXT, POLISHED_UNIFORM_TEXT, CASUAL_IRREGULAR_TEXT]:
            s2_score = classify_stylometric_probability(text)
            scores.append(s2_score)

        # Verify not all scores are identical (meaningful variation exists)
        unique_scores = len(set(scores))
        self.assertGreater(unique_scores, 1,
            f"Expected varied scores across inputs, but got: {scores}")

    def test_all_three_verdict_categories_are_represented(self) -> None:
        """The scoring should produce all three distinct verdicts across varied inputs."""
        verdicts = set()

        # Test across a range of combined scores that should hit all three categories
        test_cases = [
            (0.10, 0.15),  # Low scores -> likely_human
            (0.45, 0.50),  # Mid scores -> uncertain
            (0.80, 0.95),  # High scores -> likely_ai
        ]

        for signal_1, signal_2 in test_cases:
            result = combine_scores(signal_1, signal_2)
            verdicts.add(result.verdict)

        # Verify all three categories are represented
        expected_verdicts = {"likely_human", "uncertain", "likely_ai"}
        self.assertEqual(verdicts, expected_verdicts,
            "All three verdict categories should be represented across the score range")

    def test_real_signal_outputs_produce_range_of_verdicts(self) -> None:
        """Run signal 2 on varied inputs and verify combined scores span the verdict range."""
        test_samples = [
            CASUAL_IRREGULAR_TEXT,
            AI_LIKE_TEXT,
            POLISHED_UNIFORM_TEXT,
        ]

        results = []
        for text in test_samples:
            s2_score = classify_stylometric_probability(text)
            # Test with different signal 1 values to see full range with signal 2
            for s1_score in [0.1, 0.5, 0.9]:
                result = combine_scores(s1_score, s2_score)
                results.append((text[:30] + "...", s1_score, s2_score, result.confidence_score, result.verdict))

        # Verify we get at least 2 different verdict categories across the combinations
        verdicts = {r[4] for r in results}
        self.assertGreater(len(verdicts), 1,
            f"Expected varied verdicts across signal combinations, but got verdicts: {verdicts}\nDetails: {results}")


class DeliberatelyChosenInputsTests(unittest.TestCase):
    """Test the 4 deliberately chosen inputs: clearly AI, clearly human, and two borderlines."""

    CLEARLY_AI_TEXT = (
        "Implementing robust methodologies, and structured decision-making frameworks "
        "represent critical components in optimizing operational efficiency. The systematic "
        "approach to comprehensive strategy integration facilitates enhanced organizational capacity. "
        "Furthermore, leveraging advanced technological solutions and best practices demonstrates "
        "commitment to sustainable growth and excellence."
    )

    CLEARLY_HUMAN_TEXT = (
        "I was getting food with my friend yesterday and man she said something really crazy"
        "about how her dog was fighting some random chicken in the middle of the street/"
        "When she showed me the video of it happening, I died laughing"
    )

    BORDERLINE_1_TEXT = (
        "The concept of digital transformation has become increasingly important in modern organizations. "
        "I believe it's essential to understand both the benefits and challenges involved. "
        "Many companies are now investing heavily in cloud infrastructure and data analytics. "
        "What's your take on this trend?"
    )

    BORDERLINE_2_TEXT = (
        "So I've been thinking a lot about productivity lately right? Like how do you actually "
        "get stuff done without burning out. Some people swear by time blocking, others do the "
        "Pomodoro thing. I'm not sure what works best tbh, probably different for everyone."
    )

    def test_clearly_ai_text_scores_high(self) -> None:
        """AI-generated text with corporate jargon should score high on Signal 1 or average high."""
        def make_completion(score: float) -> MagicMock:
            message = MagicMock(content=f'{{"ai_probability": {score}}}')
            choice = MagicMock(message=message)
            return MagicMock(choices=[choice])

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = make_completion(0.82)

        with patch("signals.first_signal.os.getenv", side_effect=lambda key, default=None: {
            "GROQ_API_KEY": "test-api-key",
            "GROQ_MODEL": "test-model",
        }.get(key, default)), patch("signals.first_signal.Groq", return_value=fake_client):
            s1_score = classify_ai_probability(self.CLEARLY_AI_TEXT)

        s2_score = classify_stylometric_probability(self.CLEARLY_AI_TEXT)
        result = combine_scores(s1_score, s2_score)

        # Signal 1 should catch corporate language as AI
        self.assertGreater(s1_score, 0.7, "Signal 1 should detect corporate jargon as AI-like")
        # Combined score should be at least uncertain or higher
        self.assertGreaterEqual(result.confidence_score, 0.41, "Combined score should be at least uncertain")

    def test_clearly_human_text_scores_low(self) -> None:
        """Human-written text with personal narrative should score low on both signals."""
        def make_completion(score: float) -> MagicMock:
            message = MagicMock(content=f'{{"ai_probability": {score}}}')
            choice = MagicMock(message=message)
            return MagicMock(choices=[choice])

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = make_completion(0.15)

        with patch("signals.first_signal.os.getenv", side_effect=lambda key, default=None: {
            "GROQ_API_KEY": "test-api-key",
            "GROQ_MODEL": "test-model",
        }.get(key, default)), patch("signals.first_signal.Groq", return_value=fake_client):
            s1_score = classify_ai_probability(self.CLEARLY_HUMAN_TEXT)

        s2_score = classify_stylometric_probability(self.CLEARLY_HUMAN_TEXT)
        result = combine_scores(s1_score, s2_score)

        # Combined score should be likely_human
        self.assertEqual(result.verdict, "likely_human", "Personal narrative should score as likely_human")
        self.assertLess(result.confidence_score, 0.41, "Combined score should be below 0.41 for likely_human")

    def test_borderline_inputs_generate_varied_verdicts(self) -> None:
        """Borderline cases may produce different verdicts depending on both signals."""
        def make_completion_for_text(text: str) -> MagicMock:
            if text == self.BORDERLINE_1_TEXT:
                score = 0.55
            elif text == self.BORDERLINE_2_TEXT:
                score = 0.25
            else:
                score = 0.5
            message = MagicMock(content=f'{{"ai_probability": {score}}}')
            choice = MagicMock(message=message)
            return MagicMock(choices=[choice])

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = lambda *args, **kwargs: make_completion_for_text(
            kwargs["messages"][1]["content"].split("TEXT:\n", 1)[1]
        )

        with patch("signals.first_signal.os.getenv", side_effect=lambda key, default=None: {
            "GROQ_API_KEY": "test-api-key",
            "GROQ_MODEL": "test-model",
        }.get(key, default)), patch("signals.first_signal.Groq", return_value=fake_client):
            s1_borderline_1 = classify_ai_probability(self.BORDERLINE_1_TEXT)
            s1_borderline_2 = classify_ai_probability(self.BORDERLINE_2_TEXT)

        s2_borderline_1 = classify_stylometric_probability(self.BORDERLINE_1_TEXT)
        s2_borderline_2 = classify_stylometric_probability(self.BORDERLINE_2_TEXT)

        result_1 = combine_scores(s1_borderline_1, s2_borderline_1)
        result_2 = combine_scores(s1_borderline_2, s2_borderline_2)

        # Both borderline cases should produce valid verdicts
        self.assertIn(result_1.verdict, {"likely_human", "uncertain", "likely_ai"})
        self.assertIn(result_2.verdict, {"likely_human", "uncertain", "likely_ai"})
        # The two borderline cases may differ
        self.assertTrue(
            result_1.confidence_score != result_2.confidence_score or result_1.verdict != result_2.verdict,
            "At least one signal component should differ between the two borderline cases"
        )


class AuditLogTests(unittest.TestCase):
    """Test that audit log captures both signal scores and combined confidence."""

    def test_audit_log_structure_captures_all_signals(self) -> None:
        """Verify that the audit log entry captures signal 1, signal 2, and combined confidence."""
        from app import write_audit_log
        from pathlib import Path
        import json
        import tempfile

        # Create a temporary audit log
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Mock the AUDIT_LOG_PATH to point to our temp file
            with patch("app.AUDIT_LOG_PATH", Path(tmp_path)):
                # Write a test entry with both signal scores
                write_audit_log(
                    content_id="test-001",
                    attribution_result="likely_ai",
                    signal_1_score=0.75,
                    signal_2_score=0.65,
                    confidence_score=0.70,
                )

                # Read the audit log and verify structure
                with open(tmp_path, "r") as f:
                    entry = json.loads(f.readline())

                # Verify all required fields are present
                self.assertIn("timestamp", entry)
                self.assertIn("content_id", entry)
                self.assertIn("signal_1_score", entry)
                self.assertIn("signal_2_score", entry)
                self.assertIn("combined_confidence_score", entry)
                self.assertIn("combined_attribution_result", entry)
                self.assertIn("appeal_filed", entry)

                # Verify the values
                self.assertEqual(entry["content_id"], "test-001")
                self.assertEqual(entry["signal_1_score"], 0.75)
                self.assertEqual(entry["signal_2_score"], 0.65)
                self.assertEqual(entry["combined_confidence_score"], 0.70)
                self.assertEqual(entry["combined_attribution_result"], "likely_ai")
                self.assertFalse(entry["appeal_filed"])
        finally:
            # Clean up
            Path(tmp_path).unlink(missing_ok=True)

    def test_audit_log_handles_none_scores(self) -> None:
        """Verify audit log correctly captures None values for failed signals."""
        from app import write_audit_log
        from pathlib import Path
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("app.AUDIT_LOG_PATH", Path(tmp_path)):
                # Write an entry when signal 1 fails but signal 2 succeeds
                write_audit_log(
                    content_id="test-002",
                    attribution_result="unknown",
                    signal_1_score=None,
                    signal_2_score=0.55,
                    confidence_score=None,
                )

                with open(tmp_path, "r") as f:
                    entry = json.loads(f.readline())

                # Verify None values are preserved
                self.assertIsNone(entry["signal_1_score"])
                self.assertEqual(entry["signal_2_score"], 0.55)
                self.assertIsNone(entry["combined_confidence_score"])
                self.assertEqual(entry["combined_attribution_result"], "unknown")
                self.assertFalse(entry["appeal_filed"])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_audit_log_marks_appeals_explicitly(self) -> None:
        """Verify appeal audit entries explicitly record that an appeal was filed."""
        from app import write_audit_log
        from pathlib import Path
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("app.AUDIT_LOG_PATH", Path(tmp_path)):
                write_audit_log(
                    content_id="test-appeal-001",
                    attribution_result="likely_human",
                    signal_1_score=0.25,
                    signal_2_score=0.35,
                    confidence_score=0.30,
                    status="under_review",
                    appeal_filed=True,
                    appeal_statement="Please review this submission again.",
                )

                with open(tmp_path, "r") as f:
                    entry = json.loads(f.readline())

                self.assertTrue(entry["appeal_filed"])
                self.assertEqual(entry["status"], "under_review")
                self.assertEqual(entry["content_id"], "test-appeal-001")
                self.assertEqual(
                    entry["appeal_statement"],
                    "Please review this submission again.",
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()