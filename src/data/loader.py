"""
Dataset loader for the Zomato restaurant dataset.

Fetches the dataset from Hugging Face, converts it to a pandas DataFrame,
and implements local caching to avoid redundant API calls. Handles edge
cases D-01 through D-07 from edge-cases.md.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import HF_DATASET_ID, DATA_CACHE_DIR

logger = logging.getLogger(__name__)

# Cache filename derived from dataset ID
_CACHE_FILENAME = f"zomato_dataset_{hashlib.md5(HF_DATASET_ID.encode()).hexdigest()[:8]}.parquet"


def _get_cache_path() -> Path:
    """Get the full path to the cached dataset file."""
    return DATA_CACHE_DIR / _CACHE_FILENAME


def _load_from_cache() -> Optional[pd.DataFrame]:
    """
    Attempt to load the dataset from the local parquet cache.

    Returns:
        DataFrame if cache exists and is valid, None otherwise.
    """
    cache_path = _get_cache_path()

    if not cache_path.exists():
        logger.info("No cached dataset found at %s", cache_path)
        return None

    try:
        df = pd.read_parquet(cache_path)

        # Edge case D-04: Validate cache integrity (non-empty)
        if df.empty:
            logger.warning("Cached dataset is empty. Will re-download.")
            cache_path.unlink(missing_ok=True)
            return None

        logger.info(
            "Loaded dataset from cache: %s (%d rows)",
            cache_path,
            len(df),
        )
        return df

    except Exception as e:
        # Edge case D-04: Corrupted cache file
        logger.warning("Cache file corrupted (%s). Will re-download.", e)
        cache_path.unlink(missing_ok=True)
        return None


def _save_to_cache(df: pd.DataFrame) -> None:
    """
    Save the dataset to local parquet cache.

    Handles edge case C-11 (disk full) by catching IOError.
    """
    cache_path = _get_cache_path()

    try:
        # Edge case C-10: Create cache directory if it doesn't exist
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info("Dataset cached to %s", cache_path)

    except (IOError, OSError) as e:
        # Edge case C-11: Disk full or permission error
        logger.warning("Failed to cache dataset (%s). Proceeding without cache.", e)


def _download_from_huggingface() -> pd.DataFrame:
    """
    Download the dataset from Hugging Face and convert to DataFrame.

    Handles edge cases:
      D-01: HF API down → raises with clear message
      D-02: Dataset deleted → raises with dataset ID
      D-03: Network timeout → caught and re-raised
      D-05: Schema changes → validated after load
    """
    try:
        from datasets import load_dataset

        logger.info("Downloading dataset from Hugging Face (Streaming): %s", HF_DATASET_ID)
        # Use streaming=True to prevent massive memory usage during Arrow file generation
        dataset = load_dataset(HF_DATASET_ID, streaming=True)

        if isinstance(dataset, dict) or hasattr(dataset, "keys"):
            split_name = "train" if "train" in dataset else list(dataset.keys())[0]
            iterable_ds = dataset[split_name]
        else:
            iterable_ds = dataset

        logger.info("Iterating streaming dataset to build dataframe...")
        rows = []
        for i, row in enumerate(iterable_ds):
            # Immediately drop heavy columns to keep memory footprint tiny
            row.pop("reviews_list", None)
            row.pop("menu_item", None)
            row.pop("url", None)
            row.pop("phone", None)
            rows.append(row)
            
            if i > 0 and i % 10000 == 0:
                logger.info("Processed %d rows...", i)

        df = pd.DataFrame(rows)
        logger.info("Loaded streaming dataset with %d rows", len(df))

        return df

    except ImportError:
        raise RuntimeError(
            "The 'datasets' library is not installed. "
            "Run: pip install datasets"
        )
    except Exception as e:
        error_msg = str(e).lower()

        # Edge case D-02: Dataset not found
        if "not found" in error_msg or "404" in error_msg:
            raise RuntimeError(
                f"Dataset '{HF_DATASET_ID}' not found on Hugging Face. "
                f"Verify the dataset ID in your .env file (HF_DATASET_ID)."
            ) from e

        # Edge case D-01/D-03: Network issues
        if "connection" in error_msg or "timeout" in error_msg:
            raise RuntimeError(
                f"Failed to connect to Hugging Face API: {e}. "
                f"Check your internet connection or try again later."
            ) from e

        raise RuntimeError(
            f"Failed to load dataset '{HF_DATASET_ID}': {e}"
        ) from e


# Expected columns for schema validation (edge case D-05)
EXPECTED_COLUMNS = {"name"}  # Minimum required columns


def _validate_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate that the DataFrame has the expected columns.

    Edge case D-05: Detect schema changes early with clear error messages.
    """
    actual_columns = set(df.columns.str.lower())

    missing = EXPECTED_COLUMNS - actual_columns
    if missing:
        logger.warning(
            "Dataset is missing expected columns: %s. Available columns: %s",
            missing,
            list(df.columns),
        )

    # Log available columns for debugging
    logger.info("Dataset columns: %s", list(df.columns))

    return df


def load_data() -> pd.DataFrame:
    """
    Load the Zomato restaurant dataset.

    Tries local cache first, falls back to Hugging Face download.
    Validates schema and checks for empty dataset.

    Returns:
        pd.DataFrame: The raw (unprocessed) restaurant dataset.

    Raises:
        RuntimeError: If the dataset cannot be loaded from any source.
    """
    # Try cache first
    df = _load_from_cache()

    if df is None:
        # Download from Hugging Face
        try:
            df = _download_from_huggingface()
        except RuntimeError:
            # Edge case D-01: If download fails, check cache one more time
            cache_path = _get_cache_path()
            if cache_path.exists():
                logger.warning(
                    "Download failed. Attempting to use potentially stale cache."
                )
                df = pd.read_parquet(cache_path)
            else:
                raise

        # Cache the downloaded data
        _save_to_cache(df)

    # Edge case D-06: Empty dataset
    if df.empty:
        raise RuntimeError(
            "Dataset is empty (0 rows). Cannot start the application. "
            "Verify the dataset at: "
            f"https://huggingface.co/datasets/{HF_DATASET_ID}"
        )

    # Validate schema
    df = _validate_schema(df)

    logger.info(
        "Dataset loaded successfully: %d rows × %d columns",
        len(df),
        len(df.columns),
    )

    return df
