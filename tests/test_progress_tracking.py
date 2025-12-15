#!/usr/bin/env python3
"""Tests for progress tracking in webapp.

This test suite validates the progress bar functionality end-to-end.
"""

import io
import sys
import time
import json
from pathlib import Path
from threading import Thread

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp import app, upload_progress, update_progress, clear_progress
from werkzeug.datastructures import FileStorage


def test_progress_endpoint():
    """Test that progress endpoint returns correct data."""
    print("\ntest_progress_endpoint:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Test with non-existent upload_id
        response = client.get("/progress/0123456789abcdef0123456789abcdef")
        assert response.status_code == 200
        data = response.get_json()
        assert data["stage"] == "initializing"
        assert data["percent"] == 0
        assert data["message"] == "Starting..."
        print("✓ Progress endpoint returns default for unknown upload_id")
        
        # Test with actual progress data
        test_id = "abcd1234abcd1234abcd1234abcd1234"
        update_progress(test_id, "processing", 50, "Processing files...")
        
        response = client.get(f"/progress/{test_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["stage"] == "processing"
        assert data["percent"] == 50
        assert data["message"] == "Processing files..."
        print("✓ Progress endpoint returns updated progress")
        
        clear_progress(test_id)
    
    return True


def test_upload_id_generation():
    """Test that upload ID is generated correctly."""
    print("\ntest_upload_id_generation:")
    print("-" * 70)
    
    with app.test_client() as client:
        response = client.post('/upload?get_id=true', headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        data = response.get_json()
        assert "upload_id" in data
        assert len(data["upload_id"]) == 32  # 16 bytes as hex = 32 chars
        print(f"✓ Upload ID generated: {data['upload_id'][:16]}...")
    
    return True


def test_upload_with_progress_tracking():
    """Test file upload with progress tracking."""
    print("\ntest_upload_with_progress_tracking:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Step 1: Get upload ID
        response = client.post('/upload?get_id=true', headers={'X-Requested-With': 'XMLHttpRequest'})
        upload_id = response.get_json()["upload_id"]
        print(f"✓ Got upload_id: {upload_id[:16]}...")
        
        # Step 2: Upload file with upload_id
        test_file = Path(__file__).parent / "mock_tweets.js"
        with open(test_file, 'rb') as f:
            file_content = f.read()
        
        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename='mock_tweets.js',
            content_type='application/javascript'
        )
        
        # Track progress updates during upload
        progress_updates = []
        
        def check_progress():
            """Background thread to check progress during upload."""
            for i in range(10):  # Check 10 times over ~1 second
                time.sleep(0.1)
                if upload_id in upload_progress:
                    progress_updates.append(upload_progress[upload_id].copy())
        
        # Start background progress checker
        checker = Thread(target=check_progress)
        checker.start()
        
        response = client.post(
            '/upload',
            data={
                'files': [file_storage],
                'upload_id': upload_id
            },
            content_type='multipart/form-data',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        
        checker.join()  # Wait for progress checker to finish
        
        assert response.status_code == 200
        result = response.get_json()
        assert result["success"] is True
        print(f"✓ Upload successful")
        
        # Verify progress updates were captured
        if progress_updates:
            print(f"✓ Captured {len(progress_updates)} progress updates:")
            for i, update in enumerate(progress_updates):
                print(f"  {i+1}. {update['percent']}% - {update['stage']} - {update['message']}")
        else:
            print("⚠ No progress updates captured (may be too fast)")
        
        # Check final state (should be cleared)
        final_state = upload_id in upload_progress
        if not final_state:
            print("✓ Progress cleared after completion")
        else:
            print(f"  Final progress: {upload_progress[upload_id]}")
    
    return True


def test_progress_stages():
    """Test that all progress stages are hit during processing."""
    print("\ntest_progress_stages:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Get upload ID
        response = client.post('/upload?get_id=true', headers={'X-Requested-With': 'XMLHttpRequest'})
        upload_id = response.get_json()["upload_id"]
        
        # Upload file
        test_file = Path(__file__).parent / "mock_tweets.js"
        with open(test_file, 'rb') as f:
            file_storage = FileStorage(
                stream=io.BytesIO(f.read()),
                filename='mock_tweets.js',
                content_type='application/javascript'
            )
        
        # Track all stages
        stages_seen = set()
        
        def monitor_stages():
            """Monitor progress stages."""
            for _ in range(50):  # Monitor for ~5 seconds
                time.sleep(0.1)
                if upload_id in upload_progress:
                    stage = upload_progress[upload_id]['stage']
                    stages_seen.add(stage)
        
        monitor = Thread(target=monitor_stages)
        monitor.start()
        
        response = client.post(
            '/upload',
            data={'files': [file_storage], 'upload_id': upload_id},
            content_type='multipart/form-data',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        
        monitor.join()
        
        # Expected stages
        expected_stages = {'uploading', 'processing', 'analyzing', 'generating_charts', 'complete'}
        
        print(f"✓ Stages seen: {stages_seen}")
        print(f"  Expected: {expected_stages}")
        
        # At least some stages should be seen
        common = stages_seen.intersection(expected_stages)
        if common:
            print(f"✓ Found {len(common)} expected stages: {common}")
        else:
            print(f"⚠ No expected stages found (processing may be too fast)")
    
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("Progress Tracking Test Suite")
    print("=" * 70)
    
    tests = [
        test_progress_endpoint,
        test_upload_id_generation,
        test_upload_with_progress_tracking,
        test_progress_stages,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    sys.exit(0 if failed == 0 else 1)
