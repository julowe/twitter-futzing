#!/usr/bin/env python3
"""Generate medium-sized test files for deleted tweets and note tweets.

These files are 250-300KB to test in-memory handling with gunicorn workers.
Flask's default in-memory limit is 500KB, so these files should stay in memory
but we want to test that session storage still works correctly.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


def generate_medium_deleted_tweets(output_path: Path, num_tweets: int = 1000):
    """Generate a medium-sized deleted tweets file (~250-300KB).
    
    Args:
        output_path: Path where the file should be created
        num_tweets: Number of deleted tweets to generate (default 1000 for ~250KB)
    """
    base_date = datetime(2023, 1, 1)
    deleted_tweets = []

    for i in range(num_tweets):
        tweet_date = base_date + timedelta(days=i % 365, hours=i % 24)
        deleted_date = tweet_date + timedelta(hours=1)
        
        deleted_tweet = {
            "tweet": {
                "edit_info": {
                    "initial": {
                        "editTweetIds": [f"1234567890123{i:09d}"],
                        "editableUntil": deleted_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "editsRemaining": "5",
                        "isEditEligible": False
                    }
                },
                "retweeted": False,
                "source": '<a href="https://mobile.twitter.com" rel="nofollow">Twitter Web App</a>' if i % 2 == 0 else '<a href="http://twitter.com/download/iphone" rel="nofollow">Twitter for iPhone</a>',
                "entities": {
                    "hashtags": [],
                    "symbols": [],
                    "user_mentions": [],
                    "urls": []
                },
                "display_text_range": ["0", "60"],
                "favorite_count": str(i % 50),
                "id_str": f"1234567890123{i:09d}",
                "truncated": False,
                "retweet_count": str(i % 10),
                "id": f"1234567890123{i:09d}",
                "possibly_sensitive": False,
                "created_at": tweet_date.strftime("%a %b %d %H:%M:%S +0000 %Y"),
                "favorited": False,
                "full_text": f"This deleted tweet #{i} was removed. " + ("X" * (30 + (i % 50))),
                "lang": "en",
                "deleted_at": deleted_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            }
        }
        deleted_tweets.append(deleted_tweet)

    # Write in Twitter export format
    output = "window.YTD.deleted_tweets.part0 = " + json.dumps(deleted_tweets, indent=2)

    with open(output_path, "w") as f:
        f.write(output)
    
    # Print stats
    size_kb = output_path.stat().st_size / 1024
    print(f"Created {output_path.name}: {size_kb:.2f} KB with {len(deleted_tweets)} deleted tweets")
    
    return output_path


def generate_medium_note_tweets(output_path: Path, num_notes: int = 500):
    """Generate a medium-sized note tweets file (~250-300KB).
    
    Args:
        output_path: Path where the file should be created
        num_notes: Number of note tweets to generate (default 500 for ~250KB)
    """
    base_date = datetime(2023, 1, 1)
    note_tweets = []

    for i in range(num_notes):
        note_date = base_date + timedelta(days=i % 365, hours=i % 24, minutes=i % 60)
        
        note_tweet = {
            "noteTweet": {
                "noteTweetId": f"1234567890123{i:09d}",
                "createdAt": note_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "updatedAt": note_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "core": {
                    "styletags": [],
                    "urls": [
                        {
                            "url": f"https://example.com/article-{i}",
                            "urlType": "source"
                        }
                    ] if i % 3 == 0 else [],
                    "text": f"Twitter Note #{i}: This is a longer-form note discussing various topics. " + 
                           ("Notes allow for more detailed explanations and in-depth content. " * (2 + (i % 5))) +
                           f"This note includes thoughts on technology, social media, and communication. " +
                           ("Additional content to make the note more substantial. " * (1 + (i % 3))),
                    "mentions": [
                        {
                            "screenName": "twitter",
                            "name": "Twitter",
                            "id": "783214"
                        }
                    ] if i % 5 == 0 else [],
                    "hashtags": [
                        {
                            "text": f"Topic{i % 10}",
                            "fromIndex": "50",
                            "toIndex": "60"
                        }
                    ] if i % 2 == 0 else [],
                    "cashtags": []
                },
                "url": f"https://twitter.com/i/notes/1234567890123{i:09d}"
            }
        }
        note_tweets.append(note_tweet)

    # Write in Twitter export format
    output = "window.YTD.note_tweet.part0 = " + json.dumps(note_tweets, indent=2)

    with open(output_path, "w") as f:
        f.write(output)
    
    # Print stats
    size_kb = output_path.stat().st_size / 1024
    print(f"Created {output_path.name}: {size_kb:.2f} KB with {len(note_tweets)} note tweets")
    
    return output_path


if __name__ == "__main__":
    # Generate in tests directory
    test_dir = Path(__file__).parent
    
    deleted_file = test_dir / "mock_medium_deleted_tweets.js"
    generate_medium_deleted_tweets(deleted_file)
    
    notes_file = test_dir / "mock_medium_note_tweets.js"
    generate_medium_note_tweets(notes_file)
