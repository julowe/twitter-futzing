"""Core parsing and analysis functions for Twitter archive data.

This module provides the core functionality for parsing Twitter archive files
(.js and .json formats) and analyzing the data. It is designed to be reused
by both the CLI and web application.
"""

import io
import json
import os
import re
import textwrap
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import chardet
import pandas as pd

# Minimum confidence threshold for chardet encoding detection
# Below this threshold, we prefer UTF-8 with error handling
MIN_CHARDET_CONFIDENCE = 0.7

# Encodings that are UTF-8 compatible and don't need special handling
UTF8_COMPATIBLE_ENCODINGS = ("utf-8", "ascii", "utf-8-sig")


def detect_and_decode(data: bytes) -> str:
    """Detect encoding and decode bytes to text.

    Twitter exports are UTF-8 encoded. We try UTF-8 first, then fall back
    to chardet detection if needed. This prevents mojibake from smart quotes
    and other Unicode characters being misinterpreted.

    Args:
        data: Raw bytes to decode.

    Returns:
        Decoded and normalized Unicode string.
    """
    # Twitter exports are UTF-8. Try UTF-8 first.
    try:
        decoded = data.decode("utf-8")
        # Normalize to NFC form (canonical composition) to handle any
        # combining characters consistently
        return unicodedata.normalize("NFC", decoded)
    except UnicodeDecodeError:
        pass

    # If UTF-8 fails, fall back to chardet detection
    try:
        detection = chardet.detect(data) or {}
        encoding = detection.get("encoding") or "utf-8"
        confidence = detection.get("confidence", 0)

        # If chardet has low confidence and suggests non-UTF-8, be cautious
        if confidence < MIN_CHARDET_CONFIDENCE and encoding.lower() not in UTF8_COMPATIBLE_ENCODINGS:
            # Try UTF-8 with error replacement first
            try:
                decoded = data.decode("utf-8", errors="replace")
                return unicodedata.normalize("NFC", decoded)
            except (UnicodeDecodeError, LookupError):
                pass

        # Use chardet's suggestion
        decoded = data.decode(encoding, errors="replace")
        return unicodedata.normalize("NFC", decoded)
    except (UnicodeDecodeError, LookupError, AttributeError):
        # Last resort: UTF-8 with replacement
        # UnicodeDecodeError: bytes cannot be decoded with the specified encoding
        # LookupError: unknown encoding name provided by chardet
        # AttributeError: encoding is None or invalid type
        decoded = data.decode("utf-8", errors="replace")
        return unicodedata.normalize("NFC", decoded)


def strip_js_wrapper(text: str) -> str:
    """Strip JavaScript wrapper from Twitter export files.

    Twitter exports in .js format usually look like:
    window.YTD.tweets.part0 = [ ... ];

    This function extracts the JSON array/object from the first '[' or '{'
    to the matching last ']' or '}'.

    Args:
        text: Raw text content from a .js file.

    Returns:
        JSON string extracted from the file.

    Raises:
        ValueError: If no JSON content can be located.
    """
    # Remove UTF-8 BOM if present
    if text and text[0] == "\ufeff":
        text = text[1:]
    stripped = text.strip()

    # If it already looks like JSON, return as-is
    if stripped.startswith("[") or stripped.startswith("{"):
        return stripped

    # Try to find the first '[' ... last ']'
    lb, rb = stripped.find("["), stripped.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        return stripped[lb : rb + 1]

    # Fallback: try first '{' ... last '}'
    lb, rb = stripped.find("{"), stripped.rfind("}")
    if lb != -1 and rb != -1 and rb > lb:
        return "[" + stripped[lb : rb + 1] + "]"

    raise ValueError(
        "Could not locate JSON content within the .js file. Expected [ ... ] or { ... }."
    )


def parse_twitter_export_bytes(data: bytes, filename: str) -> List[Dict]:
    """Parse a Twitter .js or .json export file into a Python list.

    Each item is usually a dict with a single key like 'tweet', 'noteTweet', etc.

    Args:
        data: Raw bytes content of the file.
        filename: Name of the file (for error reporting).

    Returns:
        List of parsed dictionaries.

    Raises:
        ValueError: If JSON parsing fails.
    """
    text = detect_and_decode(data)
    try:
        core = strip_js_wrapper(text)
        parsed = json.loads(core)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError("Top-level JSON must be an array or object.")
        return parsed
    except json.JSONDecodeError as jde:
        context = textwrap.shorten(text, width=200, placeholder="...")
        raise ValueError(f"JSON parse error in {filename}: {jde}. Sample: {context}")


def parse_twitter_export_file(filepath: str) -> List[Dict]:
    """Parse a Twitter export file from a file path.

    Args:
        filepath: Path to the .js or .json file.

    Returns:
        List of parsed dictionaries.
    """
    with open(filepath, "rb") as f:
        data = f.read()
    return parse_twitter_export_bytes(data, os.path.basename(filepath))


def html_strip(s: Any) -> Any:
    """Strip HTML tags from a string.

    Args:
        s: Input value (string or other type).

    Returns:
        String with HTML tags removed, or original value if not a string.
    """
    if not isinstance(s, str):
        return s
    return re.sub(r"<[^>]+>", "", s)


def safe_get(d: Dict, *keys, default=None) -> Any:
    """Safely get a nested value from a dictionary.

    Args:
        d: Dictionary to traverse.
        *keys: Sequence of keys to follow.
        default: Value to return if key path doesn't exist.

    Returns:
        Value at the key path, or default.
    """
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def normalize_items(raw_items: List[Dict], source_label: str) -> List[Dict]:
    """Flatten Twitter export records into a unified schema.

    Args:
        raw_items: List of raw dictionaries from Twitter export.
        source_label: The filename (for provenance tracking).

    Returns:
        List of normalized record dictionaries.
    """
    rows = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        if "tweet" in it:
            rec = it["tweet"] or {}
            record_type = "deleted_tweet" if "deleted_at" in rec else "tweet"
            text_val = rec.get("full_text") or rec.get("text")
            created = rec.get("created_at")
            row = {
                "record_type": record_type,
                "source_file": source_label,
                "id_str": str(rec.get("id_str") or rec.get("id") or ""),
                "created_at": created,
                "text": text_val,
                "lang": rec.get("lang"),
                "source": html_strip(rec.get("source")),
                "favorite_count": rec.get("favorite_count"),
                "retweet_count": rec.get("retweet_count"),
                "possibly_sensitive": rec.get("possibly_sensitive"),
                "deleted_at": rec.get("deleted_at"),
                "in_reply_to_status_id": rec.get("in_reply_to_status_id")
                or rec.get("in_reply_to_status_id_str"),
                "in_reply_to_user_id": rec.get("in_reply_to_user_id")
                or rec.get("in_reply_to_user_id_str"),
                "in_reply_to_screen_name": rec.get("in_reply_to_screen_name"),
            }
            ents = rec.get("entities") or {}
            row.update(
                {
                    "hashtags_count": len(ents.get("hashtags") or []),
                    "user_mentions_count": len(ents.get("user_mentions") or []),
                    "urls_count": len(ents.get("urls") or []),
                    "media_count": len(ents.get("media") or []),
                }
            )
            rows.append(row)
        elif "noteTweet" in it:
            rec = it["noteTweet"] or {}
            core = rec.get("core") or {}
            row = {
                "record_type": "note",
                "source_file": source_label,
                "id_str": str(rec.get("noteTweetId") or ""),
                "created_at": rec.get("createdAt") or rec.get("updatedAt"),
                "text": core.get("text"),
                "lang": None,
                "source": "Note",
                "favorite_count": None,
                "retweet_count": None,
                "possibly_sensitive": None,
                "deleted_at": None,
                "in_reply_to_status_id": None,
                "in_reply_to_user_id": None,
                "in_reply_to_screen_name": None,
                "hashtags_count": len(core.get("hashtags") or []),
                "user_mentions_count": len(core.get("mentions") or []),
                "urls_count": len(core.get("urls") or []),
                "media_count": 0,
            }
            rows.append(row)
        else:
            # Unknown item type; keep as raw JSON string for debugging
            rows.append(
                {
                    "record_type": "unknown",
                    "source_file": source_label,
                    "id_str": "",
                    "created_at": None,
                    "text": json.dumps(it)[:5000],
                    "lang": None,
                    "source": None,
                    "favorite_count": None,
                    "retweet_count": None,
                    "possibly_sensitive": None,
                    "deleted_at": None,
                    "in_reply_to_status_id": None,
                    "in_reply_to_user_id": None,
                    "in_reply_to_screen_name": None,
                    "hashtags_count": None,
                    "user_mentions_count": None,
                    "urls_count": None,
                    "media_count": None,
                }
            )
    return rows


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce DataFrame columns to appropriate types.

    Args:
        df: DataFrame with raw data.

    Returns:
        DataFrame with properly typed columns.
    """
    # created_at to datetime
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    # counts to numeric
    for col in [
        "favorite_count",
        "retweet_count",
        "hashtags_count",
        "user_mentions_count",
        "urls_count",
        "media_count",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # id_str as string
    if "id_str" in df.columns:
        df["id_str"] = df["id_str"].astype(str)
    # text length
    if "text" in df.columns:
        df["text_len"] = df["text"].fillna("").astype(str).str.len()
    return df


def summarize(df: pd.DataFrame) -> str:
    """Generate a text summary of the DataFrame.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Multi-line summary string.
    """
    lines = []
    lines.append(f"Total records: {len(df):,}")
    if "record_type" in df.columns:
        lines.append("By type:")
        lines.extend(
            [
                "  - " + k + ": " + str(v)
                for k, v in df["record_type"].value_counts().to_dict().items()
            ]
        )
    if "created_at" in df.columns and df["created_at"].notna().any():
        lines.append(
            f'Date range: {df["created_at"].min()} -> {df["created_at"].max()}'
        )
    if "lang" in df.columns:
        top_langs = df["lang"].value_counts(dropna=True).head(5)
        if not top_langs.empty:
            lines.append(
                "Top languages: "
                + ", ".join([f"{idx} ({val})" for idx, val in top_langs.items()])
            )
    if "source" in df.columns:
        top_src = df["source"].value_counts(dropna=True).head(5)
        if not top_src.empty:
            lines.append(
                "Top sources: "
                + ", ".join([f"{idx} ({val})" for idx, val in top_src.items()])
            )
    if "text_len" in df.columns and df["text_len"].notna().any():
        lines.append(
            f"Text length (chars): mean {df['text_len'].mean():.1f}, median {df['text_len'].median():.0f}"
        )
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        lines.append(
            f"Favorites: mean {df['favorite_count'].mean():.2f}, max {df['favorite_count'].max()}"
        )
    if "retweet_count" in df.columns and df["retweet_count"].notna().any():
        lines.append(
            f"Retweets: mean {df['retweet_count'].mean():.2f}, max {df['retweet_count'].max()}"
        )
    return "\n".join(lines)


def process_files(
    files: List[Tuple[str, bytes]], progress_callback: Optional[callable] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """Process multiple Twitter export files.

    Args:
        files: List of (filename, bytes) tuples.
        progress_callback: Optional callback function(current, total, message) for progress updates.

    Returns:
        Tuple of (DataFrame with all records, list of error messages).
    """
    all_rows = []
    errors = []
    total = len(files)

    for idx, (filename, data) in enumerate(files):
        if progress_callback:
            progress_callback(idx, total, f"Processing {filename}...")
        try:
            items = parse_twitter_export_bytes(data, filename)
            rows = normalize_items(items, source_label=filename)
            all_rows.extend(rows)
        except Exception as e:
            errors.append(f"{filename}: {e}")

    if progress_callback:
        progress_callback(total, total, "Processing complete")

    if not all_rows:
        return pd.DataFrame(), errors

    df = pd.DataFrame(all_rows)
    df = coerce_types(df)
    return df, errors
