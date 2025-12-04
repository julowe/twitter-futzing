#!/usr/bin/env python3
"""Generate large test file for testing multi-worker file upload handling.

This script creates a mock Twitter archive file that exceeds Flask's default
500KB in-memory form data limit to test disk-based file handling.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


def generate_large_test_file(output_path: Path, num_tweets: int = 5000):
    """Generate a large mock tweets file.
    
    Args:
        output_path: Path where the file should be created
        num_tweets: Number of tweets to generate (default 5000 for ~2MB file)
    """
    base_date = datetime(2020, 1, 1)
    tweets = []

    for i in range(num_tweets):
        tweet_date = base_date + timedelta(days=i % 365, hours=i % 24, minutes=i % 60)
        tweet = {
            "tweet": {
                "id_str": f"1000000000000{i:06d}",
                "full_text": f"This is tweet number {i}. " + ("A" * (50 + (i % 100))),
                "created_at": tweet_date.strftime("%a %b %d %H:%M:%S +0000 %Y"),
                "favorite_count": str(i % 1000),
                "retweet_count": str(i % 100),
                "source": "Twitter Web App" if i % 2 == 0 else "Twitter for iPhone",
                "lang": "en"
            }
        }
        tweets.append(tweet)

    # Write in Twitter export format
    output = "window.YTD.tweets.part0 = " + json.dumps(tweets, indent=2)

    with open(output_path, "w") as f:
        f.write(output)
    
    # Print stats
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Created {output_path.name}: {size_mb:.2f} MB with {len(tweets)} tweets")
    
    return output_path


if __name__ == "__main__":
    # Generate in tests directory
    test_dir = Path(__file__).parent
    output_file = test_dir / "mock_large_tweets.js"
    generate_large_test_file(output_file)
