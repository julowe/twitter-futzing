#!/usr/bin/env python3
"""Integration test that simulates the webapp file upload workflow.

This test simulates the exact workflow described in the issue:
- Upload files via the webapp
- Process them
- Verify no warnings are emitted
- Verify data is not empty
"""

import io
import sys
import warnings
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from werkzeug.datastructures import FileStorage

# Capture warnings
warnings.simplefilter("always")

from webapp import app
from twitter_analyzer.core import process_files


def test_webapp_upload_workflow():
    """Test the complete webapp upload and processing workflow."""
    
    print("Testing webapp file upload workflow...")
    print("-" * 70)
    
    # Read test files
    test_dir = Path(__file__).parent
    test_files = [
        "mock_tweets.js",
        "mock_deleted_tweets.js",
        "mock_note_tweets.js",
        "mock_tweets.json",
    ]
    
    file_data = []
    for filename in test_files:
        filepath = test_dir / filename
        with open(filepath, "rb") as f:
            file_data.append((filename, f.read()))
    
    print(f"Loaded {len(file_data)} test files")
    
    # Capture any warnings during processing
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        
        # Process files exactly as the webapp does
        df, errors = process_files(file_data)
        
        # Check for the specific UserWarning about datetime format
        datetime_warnings = [
            w for w in warning_list 
            if issubclass(w.category, UserWarning) 
            and "Could not infer format" in str(w.message)
        ]
        
        if datetime_warnings:
            print("✗ FAILED: UserWarning about datetime format was raised!")
            for w in datetime_warnings:
                print(f"  Warning: {w.message}")
                print(f"  File: {w.filename}:{w.lineno}")
            return False
        
        print(f"✓ No datetime format warnings raised")
    
    # Verify processing results
    if errors:
        print(f"✗ FAILED: Errors during processing: {errors}")
        return False
    
    print(f"✓ No processing errors")
    
    if df.empty:
        print("✗ FAILED: DataFrame is empty - 'No data available' error would occur")
        return False
    
    print(f"✓ DataFrame is not empty: {len(df)} records")
    
    # Verify all dates were parsed
    if "created_at" in df.columns:
        valid_dates = df["created_at"].notna().sum()
        total_records = len(df)
        if valid_dates == 0:
            print("✗ FAILED: No dates were parsed")
            return False
        
        print(f"✓ Date parsing successful: {valid_dates}/{total_records} valid dates")
        
        # Check date range
        if valid_dates > 0:
            date_range = f"{df['created_at'].min()} to {df['created_at'].max()}"
            print(f"  Date range: {date_range}")
    
    # Verify record types
    if "record_type" in df.columns:
        record_types = df["record_type"].value_counts().to_dict()
        print(f"✓ Record types found: {', '.join(f'{k}({v})' for k, v in record_types.items())}")
    
    print("-" * 70)
    print("✓ All checks passed! The issue is fixed.")
    return True


def test_webapp_endpoint_simulation():
    """Test simulating actual webapp HTTP requests."""
    
    print("\nTesting webapp endpoint simulation...")
    print("-" * 70)
    
    with app.test_client() as client:
        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200, "Health endpoint should return 200"
        print("✓ Health endpoint works")
        
        # Test index page
        response = client.get("/")
        assert response.status_code == 200, "Index page should return 200"
        print("✓ Index page loads")
        
        # Simulate file upload
        test_dir = Path(__file__).parent
        test_file = test_dir / "mock_tweets.js"
        
        with open(test_file, "rb") as f:
            file_content = f.read()
        
        # Create a FileStorage object (simulates uploaded file)
        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename="mock_tweets.js",
            content_type="application/javascript"
        )
        
        # Capture warnings during upload
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")
            
            response = client.post(
                "/upload",
                data={"files": [file_storage]},
                content_type="multipart/form-data"
            )
            
            # Check for datetime warnings
            datetime_warnings = [
                w for w in warning_list 
                if issubclass(w.category, UserWarning) 
                and "Could not infer format" in str(w.message)
            ]
            
            if datetime_warnings:
                print("✗ FAILED: UserWarning raised during upload!")
                return False
        
        # Should redirect to results
        assert response.status_code == 302, "Upload should redirect"
        print("✓ File upload successful (redirect to results)")
    
    print("-" * 70)
    print("✓ Webapp endpoint simulation passed!")
    return True


def main():
    """Run all integration tests."""
    print("=" * 70)
    print("Twitter Archive Analyzer - Integration Test Suite")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print("=" * 70)
    print()
    
    all_passed = True
    
    # Test 1: Direct workflow
    if not test_webapp_upload_workflow():
        all_passed = False
    
    # Test 2: Webapp endpoints
    if not test_webapp_endpoint_simulation():
        all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("SUCCESS: All integration tests passed!")
        print("The datetime parsing issue is fixed.")
    else:
        print("FAILURE: Some tests failed.")
    print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
