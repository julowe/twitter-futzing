#!/usr/bin/env python3
"""Tests for webapp filtering functionality."""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from webapp import app, save_session_data, delete_session_data


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_session_data():
    """Create mock session data with a test DataFrame."""
    import pandas as pd
    from datetime import datetime, timezone
    
    data = [
        {
            "record_type": "tweet",
            "id_str": "1",
            "created_at": pd.Timestamp("2023-01-15 10:00:00", tz="UTC"),
            "text": "The blue green water is beautiful",
            "favorite_count": 100,
            "retweet_count": 10,
        },
        {
            "record_type": "tweet",
            "id_str": "2",
            "created_at": pd.Timestamp("2023-02-20 15:30:00", tz="UTC"),
            "text": "The red sky at night",
            "favorite_count": 50,
            "retweet_count": 5,
        },
        {
            "record_type": "tweet",
            "id_str": "3",
            "created_at": pd.Timestamp("2023-03-10 08:45:00", tz="UTC"),
            "text": "The purple blue tree is lovely",
            "favorite_count": 75,
            "retweet_count": 8,
        },
    ]
    df = pd.DataFrame(data)
    
    # Use a valid session ID format (32 hex chars)
    session_id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    save_session_data(session_id, {"df": df, "timestamp": datetime.now().isoformat()})
    
    yield session_id
    
    # Cleanup
    delete_session_data(session_id)


def test_api_filter_data_no_filters(client, mock_session_data):
    """Test /api/filter-data endpoint with no filters."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/filter-data')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'stats' in data
    assert 'summary' in data
    assert 'charts_html' in data
    assert 'top_tweets' in data
    assert 'preview_data' in data
    
    # Should return all 3 records
    assert data['stats']['total_records'] == 3
    assert data['stats']['unfiltered_total'] == 3


def test_api_filter_data_with_or_filter(client, mock_session_data):
    """Test /api/filter-data endpoint with OR text filter."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/filter-data?filter_or=red,purple')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Should return 2 records (tweets with "red" or "purple")
    assert data['stats']['total_records'] == 2
    assert data['stats']['unfiltered_total'] == 3
    assert len(data['top_tweets']) == 2


def test_api_filter_data_with_and_filter(client, mock_session_data):
    """Test /api/filter-data endpoint with AND text filter."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/filter-data?filter_and=blue,green')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Should return 1 record (tweet with both "blue" AND "green")
    assert data['stats']['total_records'] == 1
    assert data['stats']['unfiltered_total'] == 3
    assert len(data['top_tweets']) == 1


def test_api_filter_data_with_datetime_filter(client, mock_session_data):
    """Test /api/filter-data endpoint with datetime filter."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/filter-data?datetime_after=2023-02-01T00:00')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Should return 2 records (tweets after Feb 1)
    assert data['stats']['total_records'] == 2
    assert data['stats']['unfiltered_total'] == 3


def test_api_filter_data_charts_included(client, mock_session_data):
    """Test that charts HTML is included in the response."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/filter-data')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Charts HTML should be present (may be empty if no charts can be generated)
    assert 'charts_html' in data
    assert isinstance(data['charts_html'], str)


def test_api_top_tweets_with_filter(client, mock_session_data):
    """Test /api/top-tweets endpoint with filter."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/top-tweets?filter_or=red')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Should return 1 tweet with "red"
    assert len(data['tweets']) == 1
    assert 'red' in data['tweets'][0]['text'].lower()


def test_api_data_preview_with_filter(client, mock_session_data):
    """Test /api/data-preview endpoint with filter."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    response = client.get('/api/data-preview?filter_and=blue')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Should return 2 records with "blue"
    assert len(data['records']) == 2
    assert data['total'] == 2


def test_filter_data_session_expired(client):
    """Test /api/filter-data with no session."""
    response = client.get('/api/filter-data')
    assert response.status_code == 404
    
    data = json.loads(response.data)
    assert 'error' in data


def test_filter_data_invalid_datetime_format(client, mock_session_data):
    """Test /api/filter-data with invalid datetime format (handled gracefully)."""
    with client.session_transaction() as sess:
        sess['data_id'] = mock_session_data
    
    # Invalid datetime format should be handled gracefully
    # The parse_filter_params function will skip invalid dates
    response = client.get('/api/filter-data?datetime_after=invalid-date')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    # Should return all records since invalid date is ignored
    assert data['stats']['total_records'] == 3


def main():
    """Run all tests using pytest."""
    # Run pytest with verbose output
    exit_code = pytest.main([__file__, '-v'])
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
