"""Tests for visualization functions."""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from twitter_analyzer.visualizations import (
    create_weekly_avg_sentiment_chart,
    create_all_tweets_sentiment_chart,
    generate_all_charts,
)


def create_test_dataframe(num_records=100, start_date='2023-01-01'):
    """Create a test DataFrame with sentiment data."""
    dates = pd.date_range(start=start_date, periods=num_records, freq='D')
    df = pd.DataFrame({
        'created_at': dates,
        'sentiment_polarity': [0.1 * (i % 10 - 5) / 5 for i in range(num_records)],
        'sentiment_subjectivity': [0.5 + 0.1 * (i % 5) / 5 for i in range(num_records)],
        'sentiment_category': ['Neutral'] * num_records,
        'text': [f'Tweet {i}' for i in range(num_records)],
        'text_len': [10] * num_records,
        'record_type': ['tweet'] * num_records,
        'lang': ['en'] * num_records,
        'source': ['Twitter Web App'] * num_records,
    })
    return df


def test_create_weekly_avg_sentiment_chart():
    """Test creating weekly average sentiment chart."""
    df = create_test_dataframe(100)
    
    fig = create_weekly_avg_sentiment_chart(df)
    
    assert fig is not None
    assert 'Weekly Average Sentiment' in fig.layout.title.text
    # Should have 2 traces: polarity and subjectivity
    assert len(fig.data) == 2
    assert fig.data[0].name == 'Polarity'
    assert fig.data[1].name == 'Subjectivity'


def test_create_weekly_avg_sentiment_chart_empty():
    """Test weekly chart with empty DataFrame."""
    df = pd.DataFrame()
    
    fig = create_weekly_avg_sentiment_chart(df)
    
    assert fig is None


def test_create_weekly_avg_sentiment_chart_missing_columns():
    """Test weekly chart with missing required columns."""
    df = pd.DataFrame({
        'created_at': pd.date_range(start='2023-01-01', periods=10, freq='D'),
        'text': ['test'] * 10,
    })
    
    fig = create_weekly_avg_sentiment_chart(df)
    
    assert fig is None


def test_create_all_tweets_sentiment_chart():
    """Test creating all tweets sentiment chart."""
    df = create_test_dataframe(100)
    
    fig = create_all_tweets_sentiment_chart(df)
    
    assert fig is not None
    assert 'Sentiment Polarity of All Tweets' in fig.layout.title.text
    # Should have 1 trace: polarity line
    assert len(fig.data) == 1
    assert fig.data[0].mode == 'lines'  # No markers


def test_create_all_tweets_sentiment_chart_with_zoom():
    """Test creating all tweets chart with zoom to last N days."""
    df = create_test_dataframe(365)  # One year of data
    
    fig = create_all_tweets_sentiment_chart(df, zoom_to_last_n_days=60)
    
    assert fig is not None
    # Check that x-axis range is set (zoomed)
    assert fig.layout.xaxis.range is not None
    assert len(fig.layout.xaxis.range) == 2


def test_create_all_tweets_sentiment_chart_empty():
    """Test all tweets chart with empty DataFrame."""
    df = pd.DataFrame()
    
    fig = create_all_tweets_sentiment_chart(df)
    
    assert fig is None


def test_create_all_tweets_sentiment_chart_missing_columns():
    """Test all tweets chart with missing required columns."""
    df = pd.DataFrame({
        'created_at': pd.date_range(start='2023-01-01', periods=10, freq='D'),
        'text': ['test'] * 10,
    })
    
    fig = create_all_tweets_sentiment_chart(df)
    
    assert fig is None


def test_generate_all_charts_includes_new_charts():
    """Test that generate_all_charts includes the new sentiment charts."""
    df = create_test_dataframe(100)
    
    charts = generate_all_charts(df)
    
    assert 'sentiment_weekly_avg' in charts
    assert 'sentiment_all_tweets' in charts
    assert charts['sentiment_weekly_avg'] is not None
    assert charts['sentiment_all_tweets'] is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
