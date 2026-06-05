"""Tests for the Gemini procedure extractor and rate limiter."""
import os
import time
import pytest
from unittest.mock import MagicMock, patch
from app.modules.extraction.gemini_extractor import GeminiRouteExtractor, RateLimiter


def _clear_auth_env(monkeypatch):
    """Force the API-key branch with no creds present."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)


def _mock_genai_client(response_text):
    """Build a fake google-genai client whose generate_content returns text."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def test_gemini_extractor_lazy_init(monkeypatch):
    """Test that extractor fails appropriately if no credentials are configured."""
    _clear_auth_env(monkeypatch)
    extractor = GeminiRouteExtractor()
    with pytest.raises(RuntimeError, match="No Gemini credentials found"):
        extractor.parse("test")


def test_gemini_extractor_parse_success(monkeypatch):
    """Test that extractor parses successful JSON responses with the configured model."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-test")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")

    extractor = GeminiRouteExtractor()
    mock_client = _mock_genai_client(
        '{"steps": [{"step_id": 1, "name": "Step 1", "reagents": []}], "warnings": []}'
    )

    with patch("google.genai.Client", return_value=mock_client) as mock_ctor:
        res = extractor.parse("To a solution, add aniline (5 g)")

        mock_ctor.assert_called_once_with(api_key="dummy-key-for-test")
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"

        assert res["extractor"] == "gemini-3-flash-preview"
        assert len(res["steps"]) == 1
        assert res["steps"][0]["step_id"] == 1
        assert res["steps"][0]["name"] == "Step 1"


def test_gemini_extractor_vertex_mode(monkeypatch):
    """Test that Vertex mode builds the client from gcloud env, with no API key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")

    extractor = GeminiRouteExtractor(model_name="gemini-2.5-flash")
    mock_client = _mock_genai_client(
        '{"steps": [{"step_id": 1, "name": "Step 1", "reagents": []}], "warnings": []}'
    )

    with patch("google.genai.Client", return_value=mock_client) as mock_ctor:
        res = extractor.parse("To a solution, add aniline (5 g)")

        mock_ctor.assert_called_once_with(
            vertexai=True, project="my-proj", location="europe-west4"
        )
        assert extractor.auth_mode == "vertex"
        assert res["extractor"] == "gemini-2.5-flash"


def test_gemini_extractor_fallback_on_failure(monkeypatch):
    """Test that if the Gemini API fails, it falls back to the mock/heuristic extractor."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-test")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    extractor = GeminiRouteExtractor()

    mock_client = _mock_genai_client("")
    mock_client.models.generate_content.side_effect = Exception("API Quota Exceeded")

    with patch("google.genai.Client", return_value=mock_client):
        # The input contains "aniline (5.0 g)" which the heuristic parser can extract
        res = extractor.parse(
            "To a solution of aniline (5.0 g, 54 mmol, 1.0 equiv) in THF was added acetic anhydride."
        )
        assert "heuristic-fallback" in res["extractor"]
        assert len(res["steps"]) == 1
        assert res["steps"][0]["reagents"][0]["name"] == "aniline"
        assert res["steps"][0]["reagents"][0]["mass"] == 5.0


def test_rate_limiter():
    """Test that the sliding-window rate limiter delays calls when threshold is crossed."""
    # Create a fast rate limiter: 2 calls max in a 0.2 second window
    limiter = RateLimiter(max_calls=2, period_seconds=0.2)

    start = time.monotonic()
    limiter.wait()  # Call 1 (allowed immediately)
    limiter.wait()  # Call 2 (allowed immediately)

    limiter.wait()  # Call 3 (must wait for first timestamp to clear)
    duration = time.monotonic() - start

    # The duration should be at least 0.2s (the window period)
    assert duration >= 0.15


def test_gemini_extractor_coerces_null_is_limiting(monkeypatch):
    """Test that if the model returns null for is_limiting, it is coerced to False."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-test")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    extractor = GeminiRouteExtractor()

    mock_client = _mock_genai_client(
        '{"steps": [{"step_id": 1, "name": "Step 1", "reagents": [{"name": "aniline", "is_limiting": null}]}], "warnings": []}'
    )

    with patch("google.genai.Client", return_value=mock_client):
        res = extractor.parse("To a solution, add aniline")
        assert res["steps"][0]["reagents"][0]["is_limiting"] is False
