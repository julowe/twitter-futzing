# Test Suite for Twitter Archive Analyzer

This directory contains test files and mock data for testing the Twitter Archive Analyzer.

## Test Files

### Unit Tests
- **test_core.py**: Core functionality tests for parsing, normalization, and type coercion
- **test_integration.py**: Integration tests simulating the complete webapp workflow

### Mock Data Files

The mock data files simulate real Twitter archive exports and cover various formats and edge cases:

#### Regular Tweets (mock_tweets.js)
- 5 sample tweets in JavaScript format (`.js`)
- Includes tweets with:
  - Hashtags and user mentions
  - URLs and media attachments
  - Reply threads
  - Various engagement metrics (favorites, retweets)
  - Different client sources (Web, iPhone, Android, TweetDeck)

#### Deleted Tweets (mock_deleted_tweets.js)
- 2 sample deleted tweets
- Includes `deleted_at` timestamp field
- Tests handling of deleted content

#### Twitter Notes (mock_note_tweets.js)
- 2 sample Twitter Notes (long-form content)
- Tests `noteTweet` format with:
  - Extended text content
  - ISO 8601 timestamps (`createdAt`, `updatedAt`)
  - Hashtags and mentions

#### JSON Format (mock_tweets.json)
- 2 sample tweets in pure JSON format
- Tests handling of `.json` files without JavaScript wrapper
- Uses same structure as `.js` files

## Date Formats

The mock data includes both date formats used by Twitter:

1. **RFC 2822 format** (in `tweet.created_at`):
   ```
   "Wed Nov 15 12:00:45 +0000 2023"
   ```

2. **ISO 8601 format** (in `noteTweet.createdAt` and `deleted_at`):
   ```
   "2023-11-15T12:30:45.000Z"
   ```

This ensures the datetime parsing fix handles both formats correctly.

## Running Tests

### Run all unit tests:
```bash
python tests/test_core.py
```

### Run integration tests:
```bash
python tests/test_integration.py
```

### Run both test suites:
```bash
python tests/test_core.py && python tests/test_integration.py
```

## Expected Results

All tests should pass with:
- No UserWarning about datetime format inference
- 100% date parsing success rate
- All record types properly identified (tweet, deleted_tweet, note)
- No empty DataFrames

## Test Coverage

The test suite validates:
- ✓ Parsing `.js` files with JavaScript wrapper
- ✓ Parsing `.json` files without wrapper
- ✓ Handling deleted tweets with `deleted_at` field
- ✓ Handling Twitter Notes with ISO 8601 dates
- ✓ Date parsing for RFC 2822 format (Twitter API format)
- ✓ Date parsing for ISO 8601 format (Notes format)
- ✓ Data normalization to unified schema
- ✓ Type coercion (datetime, numeric, string)
- ✓ Summary generation
- ✓ Multi-file processing
- ✓ Webapp upload workflow
- ✓ Error handling
