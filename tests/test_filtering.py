#!/usr/bin/env python3
"""Tests for filtering functionality."""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from twitter_analyzer.core import filter_dataframe, process_files


def create_test_dataframe():
    """Create a test DataFrame with sample data."""
    data = [
        {
            "record_type": "tweet",
            "id_str": "1",
            "created_at": pd.Timestamp("2023-01-15 10:00:00", tz="UTC"),
            "text": "The blue green water is beautiful",
        },
        {
            "record_type": "tweet",
            "id_str": "2",
            "created_at": pd.Timestamp("2023-02-20 15:30:00", tz="UTC"),
            "text": "The red sky at night",
        },
        {
            "record_type": "tweet",
            "id_str": "3",
            "created_at": pd.Timestamp("2023-03-10 08:45:00", tz="UTC"),
            "text": "The purple blue tree is lovely",
        },
        {
            "record_type": "tweet",
            "id_str": "4",
            "created_at": pd.Timestamp("2023-04-05 12:00:00", tz="UTC"),
            "text": "The blue sky is clear today",
        },
        {
            "record_type": "tweet",
            "id_str": "5",
            "created_at": pd.Timestamp("2023-05-01 09:15:00", tz="UTC"),
            "text": "The earth rotates around the sun",
        },
        {
            "record_type": "tweet",
            "id_str": "6",
            "created_at": pd.Timestamp("2023-06-15 14:20:00", tz="UTC"),
            "text": "Green grass and blue skies",
        },
    ]
    return pd.DataFrame(data)


def test_filter_text_and():
    """Test AND filtering with multiple words."""
    df = create_test_dataframe()
    
    # Filter for tweets containing both "blue" AND "green"
    filtered = filter_dataframe(df, filter_and=["blue", "green"])
    
    # Should match:
    # - "The blue green water is beautiful" (id 1)
    # - "Green grass and blue skies" (id 6)
    assert len(filtered) == 2, f"Expected 2 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"1", "6"}, f"Unexpected tweets: {set(filtered['id_str'])}"
    
    print("✓ test_filter_text_and passed")


def test_filter_text_or():
    """Test OR filtering with multiple words."""
    df = create_test_dataframe()
    
    # Filter for tweets containing "red" OR "purple blue"
    filtered = filter_dataframe(df, filter_or=["red", "purple blue"])
    
    # Should match:
    # - "The red sky at night" (id 2)
    # - "The purple blue tree is lovely" (id 3)
    assert len(filtered) == 2, f"Expected 2 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"2", "3"}, f"Unexpected tweets: {set(filtered['id_str'])}"
    
    print("✓ test_filter_text_or passed")


def test_filter_text_and_or():
    """Test combined AND and OR filtering."""
    df = create_test_dataframe()
    
    # Filter for tweets containing both "blue" AND "green", OR "red", OR "purple blue"
    # This matches the example from the issue
    filtered = filter_dataframe(
        df,
        filter_and=["blue", "green"],
        filter_or=["red", "purple blue"]
    )
    
    # Should match:
    # - "The blue green water is beautiful" (has blue AND green) (id 1)
    # - "The red sky at night" (has red) (id 2)
    # - "The purple blue tree is lovely" (has purple blue) (id 3)
    # - "Green grass and blue skies" (has blue AND green) (id 6)
    # Should NOT match:
    # - "The blue sky is clear today" (has blue but not green, and no OR words) (id 4)
    # - "The earth rotates around the sun" (no filter words) (id 5)
    assert len(filtered) == 4, f"Expected 4 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"1", "2", "3", "6"}, f"Unexpected tweets: {set(filtered['id_str'])}"
    
    print("✓ test_filter_text_and_or passed")


def test_filter_text_case_insensitive():
    """Test that text filtering is case-insensitive."""
    df = create_test_dataframe()
    
    # Filter with different cases
    filtered1 = filter_dataframe(df, filter_and=["BLUE", "GREEN"])
    filtered2 = filter_dataframe(df, filter_and=["blue", "green"])
    filtered3 = filter_dataframe(df, filter_and=["Blue", "Green"])
    
    # All should produce the same result
    assert len(filtered1) == len(filtered2) == len(filtered3)
    assert set(filtered1["id_str"]) == set(filtered2["id_str"]) == set(filtered3["id_str"])
    
    print("✓ test_filter_text_case_insensitive passed")


def test_filter_datetime_after():
    """Test datetime filtering with after constraint."""
    df = create_test_dataframe()
    
    # Filter for tweets after March 1, 2023
    after_date = datetime(2023, 3, 1, tzinfo=timezone.utc)
    filtered = filter_dataframe(df, datetime_after=after_date)
    
    # Should match tweets with id 3, 4, 5, 6 (March onwards)
    assert len(filtered) == 4, f"Expected 4 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"3", "4", "5", "6"}
    
    print("✓ test_filter_datetime_after passed")


def test_filter_datetime_before():
    """Test datetime filtering with before constraint."""
    df = create_test_dataframe()
    
    # Filter for tweets before April 1, 2023
    before_date = datetime(2023, 4, 1, tzinfo=timezone.utc)
    filtered = filter_dataframe(df, datetime_before=before_date)
    
    # Should match tweets with id 1, 2, 3 (before April)
    assert len(filtered) == 3, f"Expected 3 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"1", "2", "3"}
    
    print("✓ test_filter_datetime_before passed")


def test_filter_datetime_range():
    """Test datetime filtering with both after and before constraints."""
    df = create_test_dataframe()
    
    # Filter for tweets in February-April 2023
    after_date = datetime(2023, 2, 1, tzinfo=timezone.utc)
    before_date = datetime(2023, 4, 30, tzinfo=timezone.utc)
    filtered = filter_dataframe(
        df,
        datetime_after=after_date,
        datetime_before=before_date
    )
    
    # Should match tweets with id 2, 3, 4
    assert len(filtered) == 3, f"Expected 3 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"2", "3", "4"}
    
    print("✓ test_filter_datetime_range passed")


def test_filter_combined():
    """Test combined text and datetime filtering."""
    df = create_test_dataframe()
    
    # Filter for tweets with "blue" after March 1, 2023
    after_date = datetime(2023, 3, 1, tzinfo=timezone.utc)
    filtered = filter_dataframe(
        df,
        filter_or=["blue"],
        datetime_after=after_date
    )
    
    # Should match:
    # - "The purple blue tree is lovely" (id 3)
    # - "The blue sky is clear today" (id 4)
    # - "Green grass and blue skies" (id 6)
    assert len(filtered) == 3, f"Expected 3 tweets, got {len(filtered)}"
    assert set(filtered["id_str"]) == {"3", "4", "6"}
    
    print("✓ test_filter_combined passed")


def test_filter_empty_dataframe():
    """Test filtering on an empty DataFrame."""
    df = pd.DataFrame()
    
    # Should return empty DataFrame without errors
    filtered = filter_dataframe(
        df,
        filter_and=["test"],
        datetime_after=datetime(2023, 1, 1, tzinfo=timezone.utc)
    )
    
    assert filtered.empty, "Filtered empty DataFrame should be empty"
    
    print("✓ test_filter_empty_dataframe passed")


def test_filter_no_matches():
    """Test filtering that results in no matches."""
    df = create_test_dataframe()
    
    # Filter for impossible combination
    filtered = filter_dataframe(df, filter_and=["nonexistent", "word"])
    
    assert len(filtered) == 0, f"Expected 0 tweets, got {len(filtered)}"
    
    print("✓ test_filter_no_matches passed")


def test_filter_with_real_data():
    """Test filtering with real mock data from test files."""
    test_dir = Path(__file__).parent
    test_file = test_dir / "mock_tweets.js"
    
    # Load test data
    with open(test_file, "rb") as f:
        files = [("mock_tweets.js", f.read())]
    
    df, _ = process_files(files)
    assert not df.empty, "Should have loaded test data"
    
    original_count = len(df)
    
    # Apply various filters
    # Test datetime filter
    after_date = datetime(2023, 7, 1, tzinfo=timezone.utc)
    filtered = filter_dataframe(df, datetime_after=after_date)
    assert len(filtered) <= original_count, "Filtered count should be <= original"
    
    # Test text filter (AI is in the mock data)
    filtered = filter_dataframe(df, filter_or=["AI"])
    assert len(filtered) > 0, "Should find tweets with 'AI'"
    
    print(f"✓ test_filter_with_real_data passed - tested {original_count} real tweets")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Filtering Tests")
    print("=" * 70)
    
    tests = [
        test_filter_text_and,
        test_filter_text_or,
        test_filter_text_and_or,
        test_filter_text_case_insensitive,
        test_filter_datetime_after,
        test_filter_datetime_before,
        test_filter_datetime_range,
        test_filter_combined,
        test_filter_empty_dataframe,
        test_filter_no_matches,
        test_filter_with_real_data,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed.append(test.__name__)
    
    print("=" * 70)
    if failed:
        print(f"FAILED: {len(failed)} test(s) failed:")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print(f"SUCCESS: All {len(tests)} tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
