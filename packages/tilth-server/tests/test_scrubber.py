"""Tests for PII scrubbing."""

from unittest.mock import MagicMock

from tilth_server.ingest.scrubber import scrub_text


class TestScrubber:
    def test_email_replaced_with_token(self) -> None:
        """An email in text is replaced with a Presidio-style token."""
        mock_analyzer = MagicMock()
        mock_anonymizer = MagicMock()

        # Simulate Presidio finding an email
        from presidio_analyzer import RecognizerResult

        finding = RecognizerResult(
            entity_type="EMAIL_ADDRESS",
            start=10,
            end=28,
            score=0.99,
        )
        mock_analyzer.analyze.return_value = [finding]
        mock_anonymizer.anonymize.return_value = MagicMock(
            text="Contact <EMAIL_ADDRESS> for help"
        )

        result = scrub_text(
            "Contact user@example.com for help",
            analyzer=mock_analyzer,
            anonymizer=mock_anonymizer,
        )
        assert "<EMAIL_ADDRESS>" in result
        assert "user@example.com" not in result

    def test_no_pii_returns_original(self) -> None:
        mock_analyzer = MagicMock()
        mock_anonymizer = MagicMock()
        mock_analyzer.analyze.return_value = []

        result = scrub_text(
            "No PII here",
            analyzer=mock_analyzer,
            anonymizer=mock_anonymizer,
        )
        assert result == "No PII here"

    def test_analyzer_called_with_correct_entities(self) -> None:
        mock_analyzer = MagicMock()
        mock_anonymizer = MagicMock()
        mock_analyzer.analyze.return_value = []

        scrub_text("test text", analyzer=mock_analyzer, anonymizer=mock_anonymizer)

        call_kwargs = mock_analyzer.analyze.call_args
        assert call_kwargs.kwargs["language"] == "en"
        entities = call_kwargs.kwargs["entities"]
        assert "EMAIL_ADDRESS" in entities
        assert "CREDIT_CARD" in entities
        assert "US_SSN" in entities
        assert "PHONE_NUMBER" in entities
        assert "IP_ADDRESS" in entities
        assert "IBAN_CODE" in entities
