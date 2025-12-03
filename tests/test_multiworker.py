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


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Multi-Worker Compatibility Test Suite")
    print("="*70)
    
    tests = [
        ("Session Storage", test_session_storage),
        ("Single Worker (python)", test_webapp_single_worker),
        ("Gunicorn (1 worker)", test_webapp_gunicorn_single),
        ("Gunicorn (2 workers)", test_webapp_gunicorn_multi),
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
