#!/usr/bin/env python3
"""Tests for Twitter Archive Analyzer core functionality.

This test suite validates:
- File parsing (.js and .json formats)
- Date parsing with different Python versions
- Data normalization and type coercion
- Mock data processing
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from twitter_analyzer.core import (
    parse_twitter_export_file,
    parse_twitter_export_bytes,
    normalize_items,
    coerce_types,
    summarize,
    process_files,
)


def test_parse_js_file():
    """Test parsing .js files with JavaScript wrapper."""
    test_file = Path(__file__).parent / "mock_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    
    assert isinstance(items, list), "Should return a list"
    assert len(items) > 0, "Should parse at least one item"
    assert "tweet" in items[0], "First item should contain 'tweet' key"
    
    print(f"✓ Parsed {len(items)} items from mock_tweets.js")


def test_parse_json_file():
    """Test parsing .json files without JavaScript wrapper."""
    test_file = Path(__file__).parent / "mock_tweets.json"
    items = parse_twitter_export_file(str(test_file))
    
    assert isinstance(items, list), "Should return a list"
    assert len(items) > 0, "Should parse at least one item"
    assert "tweet" in items[0], "First item should contain 'tweet' key"
    
    print(f"✓ Parsed {len(items)} items from mock_tweets.json")


def test_parse_deleted_tweets():
    """Test parsing deleted tweets file."""
    test_file = Path(__file__).parent / "mock_deleted_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    
    assert isinstance(items, list), "Should return a list"
    assert len(items) > 0, "Should parse at least one item"
    
    # Check for deleted_at field
    first_tweet = items[0].get("tweet", {})
    assert "deleted_at" in first_tweet, "Deleted tweet should have 'deleted_at' field"
    
    print(f"✓ Parsed {len(items)} deleted tweets from mock_deleted_tweets.js")


def test_parse_note_tweets():
    """Test parsing Twitter Notes."""
    test_file = Path(__file__).parent / "mock_note_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    
    assert isinstance(items, list), "Should return a list"
    assert len(items) > 0, "Should parse at least one item"
    assert "noteTweet" in items[0], "First item should contain 'noteTweet' key"
    
    print(f"✓ Parsed {len(items)} notes from mock_note_tweets.js")


def test_normalize_items():
    """Test normalizing Twitter export items to unified schema."""
    test_file = Path(__file__).parent / "mock_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    
    rows = normalize_items(items, source_label="mock_tweets.js")
    
    assert isinstance(rows, list), "Should return a list"
    assert len(rows) > 0, "Should normalize at least one row"
    
    # Check required fields
    first_row = rows[0]
    required_fields = ["record_type", "source_file", "id_str", "created_at", "text"]
    for field in required_fields:
        assert field in first_row, f"Normalized row should have '{field}' field"
    
    print(f"✓ Normalized {len(rows)} rows with all required fields")


def test_coerce_types():
    """Test type coercion with date parsing."""
    test_file = Path(__file__).parent / "mock_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    rows = normalize_items(items, source_label="mock_tweets.js")
    
    df = pd.DataFrame(rows)
    df_typed = coerce_types(df)
    
    # Check datetime conversion
    assert pd.api.types.is_datetime64_any_dtype(df_typed["created_at"]), \
        "created_at should be datetime type"
    
    # Check that dates were parsed correctly (no NaT values for valid data)
    valid_dates = df_typed["created_at"].notna().sum()
    assert valid_dates > 0, "Should have at least one valid parsed date"
    
    # Check numeric conversions
    assert pd.api.types.is_numeric_dtype(df_typed["favorite_count"]), \
        "favorite_count should be numeric"
    assert pd.api.types.is_numeric_dtype(df_typed["retweet_count"]), \
        "retweet_count should be numeric"
    
    # Check text_len was added
    assert "text_len" in df_typed.columns, "Should add text_len column"
    
    print(f"✓ Type coercion successful: {valid_dates}/{len(df_typed)} dates parsed")
    print(f"  - Date range: {df_typed['created_at'].min()} to {df_typed['created_at'].max()}")


def test_process_multiple_files():
    """Test processing multiple files at once."""
    test_dir = Path(__file__).parent
    
    files = [
        (test_dir / "mock_tweets.js", "mock_tweets.js"),
        (test_dir / "mock_deleted_tweets.js", "mock_deleted_tweets.js"),
        (test_dir / "mock_note_tweets.js", "mock_note_tweets.js"),
        (test_dir / "mock_tweets.json", "mock_tweets.json"),
    ]
    
    file_data = []
    for filepath, name in files:
        with open(filepath, "rb") as f:
            file_data.append((name, f.read()))
    
    df, errors = process_files(file_data)
    
    assert isinstance(df, pd.DataFrame), "Should return a DataFrame"
    assert not df.empty, "DataFrame should not be empty"
    assert len(errors) == 0, f"Should have no errors, but got: {errors}"
    
    # Check that we have different record types
    if "record_type" in df.columns:
        record_types = df["record_type"].unique()
        assert "tweet" in record_types, "Should have tweet records"
        print(f"✓ Processed {len(df)} records from {len(file_data)} files")
        print(f"  - Record types: {', '.join(record_types)}")
    
    # Verify dates were parsed without warnings
    if "created_at" in df.columns:
        valid_dates = df["created_at"].notna().sum()
        print(f"  - Valid dates: {valid_dates}/{len(df)}")


def test_summarize():
    """Test summary generation."""
    test_file = Path(__file__).parent / "mock_tweets.js"
    items = parse_twitter_export_file(str(test_file))
    rows = normalize_items(items, source_label="mock_tweets.js")
    
    df = pd.DataFrame(rows)
    df = coerce_types(df)
    
    summary = summarize(df)
    
    assert isinstance(summary, str), "Should return a string"
    assert len(summary) > 0, "Summary should not be empty"
    assert "Total records:" in summary, "Should include total records"
    
    print(f"✓ Generated summary:\n{summary}\n")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Twitter Archive Analyzer - Test Suite")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print(f"Pandas version: {pd.__version__}")
    print("=" * 70)
    print()
    
    tests = [
        test_parse_js_file,
        test_parse_json_file,
        test_parse_deleted_tweets,
        test_parse_note_tweets,
        test_normalize_items,
        test_coerce_types,
        test_process_multiple_files,
        test_summarize,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n{test.__name__}:")
            print("-" * 70)
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
