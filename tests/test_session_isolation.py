#!/usr/bin/env python3
"""Test session isolation and unique URLs functionality."""

import io
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp import app
from werkzeug.datastructures import FileStorage


def test_session_isolation():
    """Test that users cannot access other sessions without the correct URL."""
    print("\ntest_session_isolation:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Upload first file to create session 1
        test_dir = Path(__file__).parent
        test_file = test_dir / "mock_tweets.js"
        
        with open(test_file, "rb") as f:
            file_content = f.read()
        
        file_storage1 = FileStorage(
            stream=io.BytesIO(file_content),
            filename="mock_tweets.js",
            content_type="application/javascript"
        )
        
        response1 = client.post(
            "/upload",
            data={"files": [file_storage1]},
            content_type="multipart/form-data",
            follow_redirects=False
        )
        
        assert response1.status_code == 302, "Upload 1 should redirect"
        session_id_1 = response1.location.split("/session/")[1].split("/")[0]
        print(f"✓ Created session 1: {session_id_1}")
        
        # Upload second file to create session 2
        file_storage2 = FileStorage(
            stream=io.BytesIO(file_content),
            filename="mock_tweets.js",
            content_type="application/javascript"
        )
        
        response2 = client.post(
            "/upload",
            data={"files": [file_storage2]},
            content_type="multipart/form-data",
            follow_redirects=False
        )
        
        assert response2.status_code == 302, "Upload 2 should redirect"
        session_id_2 = response2.location.split("/session/")[1].split("/")[0]
        print(f"✓ Created session 2: {session_id_2}")
        
        # Verify sessions are different
        assert session_id_1 != session_id_2, "Session IDs should be unique"
        print("✓ Session IDs are unique")
        
        # Verify session 1 can access its own results
        response = client.get(f"/session/{session_id_1}/results")
        assert response.status_code == 200, "Session 1 should access its own results"
        print("✓ Session 1 can access its own results")
        
        # Verify session 2 can access its own results
        response = client.get(f"/session/{session_id_2}/results")
        assert response.status_code == 200, "Session 2 should access its own results"
        print("✓ Session 2 can access its own results")
        
        # Try to access session with invalid ID
        response = client.get("/session/invalid_session_id_12345678/results")
        assert response.status_code == 302, "Invalid session should redirect"
        print("✓ Invalid session ID correctly redirects")
        
        # Try to access session with path traversal attempt
        # Note: Flask routing won't match this pattern, so it returns 404 not 302
        response = client.get("/session/../../../etc/passwd/results")
        assert response.status_code in (302, 404), "Path traversal attempt should be rejected"
        print("✓ Path traversal attempt blocked")
        
    print("-" * 70)
    return True


def test_unique_urls_preserve_state():
    """Test that unique URLs preserve session state across requests."""
    print("\ntest_unique_urls_preserve_state:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Upload file to create session
        test_dir = Path(__file__).parent
        test_file = test_dir / "mock_tweets.js"
        
        with open(test_file, "rb") as f:
            file_content = f.read()
        
        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename="mock_tweets.js",
            content_type="application/javascript"
        )
        
        response = client.post(
            "/upload",
            data={"files": [file_storage]},
            content_type="multipart/form-data",
            follow_redirects=False
        )
        
        session_id = response.location.split("/session/")[1].split("/")[0]
        print(f"✓ Created session: {session_id}")
        
        # Access results multiple times
        for i in range(3):
            response = client.get(f"/session/{session_id}/results")
            assert response.status_code == 200, f"Request {i+1} should succeed"
        print("✓ Session state preserved across multiple requests")
        
        # Access different endpoints with same session
        endpoints = [
            f"/session/{session_id}/download",
            f"/session/{session_id}/api/top-tweets",
            f"/session/{session_id}/api/data-preview",
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, f"{endpoint} should succeed"
        print("✓ All session endpoints accessible with session URL")
        
    print("-" * 70)
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("Session Isolation Test Suite")
    print("=" * 70)
    
    tests = [
        test_session_isolation,
        test_unique_urls_preserve_state,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
    
    print("=" * 70)
    if failed == 0:
        print(f"SUCCESS: All {passed} session isolation tests passed!")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"FAILURE: {passed} passed, {failed} failed")
        print("=" * 70)
        sys.exit(1)
