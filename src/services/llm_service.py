"""
Groq LLM service for restaurant recommendations.

Handles communication with the Groq API, including initialization,
request sending, error handling, retries, and response extraction.
Handles edge cases L-01 through L-08.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.config import (
    GROQ_API_KEY,
    LLM_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger(__name__)

# Fallback model if the configured model doesn't exist (edge case L-08)
FALLBACK_MODEL = "mixtral-8x7b-32768"

# Request timeout in seconds (edge case L-04)
REQUEST_TIMEOUT = 30

# Maximum retries
MAX_RETRIES = 1


# ---------------------------------------------------------------------------
# Client Initialization
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """
    Lazy-initialize the Groq client.

    Edge case L-01: Fails with clear error if API key is missing.
    """
    global _client

    if _client is not None:
        return _client

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get your API key at "
            "https://console.groq.com and add it to your .env file."
        )

    try:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized (model: %s)", LLM_MODEL)
        return _client
    except ImportError:
        raise RuntimeError(
            "The 'groq' library is not installed. "
            "Run: pip install groq"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Groq client: {e}") from e


# ---------------------------------------------------------------------------
# API Call
# ---------------------------------------------------------------------------

def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Send a chat completion request to the Groq API.

    Uses JSON response format for structured output. Implements retry logic
    for transient errors and model fallback.

    Args:
        system_prompt: The system message defining the AI's role.
        user_prompt: The user message with preferences and candidates.
        model: Override for the LLM model. Defaults to config value.
        max_tokens: Override for max tokens. Defaults to config value.
        temperature: Override for temperature. Defaults to config value.

    Returns:
        The raw text content of the LLM's response.

    Raises:
        RuntimeError: If the API call fails after all retries.
    """
    client = _get_client()
    model = model or LLM_MODEL
    max_tokens = max_tokens or LLM_MAX_TOKENS
    temperature = temperature if temperature is not None else LLM_TEMPERATURE

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        current_model = model

        try:
            logger.info(
                "Groq API call (attempt %d/%d, model: %s, max_tokens: %d)",
                attempt + 1,
                MAX_RETRIES + 1,
                current_model,
                max_tokens,
            )

            start_time = time.time()

            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=REQUEST_TIMEOUT,
            )

            elapsed = time.time() - start_time
            logger.info("Groq API responded in %.2fs", elapsed)

            # Extract response content
            if not response.choices:
                # Edge case L-05: Empty response
                raise RuntimeError("Groq API returned empty response (no choices)")

            content = response.choices[0].message.content

            if not content or not content.strip():
                # Edge case L-05: Empty content
                raise RuntimeError("Groq API returned empty content")

            # Log usage stats
            if response.usage:
                logger.info(
                    "Token usage: prompt=%d, completion=%d, total=%d",
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    response.usage.total_tokens,
                )

            return content

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Edge case L-08: Model not found — try fallback
            if "model" in error_str and ("not found" in error_str or "does not exist" in error_str):
                if current_model != FALLBACK_MODEL:
                    logger.warning(
                        "Model '%s' not found. Falling back to '%s'.",
                        current_model,
                        FALLBACK_MODEL,
                    )
                    model = FALLBACK_MODEL
                    continue
                else:
                    logger.error("Fallback model '%s' also not found.", FALLBACK_MODEL)
                    break

            # Edge case L-02: Rate limited (429)
            if "rate" in error_str and "limit" in error_str or "429" in error_str:
                if attempt < MAX_RETRIES:
                    # Try to extract retry-after delay
                    wait_time = _extract_retry_after(e)
                    logger.warning(
                        "Rate limited. Waiting %.1fs before retry...",
                        wait_time,
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error("Rate limited after all retries.")
                    break

            # Edge case L-03: Server error (500/503)
            if "500" in error_str or "503" in error_str or "server" in error_str:
                if attempt < MAX_RETRIES:
                    logger.warning("Server error. Retrying in 2s...")
                    time.sleep(2)
                    continue
                else:
                    logger.error("Server error after all retries.")
                    break

            # Edge case L-04: Timeout
            if "timeout" in error_str or "timed out" in error_str:
                if attempt < MAX_RETRIES:
                    logger.warning("Request timed out. Retrying...")
                    continue
                else:
                    logger.error("Timed out after all retries.")
                    break

            # Edge case L-06: Connection error
            if "connection" in error_str or "network" in error_str:
                if attempt < MAX_RETRIES:
                    logger.warning("Connection error. Retrying in 1s...")
                    time.sleep(1)
                    continue
                else:
                    logger.error("Connection error after all retries.")
                    break

            # Unknown error — don't retry
            logger.error("Unexpected Groq API error: %s", e)
            break

    # All retries exhausted
    raise RuntimeError(
        f"Groq API call failed after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


def _extract_retry_after(error: Exception) -> float:
    """
    Try to extract the retry-after delay from a rate limit error.

    Returns a default of 5 seconds if the header is not available.
    """
    # The groq SDK may include retry-after info in the exception
    try:
        if hasattr(error, "response") and hasattr(error.response, "headers"):
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                return float(retry_after)
    except (ValueError, AttributeError):
        pass

    return 5.0  # Default wait time


def check_api_key() -> bool:
    """
    Check if the Groq API key is configured.

    Returns True if the key is set, False otherwise.
    Does NOT validate the key against the API.
    """
    return bool(GROQ_API_KEY)
