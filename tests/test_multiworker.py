#!/usr/bin/env python3
"""Tests for multi-worker compatibility (file loading and pagination).

This test ensures that the webapp works correctly when running with multiple
gunicorn workers, where session data needs to be shared across processes.
"""

import io
import os
import sys
import time
import subprocess
import requests
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp import app, save_session_data, load_session_data


def test_session_storage():
    """Test that session storage works across different contexts (simulating workers)."""
    print("\n" + "="*70)
    print("Testing Session Storage Across Workers")
    print("="*70)
    
    import pandas as pd
    import secrets
    
    # Create test data
    test_data = {
        "df": pd.DataFrame({
            "id_str": ["123", "456"],
            "text": ["Test 1", "Test 2"],
            "record_type": ["tweet", "tweet"],
        }),
        "timestamp": "2025-12-03T12:00:00",
    }
    
    # Save data (generate unique session ID for test isolation)
    session_id = secrets.token_hex(16)
    save_session_data(session_id, test_data)
    print(f"✓ Saved session data for {session_id}")
    
    # Load data (simulating different worker)
    loaded_data = load_session_data(session_id)
    
    if loaded_data is None:
        print("✗ FAILED: Could not load session data")
        return False
    
    if not isinstance(loaded_data["df"], pd.DataFrame):
        print("✗ FAILED: Loaded data is not a DataFrame")
        return False
    
    if len(loaded_data["df"]) != 2:
        print("✗ FAILED: DataFrame has wrong number of rows")
        return False
    
    print(f"✓ Successfully loaded session data with {len(loaded_data['df'])} rows")
    
    # Cleanup
    from webapp import delete_session_data
    delete_session_data(session_id)
    print("✓ Cleaned up test session data")
    
    return True


def test_webapp_single_worker():
    """Test webapp functionality with single worker (python webapp.py)."""
    print("\n" + "="*70)
    print("Testing Single Worker (python webapp.py)")
    print("="*70)
    
    # Start webapp in background
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_12345"
    
    proc = subprocess.Popen(
        [sys.executable, "webapp.py"],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5000/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        # Test file upload and pagination
        test_dir = Path(__file__).parent
        files = [
            ("files", ("mock_tweets.js", open(test_dir / "mock_tweets.js", "rb"), "application/javascript")),
            ("files", ("mock_deleted_tweets.js", open(test_dir / "mock_deleted_tweets.js", "rb"), "application/javascript")),
        ]
        
        session = requests.Session()
        
        # Upload files
        upload_response = session.post("http://localhost:5000/upload", files=files, allow_redirects=False, timeout=10)
        
        # Close file handles
        for _, (_, f, _) in files:
            f.close()
        
        if upload_response.status_code != 302:
            print(f"✗ FAILED: Upload returned {upload_response.status_code}")
            return False
        print("✓ File upload successful")
        
        # Test pagination endpoint
        pagination_response = session.get("http://localhost:5000/api/top-tweets?offset=0&limit=5", timeout=5)
        if pagination_response.status_code != 200:
            print(f"✗ FAILED: Pagination returned {pagination_response.status_code}")
            print(f"   Response: {pagination_response.text}")
            return False
        
        data = pagination_response.json()
        if "tweets" not in data:
            print("✗ FAILED: No tweets in response")
            return False
        
        print(f"✓ Pagination working ({len(data.get('tweets', []))} tweets loaded)")
        
        # Test data preview endpoint
        preview_response = session.get("http://localhost:5000/api/data-preview?offset=0&limit=5", timeout=5)
        if preview_response.status_code != 200:
            print(f"✗ FAILED: Data preview returned {preview_response.status_code}")
            return False
        
        preview_data = preview_response.json()
        if "records" not in preview_data:
            print("✗ FAILED: No records in preview response")
            return False
        
        print(f"✓ Data preview working ({len(preview_data.get('records', []))} records loaded)")
        
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        proc.wait(timeout=5)
        print("✓ Server stopped")


def test_webapp_gunicorn_single():
    """Test webapp with gunicorn single worker."""
    print("\n" + "="*70)
    print("Testing Gunicorn Single Worker")
    print("="*70)
    
    return test_with_gunicorn(1)


def test_webapp_gunicorn_multi():
    """Test webapp with gunicorn multiple workers."""
    print("\n" + "="*70)
    print("Testing Gunicorn Multiple Workers (2)")
    print("="*70)
    
    return test_with_gunicorn(2)


def test_with_gunicorn(workers):
    """Helper to test with gunicorn."""
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_12345"
    
    # Start gunicorn
    proc = subprocess.Popen(
        [
            "gunicorn",
            "--bind", "0.0.0.0:5001",
            "--workers", str(workers),
            "--timeout", "30",
            "webapp:app"
        ],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(5)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5001/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        # Test file upload and pagination multiple times to hit different workers
        for attempt in range(3):
            print(f"\n  Attempt {attempt + 1}/3:")
            
            test_dir = Path(__file__).parent
            files = [
                ("files", ("mock_tweets.js", open(test_dir / "mock_tweets.js", "rb"), "application/javascript")),
                ("files", ("mock_deleted_tweets.js", open(test_dir / "mock_deleted_tweets.js", "rb"), "application/javascript")),
            ]
            
            session = requests.Session()
            
            # Upload files
            upload_response = session.post("http://localhost:5001/upload", files=files, allow_redirects=False, timeout=10)
            
            # Close file handles
            for _, (_, f, _) in files:
                f.close()
            
            if upload_response.status_code != 302:
                print(f"  ✗ Upload attempt {attempt + 1} failed: {upload_response.status_code}")
                return False
            print(f"  ✓ Upload successful")
            
            # Test pagination endpoint (may hit different worker)
            pagination_response = session.get("http://localhost:5001/api/top-tweets?offset=0&limit=5", timeout=5)
            if pagination_response.status_code != 200:
                print(f"  ✗ Pagination failed: {pagination_response.status_code}")
                print(f"     Response: {pagination_response.text}")
                return False
            
            data = pagination_response.json()
            if "tweets" not in data:
                print(f"  ✗ No tweets in response")
                return False
            
            print(f"  ✓ Pagination working ({len(data.get('tweets', []))} tweets)")
            
            # Test data preview
            preview_response = session.get("http://localhost:5001/api/data-preview?offset=0&limit=5", timeout=5)
            if preview_response.status_code != 200:
                print(f"  ✗ Data preview failed: {preview_response.status_code}")
                return False
            
            preview_data = preview_response.json()
            if "records" not in preview_data:
                print(f"  ✗ No records in preview")
                return False
            
            print(f"  ✓ Data preview working ({len(preview_data.get('records', []))} records)")
            
            # Small delay between attempts
            time.sleep(0.5)
        
        print(f"\n✓ All 3 attempts successful with {workers} worker(s)")
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✓ Server stopped")


def ensure_large_test_file():
    """Ensure the large test file exists, generating it if necessary."""
    test_dir = Path(__file__).parent
    large_file_path = test_dir / "mock_large_tweets.js"
    
    if not large_file_path.exists():
        print("  Generating large test file...")
        # Import and run the generator
        import sys
        sys.path.insert(0, str(test_dir))
        from generate_large_test_file import generate_large_test_file
        generate_large_test_file(large_file_path)
    
    return large_file_path


def ensure_medium_test_files():
    """Ensure the medium test files exist, generating them if necessary."""
    test_dir = Path(__file__).parent
    deleted_file_path = test_dir / "mock_medium_deleted_tweets.js"
    notes_file_path = test_dir / "mock_medium_note_tweets.js"
    
    if not deleted_file_path.exists() or not notes_file_path.exists():
        print("  Generating medium test files...")
        # Import and run the generator
        import sys
        sys.path.insert(0, str(test_dir))
        from generate_medium_test_files import generate_medium_deleted_tweets, generate_medium_note_tweets
        
        if not deleted_file_path.exists():
            generate_medium_deleted_tweets(deleted_file_path, num_tweets=250)
        if not notes_file_path.exists():
            generate_medium_note_tweets(notes_file_path, num_notes=120)
    
    return deleted_file_path, notes_file_path


def test_large_file_upload():
    """Test uploading a large file (> 500KB to exceed Flask's default in-memory limit)."""
    print("\n" + "="*70)
    print("Testing Large File Upload")
    print("="*70)
    
    # Ensure large test file exists
    large_file_path = ensure_large_test_file()
    
    # Start webapp in background
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_large_file"
    
    proc = subprocess.Popen(
        [sys.executable, "webapp.py"],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5000/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        # Test large file upload (file path already ensured above)
        if not large_file_path.exists():
            print(f"✗ FAILED: Large test file not found at {large_file_path}")
            return False
        
        file_size_mb = large_file_path.stat().st_size / (1024 * 1024)
        print(f"  Large file size: {file_size_mb:.2f} MB")
        
        session = requests.Session()
        
        # Upload large file
        with open(large_file_path, "rb") as f:
            files = [("files", ("mock_large_tweets.js", f, "application/javascript"))]
            upload_response = session.post("http://localhost:5000/upload", files=files, allow_redirects=False, timeout=30)
        
        if upload_response.status_code != 302:
            print(f"✗ FAILED: Large file upload returned {upload_response.status_code}")
            return False
        print(f"✓ Large file upload successful")
        
        # Test that data is accessible via pagination
        pagination_response = session.get("http://localhost:5000/api/top-tweets?offset=0&limit=10", timeout=10)
        if pagination_response.status_code != 200:
            print(f"✗ FAILED: Pagination after large upload returned {pagination_response.status_code}")
            print(f"   Response: {pagination_response.text}")
            return False
        
        data = pagination_response.json()
        if "tweets" not in data:
            print("✗ FAILED: No tweets in response after large file upload")
            return False
        
        total = data.get("total", 0)
        print(f"✓ Pagination working after large upload ({len(data.get('tweets', []))} tweets loaded, {total} total)")
        
        # Verify we got a substantial number of tweets
        if total < 1000:
            print(f"✗ WARNING: Expected > 1000 tweets but got {total}")
        
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        proc.wait(timeout=5)
        print("✓ Server stopped")


def test_large_file_gunicorn():
    """Test large file upload with gunicorn (2 workers)."""
    print("\n" + "="*70)
    print("Testing Large File Upload with Gunicorn (2 workers)")
    print("="*70)
    
    # Ensure large test file exists
    large_file_path = ensure_large_test_file()
    
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_large_gunicorn"
    
    # Start gunicorn with 2 workers
    proc = subprocess.Popen(
        [
            "gunicorn",
            "--bind", "0.0.0.0:5002",
            "--workers", "2",
            "--timeout", "60",
            "webapp:app"
        ],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(5)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5002/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        # Test large file upload multiple times to hit different workers
        for attempt in range(2):
            print(f"\n  Attempt {attempt + 1}/2:")
            
            # File path already ensured above
            if not large_file_path.exists():
                print(f"  ✗ Large test file not found")
                return False
            
            session = requests.Session()
            
            # Upload large file
            with open(large_file_path, "rb") as f:
                files = [("files", ("mock_large_tweets.js", f, "application/javascript"))]
                upload_response = session.post("http://localhost:5002/upload", files=files, allow_redirects=False, timeout=30)
            
            if upload_response.status_code != 302:
                print(f"  ✗ Upload attempt {attempt + 1} failed: {upload_response.status_code}")
                return False
            print(f"  ✓ Upload successful")
            
            # Test pagination (may hit different worker)
            pagination_response = session.get("http://localhost:5002/api/top-tweets?offset=0&limit=10", timeout=10)
            if pagination_response.status_code != 200:
                print(f"  ✗ Pagination failed: {pagination_response.status_code}")
                print(f"     Response: {pagination_response.text}")
                return False
            
            data = pagination_response.json()
            if "tweets" not in data:
                print(f"  ✗ No tweets in response")
                return False
            
            total = data.get("total", 0)
            print(f"  ✓ Pagination working ({len(data.get('tweets', []))} tweets, {total} total)")
            
            # Small delay between attempts
            time.sleep(0.5)
        
        print(f"\n✓ All 2 attempts successful with 2 workers")
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✓ Server stopped")


def test_medium_deleted_tweets_gunicorn():
    """Test medium-sized deleted tweets file with gunicorn (2 workers)."""
    print("\n" + "="*70)
    print("Testing Medium Deleted Tweets File with Gunicorn (2 workers)")
    print("="*70)
    
    # Ensure medium test files exist
    deleted_file_path, _ = ensure_medium_test_files()
    
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_deleted_gunicorn"
    
    # Start gunicorn with 2 workers
    proc = subprocess.Popen(
        [
            "gunicorn",
            "--bind", "0.0.0.0:5003",
            "--workers", "2",
            "--timeout", "60",
            "webapp:app"
        ],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(5)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5003/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        file_size_kb = deleted_file_path.stat().st_size / 1024
        print(f"  File size: {file_size_kb:.2f} KB")
        
        # Test deleted tweets file upload multiple times to hit different workers
        for attempt in range(2):
            print(f"\n  Attempt {attempt + 1}/2:")
            
            session = requests.Session()
            
            # Upload deleted tweets file
            with open(deleted_file_path, "rb") as f:
                files = [("files", ("mock_medium_deleted_tweets.js", f, "application/javascript"))]
                upload_response = session.post("http://localhost:5003/upload", files=files, allow_redirects=False, timeout=30)
            
            if upload_response.status_code != 302:
                print(f"  ✗ Upload attempt {attempt + 1} failed: {upload_response.status_code}")
                return False
            print(f"  ✓ Upload successful")
            
            # Test data preview (deleted tweets don't show in top tweets)
            preview_response = session.get("http://localhost:5003/api/data-preview?offset=0&limit=10", timeout=10)
            if preview_response.status_code != 200:
                print(f"  ✗ Data preview failed: {preview_response.status_code}")
                print(f"     Response: {preview_response.text}")
                return False
            
            preview_data = preview_response.json()
            if "records" not in preview_data:
                print(f"  ✗ No records in preview")
                return False
            
            total = preview_data.get("total", 0)
            records = preview_data.get("records", [])
            print(f"  ✓ Data preview working ({len(records)} records, {total} total)")
            
            # Verify we got deleted tweets
            if records and records[0].get("record_type") != "deleted_tweet":
                print(f"  ✗ Expected deleted_tweet but got {records[0].get('record_type')}")
                return False
            
            print(f"  ✓ Deleted tweets loaded correctly")
            
            # Small delay between attempts
            time.sleep(0.5)
        
        print(f"\n✓ All 2 attempts successful with 2 workers")
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✓ Server stopped")


def test_medium_note_tweets_gunicorn():
    """Test medium-sized note tweets file with gunicorn (2 workers)."""
    print("\n" + "="*70)
    print("Testing Medium Note Tweets File with Gunicorn (2 workers)")
    print("="*70)
    
    # Ensure medium test files exist
    _, notes_file_path = ensure_medium_test_files()
    
    env = os.environ.copy()
    env["SECRET_KEY"] = "test_secret_key_notes_gunicorn"
    
    # Start gunicorn with 2 workers
    proc = subprocess.Popen(
        [
            "gunicorn",
            "--bind", "0.0.0.0:5004",
            "--workers", "2",
            "--timeout", "60",
            "webapp:app"
        ],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    time.sleep(5)
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:5004/health", timeout=5)
        if response.status_code != 200:
            print(f"✗ FAILED: Health check returned {response.status_code}")
            return False
        print("✓ Health endpoint working")
        
        file_size_kb = notes_file_path.stat().st_size / 1024
        print(f"  File size: {file_size_kb:.2f} KB")
        
        # Test note tweets file upload multiple times to hit different workers
        for attempt in range(2):
            print(f"\n  Attempt {attempt + 1}/2:")
            
            session = requests.Session()
            
            # Upload note tweets file
            with open(notes_file_path, "rb") as f:
                files = [("files", ("mock_medium_note_tweets.js", f, "application/javascript"))]
                upload_response = session.post("http://localhost:5004/upload", files=files, allow_redirects=False, timeout=30)
            
            if upload_response.status_code != 302:
                print(f"  ✗ Upload attempt {attempt + 1} failed: {upload_response.status_code}")
                return False
            print(f"  ✓ Upload successful")
            
            # Test data preview (note tweets show in data preview)
            preview_response = session.get("http://localhost:5004/api/data-preview?offset=0&limit=10", timeout=10)
            if preview_response.status_code != 200:
                print(f"  ✗ Data preview failed: {preview_response.status_code}")
                print(f"     Response: {preview_response.text}")
                return False
            
            preview_data = preview_response.json()
            if "records" not in preview_data:
                print(f"  ✗ No records in preview")
                return False
            
            total = preview_data.get("total", 0)
            records = preview_data.get("records", [])
            print(f"  ✓ Data preview working ({len(records)} records, {total} total)")
            
            # Verify we got note tweets
            if records and records[0].get("record_type") != "note":
                print(f"  ✗ Expected note but got {records[0].get('record_type')}")
                return False
            
            print(f"  ✓ Note tweets loaded correctly")
            
            # Small delay between attempts
            time.sleep(0.5)
        
        print(f"\n✓ All 2 attempts successful with 2 workers")
        return True
        
    finally:
        # Stop the server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✓ Server stopped")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Multi-Worker Compatibility Test Suite")
    print("="*70)
    
    tests = [
        ("Session Storage", test_session_storage),
        ("Large File Upload (single worker)", test_large_file_upload),
        ("Single Worker (python)", test_webapp_single_worker),
        ("Gunicorn (1 worker)", test_webapp_gunicorn_single),
        ("Gunicorn (2 workers)", test_webapp_gunicorn_multi),
        ("Large File Upload (gunicorn 2 workers)", test_large_file_gunicorn),
        ("Medium Deleted Tweets (gunicorn 2 workers)", test_medium_deleted_tweets_gunicorn),
        ("Medium Note Tweets (gunicorn 2 workers)", test_medium_note_tweets_gunicorn),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Print summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    print("="*70)
    if all_passed:
        print("SUCCESS: All multi-worker tests passed!")
        return 0
    else:
        print("FAILURE: Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
