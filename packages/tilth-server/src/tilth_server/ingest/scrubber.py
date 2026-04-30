"""Presidio PII scrubbing."""

from __future__ import annotations

from typing import Any

PII_ENTITIES = [
    "EMAIL_ADDRESS",
    "CREDIT_CARD",
    "US_SSN",
    "PHONE_NUMBER",
    "IP_ADDRESS",
    "IBAN_CODE",
]


def scrub_text(
    text: str,
    analyzer: Any,
    anonymizer: Any,
) -> str:
    """Run Presidio scrubber on text, replacing PII with type tokens.

    Args:
        text: the text to scrub.
        analyzer: a PresidioAnalyzerEngine instance.
        anonymizer: a PresidioAnonymizerEngine instance.

    Returns:
        The scrubbed text with PII replaced by tokens like <EMAIL_ADDRESS>.
    """
    findings = analyzer.analyze(
        text=text,
        entities=PII_ENTITIES,
        language="en",
    )
    if not findings:
        return text
    return anonymizer.anonymize(text=text, analyzer_results=findings).text


def create_analyzer() -> Any:
    """Create and warm a Presidio AnalyzerEngine."""
    from presidio_analyzer import AnalyzerEngine

    engine = AnalyzerEngine()
    # Warm the spaCy model
    engine.analyze(text="warm up", entities=PII_ENTITIES, language="en")
    return engine


def create_anonymizer() -> Any:
    """Create a Presidio AnonymizerEngine."""
    from presidio_anonymizer import AnonymizerEngine

    return AnonymizerEngine()
