#!/usr/bin/env python3
"""Tests for webapp functionality including the download feature.

This test suite validates:
- Download endpoint functionality
- ZIP file generation
- CSV file generation
- PNG image generation (if kaleido available)
- HTML and Markdown report generation
"""

import io
import sys
import zipfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp import app
from werkzeug.datastructures import FileStorage


def test_download_endpoint_requires_session():
    """Test that download endpoint requires a valid session."""
    print("\ntest_download_endpoint_requires_session:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Try to download without uploading first
        response = client.get("/download")
        
        # Should redirect to index
        assert response.status_code == 302, "Should redirect without session"
        assert "/download" not in response.location, "Should not stay on download page"
        print("✓ Download endpoint correctly requires session")
    
    return True


def test_download_generates_zip():
    """Test that download endpoint generates a ZIP file with correct contents."""
    print("\ntest_download_generates_zip:")
    print("-" * 70)
    
    with app.test_client() as client:
        # First, upload a file to create a session
        test_dir = Path(__file__).parent
        test_file = test_dir / "mock_tweets.js"
        
        with open(test_file, "rb") as f:
            file_content = f.read()
        
        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename="mock_tweets.js",
            content_type="application/javascript"
        )
        
        # Upload file
        response = client.post(
            "/upload",
            data={"files": [file_storage]},
            content_type="multipart/form-data",
            follow_redirects=False
        )
        
        assert response.status_code == 302, "Upload should redirect"
        print("✓ File uploaded successfully")
        
        # Now download the ZIP
        response = client.get("/download")
        
        assert response.status_code == 200, "Download should succeed"
        assert response.mimetype == "application/zip", "Should return ZIP file"
        print("✓ Download endpoint returns ZIP file")
        
        # Parse the ZIP file
        zip_data = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            file_list = zip_file.namelist()
            
            print(f"✓ ZIP contains {len(file_list)} files:")
            for filename in sorted(file_list):
                file_size = zip_file.getinfo(filename).file_size
                print(f"  - {filename} ({file_size:,} bytes)")
            
            # Verify expected files are present
            csv_files = [f for f in file_list if f.endswith('.csv')]
            assert len(csv_files) >= 1, "Should have at least one CSV file"
            print(f"✓ Found {len(csv_files)} CSV file(s)")
            
            # Check for all records CSV
            all_records_csv = [f for f in csv_files if 'twitter_records_' in f]
            assert len(all_records_csv) == 1, "Should have one all-records CSV"
            print("✓ Found all-records CSV file")
            
            # Check for report files
            html_reports = [f for f in file_list if f.endswith('.html')]
            md_reports = [f for f in file_list if f.endswith('.md')]
            
            assert len(html_reports) == 1, "Should have one HTML report"
            assert len(md_reports) == 1, "Should have one Markdown report"
            print("✓ Found HTML and Markdown reports")
            
            # Check for PNG images (optional, depends on kaleido availability)
            png_files = [f for f in file_list if f.endswith('.png')]
            print(f"  Found {len(png_files)} PNG image(s)")
            
            # Verify CSV content is valid
            all_records_filename = all_records_csv[0]
            csv_content = zip_file.read(all_records_filename).decode('utf-8')
            
            # Should have header row and data rows
            lines = csv_content.strip().split('\n')
            assert len(lines) >= 2, "CSV should have header and at least one data row"
            
            # Check for expected columns
            header = lines[0]
            expected_columns = ['record_type', 'id_str', 'created_at', 'text']
            for col in expected_columns:
                assert col in header, f"CSV should have '{col}' column"
            
            print(f"✓ CSV file is valid ({len(lines)-1} data rows)")
            
            # Verify HTML report content
            html_filename = html_reports[0]
            html_content = zip_file.read(html_filename).decode('utf-8')
            
            assert '<!DOCTYPE html>' in html_content, "HTML report should be valid HTML"
            assert 'Twitter Archive Analysis Report' in html_content, "HTML should have title"
            print("✓ HTML report is valid")
            
            # Verify Markdown report content
            md_filename = md_reports[0]
            md_content = zip_file.read(md_filename).decode('utf-8')
            
            assert '# Twitter Archive Analysis Report' in md_content, "MD should have title"
            assert '## Summary' in md_content, "MD should have summary section"
            print("✓ Markdown report is valid")
    
    print("-" * 70)
    return True


def test_download_with_multiple_file_types():
    """Test download with multiple file types (tweets, deleted tweets, notes)."""
    print("\ntest_download_with_multiple_file_types:")
    print("-" * 70)
    
    with app.test_client() as client:
        # Upload multiple file types
        test_dir = Path(__file__).parent
        test_files = [
            "mock_tweets.js",
            "mock_deleted_tweets.js",
            "mock_note_tweets.js"
        ]
        
        file_storages = []
        for filename in test_files:
            filepath = test_dir / filename
            with open(filepath, "rb") as f:
                file_content = f.read()
            
            file_storages.append(FileStorage(
                stream=io.BytesIO(file_content),
                filename=filename,
                content_type="application/javascript"
            ))
        
        # Upload files
        response = client.post(
            "/upload",
            data={"files": file_storages},
            content_type="multipart/form-data",
            follow_redirects=False
        )
        
        assert response.status_code == 302, "Upload should redirect"
        print(f"✓ Uploaded {len(test_files)} files successfully")
        
        # Download the ZIP
        response = client.get("/download")
        assert response.status_code == 200, "Download should succeed"
        
        # Parse the ZIP
        zip_data = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            file_list = zip_file.namelist()
            csv_files = [f for f in file_list if f.endswith('.csv')]
            
            print(f"✓ ZIP contains {len(csv_files)} CSV files:")
            for csv_file in sorted(csv_files):
                print(f"  - {csv_file}")
            
            # Should have tweet, deleted_tweet, and note CSV files
            assert any('tweet_' in f for f in csv_files), "Should have tweet CSV"
            assert any('deleted_tweet_' in f for f in csv_files), "Should have deleted_tweet CSV"
            assert any('note_' in f for f in csv_files), "Should have note CSV"
            print("✓ Found per-type CSV files for all record types")
    
    print("-" * 70)
    return True


def test_download_png_generation():
    """Test that PNG images are generated when kaleido is available."""
    print("\ntest_download_png_generation:")
    print("-" * 70)
    
    # Check if kaleido is available
    try:
        import kaleido
        kaleido_available = True
        print("✓ kaleido is available")
    except ImportError:
        kaleido_available = False
        print("  kaleido not available, skipping PNG generation test")
        return True
    
    with app.test_client() as client:
        # Upload a file
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
        
        # Download the ZIP
        response = client.get("/download")
        
        # Parse the ZIP
        zip_data = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            png_files = [f for f in zip_file.namelist() if f.endswith('.png')]
            
            if kaleido_available:
                assert len(png_files) > 0, "Should have PNG images when kaleido is available"
                print(f"✓ Generated {len(png_files)} PNG images:")
                for png_file in sorted(png_files):
                    file_info = zip_file.getinfo(png_file)
                    print(f"  - {png_file} ({file_info.file_size:,} bytes)")
                
                # Verify PNG files are valid by checking magic bytes
                for png_file in png_files:
                    png_data = zip_file.read(png_file)
                    # PNG files start with specific magic bytes
                    assert png_data[:8] == b'\x89PNG\r\n\x1a\n', f"{png_file} should be valid PNG"
                
                print("✓ All PNG files are valid")
            else:
                print(f"  Found {len(png_files)} PNG images (kaleido may have failed)")
    
    print("-" * 70)
    return True


def main():
    """Run all webapp tests."""
    print("=" * 70)
    print("Twitter Archive Analyzer - Webapp Test Suite")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print("=" * 70)
    
    all_passed = True
    
    tests = [
        test_download_endpoint_requires_session,
        test_download_generates_zip,
        test_download_with_multiple_file_types,
        test_download_png_generation,
    ]
    
    for test in tests:
        try:
            if not test():
                all_passed = False
                print(f"✗ {test.__name__} FAILED")
        except AssertionError as e:
            all_passed = False
            print(f"✗ {test.__name__} FAILED: {e}")
        except Exception as e:
            all_passed = False
            print(f"✗ {test.__name__} ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    if all_passed:
        print("SUCCESS: All webapp tests passed!")
    else:
        print("FAILURE: Some tests failed.")
    print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
