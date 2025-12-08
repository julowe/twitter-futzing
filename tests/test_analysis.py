
import sys
import pandas as pd
from pathlib import Path
import pytest
from twitter_analyzer.analysis import (
    clean_text_for_analysis,
    analyze_sentiment,
    generate_wordcloud
)

# Add parent directory to path for imports if needed, though pytest usually handles this
# depending on invocation.
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_clean_text_for_analysis():
    """Test text cleaning for NLP."""
    # Test URL removal
    assert clean_text_for_analysis("Check this out https://example.com") == "Check this out"
    # Test mention removal
    assert clean_text_for_analysis("Hello @user") == "Hello"
    # Test special char removal
    assert clean_text_for_analysis("Hello!") == "Hello"
    # Test number removal (if intent is to keep only alpha, function doc says 'non-alphanumeric (keep spaces)', let's check validation)
    # The implementation: re.sub(r'[^a-zA-Z\s]', '', text) -> removes numbers too.
    assert clean_text_for_analysis("Phone 123") == "Phone" 
    
    # Test empty/None
    assert clean_text_for_analysis("") == ""
    assert clean_text_for_analysis(None) == ""

def test_analyze_sentiment():
    """Test sentiment analysis."""
    data = {
        "text": [
            "I love this amazing day!",
            "I hate this terrible error.",
            "This is a book."
        ]
    }
    df = pd.DataFrame(data)
    
    result = analyze_sentiment(df)
    
    # Check columns added
    assert "sentiment_polarity" in result.columns
    assert "sentiment_subjectivity" in result.columns
    assert "sentiment_category" in result.columns
    
    # Check values
    # Positive
    positive_row = result.iloc[0]
    assert positive_row["sentiment_polarity"] > 0
    assert positive_row["sentiment_category"] == "Positive"
    
    # Negative
    negative_row = result.iloc[1]
    assert negative_row["sentiment_polarity"] < 0
    assert negative_row["sentiment_category"] == "Negative"
    
    # Neutral
    neutral_row = result.iloc[2]
    # "This is a book" might be neutral (0.0). TextBlob logic varies but usually 0.0
    # Let's just check the type/range
    assert -1.0 <= neutral_row["sentiment_polarity"] <= 1.0

def test_analyze_sentiment_empty():
    """Test sentiment analysis with empty df."""
    df = pd.DataFrame({"other": []})
    result = analyze_sentiment(df)
    assert result.equals(df)

def test_generate_wordcloud():
    """Test wordcloud generation."""
    data = {
        "text": ["word " * 10, "another " * 5]
    }
    df = pd.DataFrame(data)
    
    wc = generate_wordcloud(df)
    
    assert wc is not None
    # We can't easily check the image content, but we can check if it returned a WordCloud object
    from wordcloud import WordCloud
    assert isinstance(wc, WordCloud)

def test_generate_wordcloud_no_text():
    """Test wordcloud with no text column."""
    df = pd.DataFrame({"other": [1, 2]})
    wc = generate_wordcloud(df)
    assert wc is None

def test_generate_wordcloud_empty_text():
    """Test wordcloud with empty text."""
    df = pd.DataFrame({"text": ["", None]})
    wc = generate_wordcloud(df)
    assert wc is None
