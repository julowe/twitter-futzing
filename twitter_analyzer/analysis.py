"""NLP analysis functions for Twitter archive data.

This module provides functions for sentiment analysis using TextBlob
and word cloud generation using wordcloud.
"""

import io
import re
from typing import Optional

import pandas as pd
from textblob import TextBlob
from wordcloud import WordCloud, STOPWORDS as WC_STOPWORDS

# Additional stopwords including user requested "then, and, this, he"
# Note: "and", "this", "he" are already in default stopwords, but adding explicity doesn't hurt
CUSTOM_STOPWORDS = {
    "t", "co", "https", "http", "rt", "gt", "lt", "amp", "twitter", "com",
    "then", "and", "this", "he", "she", "it", "that", "there", "what"
}

STOPWORDS = WC_STOPWORDS.union(CUSTOM_STOPWORDS)


def clean_text_for_analysis(text: str) -> str:
    """Clean text for NLP analysis.
    
    Removes URLs, mentions, and special characters.
    """
    if not isinstance(text, str):
        return ""
    
    # Remove URLs
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    # Remove user mentions
    text = re.sub(r'@\w+', '', text)
    # Remove HTML entities
    text = re.sub(r'&[a-z]+;', '', text)
    # Remove non-alphanumeric (keep spaces)
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    
    return text.strip()


def analyze_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment analysis columns to DataFrame.
    
    Adds 'sentiment_polarity' (-1 to 1) and 'sentiment_subjectivity' (0 to 1).
    
    Args:
        df: DataFrame with Twitter data.
        
    Returns:
        DataFrame with added sentiment columns.
    """
    if "text" not in df.columns:
        return df
    
    def get_sentiment(text):
        if not isinstance(text, str) or not text.strip():
            return pd.Series([0.0, 0.0])
        blob = TextBlob(clean_text_for_analysis(text))
        return pd.Series([blob.sentiment.polarity, blob.sentiment.subjectivity])
    
    # Apply sentiment analysis
    # Note: This can be slow for large datasets
    sentiments = df["text"].apply(get_sentiment)
    df["sentiment_polarity"] = sentiments[0]
    df["sentiment_subjectivity"] = sentiments[1]
    
    # Categorize sentiment
    def categorize(polarity):
        if polarity > 0.1:
            return "Positive"
        elif polarity < -0.1:
            return "Negative"
        else:
            return "Neutral"
            
    df["sentiment_category"] = df["sentiment_polarity"].apply(categorize)
    
    return df


def generate_wordcloud(df: pd.DataFrame, width: int = 800, height: int = 400) -> Optional[WordCloud]:
    """Generate a word cloud from tweet text.
    
    Args:
        df: DataFrame with Twitter data.
        width: Width of the image.
        height: Height of the image.
        
    Returns:
        WordCloud object or None if no text data.
    """
    if "text" not in df.columns or df.empty:
        return None
        
    # Combine all text
    text_content = " ".join(df["text"].dropna().astype(str).tolist())
    
    # Clean text
    # We do a simpler clean here to keep some context, but remove URLs
    text_content = re.sub(r'http\S+|www\S+|https\S+', '', text_content)
    
    if not text_content.strip():
        return None
        
    # Generate word cloud
    wc = WordCloud(
        width=width,
        height=height,
        background_color="white",
        stopwords=STOPWORDS,
        colormap="viridis",
        collocations=True,
        min_word_length=3
    ).generate(text_content)
    
    return wc
