"""
Configuration management for the Nextleap Zomato application.

Loads environment variables from a .env file and provides typed access
to all configuration values with sensible defaults.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env file from project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    print(f"[WARNING] No .env file found at {ENV_PATH}")
    print(f"[WARNING] Copy .env.example to .env and configure your settings.")
    print(f"[WARNING] Using defaults and environment variables only.\n")


# ---------------------------------------------------------------------------
# LLM Configuration (Groq)
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# Clamp temperature to valid range (edge case C-08)
LLM_TEMPERATURE = max(0.0, min(2.0, LLM_TEMPERATURE))

# ---------------------------------------------------------------------------
# Dataset Configuration
# ---------------------------------------------------------------------------
HF_DATASET_ID: str = os.getenv(
    "HF_DATASET_ID", "ManikaSaini/zomato-restaurant-recommendation"
)
DATA_CACHE_DIR: Path = Path(
    os.getenv("DATA_CACHE_DIR", str(PROJECT_ROOT / "data" / "cache"))
)

# ---------------------------------------------------------------------------
# Filtering Configuration
# ---------------------------------------------------------------------------
MAX_CANDIDATES: int = int(os.getenv("MAX_CANDIDATES", "20"))
BUDGET_LOW_MAX: int = int(os.getenv("BUDGET_LOW_MAX", "500"))
BUDGET_MEDIUM_MAX: int = int(os.getenv("BUDGET_MEDIUM_MAX", "1500"))

# Clamp MAX_CANDIDATES to reasonable range (edge case C-06, C-07)
MAX_CANDIDATES = max(1, min(50, MAX_CANDIDATES))

# Validate budget thresholds (edge case C-04, C-05)
if BUDGET_LOW_MAX >= BUDGET_MEDIUM_MAX:
    print(
        f"[WARNING] BUDGET_LOW_MAX ({BUDGET_LOW_MAX}) >= BUDGET_MEDIUM_MAX "
        f"({BUDGET_MEDIUM_MAX}). Swapping values."
    )
    BUDGET_LOW_MAX, BUDGET_MEDIUM_MAX = (
        min(BUDGET_LOW_MAX, BUDGET_MEDIUM_MAX),
        max(BUDGET_LOW_MAX, BUDGET_MEDIUM_MAX),
    )
    # If they're equal, offset by 1
    if BUDGET_LOW_MAX == BUDGET_MEDIUM_MAX:
        BUDGET_MEDIUM_MAX = BUDGET_LOW_MAX + 500

# Budget tier ranges (inclusive boundaries — edge case F-08)
BUDGET_TIERS: dict[str, tuple[int, int]] = {
    "low": (0, BUDGET_LOW_MAX),
    "medium": (BUDGET_LOW_MAX + 1, BUDGET_MEDIUM_MAX),
    "high": (BUDGET_MEDIUM_MAX + 1, 999999),
}

# ---------------------------------------------------------------------------
# Server Configuration
# ---------------------------------------------------------------------------
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------
def validate_config() -> bool:
    """
    Validate critical configuration values at startup.
    Returns True if config is valid, prints errors and returns False otherwise.
    """
    errors: list[str] = []

    if not GROQ_API_KEY:
        errors.append(
            "GROQ_API_KEY is not set. Get your key at https://console.groq.com"
        )

    if not HF_DATASET_ID:
        errors.append("HF_DATASET_ID is not set.")

    if errors:
        print("\n[CONFIG ERROR] The following configuration issues were found:")
        for err in errors:
            print(f"  ✗ {err}")
        print()
        return False

    return True


def print_config_summary() -> None:
    """Print a summary of the current configuration (masking sensitive values)."""
    masked_key = (
        f"{GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:]}"
        if len(GROQ_API_KEY) > 12
        else "***"
    )
    print("=" * 60)
    print("  Nextleap Zomato — Configuration Summary")
    print("=" * 60)
    print(f"  LLM Provider:     {LLM_PROVIDER}")
    print(f"  Groq API Key:     {masked_key}")
    print(f"  LLM Model:        {LLM_MODEL}")
    print(f"  Temperature:      {LLM_TEMPERATURE}")
    print(f"  Max Tokens:       {LLM_MAX_TOKENS}")
    print(f"  Dataset ID:       {HF_DATASET_ID}")
    print(f"  Cache Dir:        {DATA_CACHE_DIR}")
    print(f"  Max Candidates:   {MAX_CANDIDATES}")
    print(f"  Budget Tiers:     Low <=Rs.{BUDGET_LOW_MAX} | "
          f"Medium <=Rs.{BUDGET_MEDIUM_MAX} | High >Rs.{BUDGET_MEDIUM_MAX}")
    print(f"  Server:           {HOST}:{PORT} (debug={DEBUG})")
    print("=" * 60)
