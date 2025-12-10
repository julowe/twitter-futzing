#!/usr/bin/env python3
"""Tests for the CLI functionality."""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import main, load_files_from_paths
from twitter_analyzer.visualizations import save_charts_as_images, generate_all_charts
from twitter_analyzer.core import process_files


def test_load_files_from_paths():
    """Test loading files from paths."""
    test_dir = Path(__file__).parent
    test_files = ["mock_tweets.js", "mock_deleted_tweets.js"]
    paths = [str(test_dir / f) for f in test_files]
    
    files = load_files_from_paths(paths)
    
    assert len(files) == 2, f"Expected 2 files, got {len(files)}"
    assert all(isinstance(f[0], str) for f in files), "File names should be strings"
    assert all(isinstance(f[1], bytes) for f in files), "File contents should be bytes"
    print("✓ test_load_files_from_paths passed")


def test_load_files_missing_file():
    """Test loading files with a missing file."""
    test_dir = Path(__file__).parent
    paths = [str(test_dir / "mock_tweets.js"), "/nonexistent/file.js"]
    
    files = load_files_from_paths(paths)
    
    # Should only load the valid file
    assert len(files) == 1, f"Expected 1 file, got {len(files)}"
    print("✓ test_load_files_missing_file passed")


def test_load_files_wrong_extension():
    """Test loading files with wrong extension."""
    test_dir = Path(__file__).parent
    paths = [str(test_dir / "README.md")]
    
    files = load_files_from_paths(paths)
    
    # Should skip non-.js/.json files
    assert len(files) == 0, f"Expected 0 files, got {len(files)}"
    print("✓ test_load_files_wrong_extension passed")


def test_cli_image_generation():
    """Test that CLI generates image files correctly."""
    test_dir = Path(__file__).parent
    test_file = test_dir / "mock_tweets.js"
    
    # Load and process test data
    files = load_files_from_paths([str(test_file)])
    assert len(files) > 0, "Should load at least one file"
    
    df, errors = process_files(files)
    assert not df.empty, "DataFrame should not be empty"
    
    # Generate charts
    charts = generate_all_charts(df)
    assert len(charts) > 0, "Should generate at least one chart"
    
    # Save images to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            image_files = save_charts_as_images(charts, tmpdir, format="png")
            
            # Verify images were created
            assert len(image_files) > 0, "Should create at least one image file"
            
            # Verify all image files exist and have content
            for img_path in image_files:
                assert os.path.exists(img_path), f"Image file not found: {img_path}"
                assert os.path.getsize(img_path) > 0, f"Image file is empty: {img_path}"
                assert img_path.endswith(".png"), f"Image file should be .png: {img_path}"
            
            print(f"✓ test_cli_image_generation passed - Created {len(image_files)} images")
        except ImportError as e:
            print(f"⚠ test_cli_image_generation skipped - kaleido not installed: {e}")
            return


def test_cli_multiple_files():
    """Test CLI with multiple input files."""
    test_dir = Path(__file__).parent
    test_files = [
        test_dir / "mock_tweets.js",
        test_dir / "mock_deleted_tweets.js",
        test_dir / "mock_note_tweets.js",
    ]
    
    files = load_files_from_paths([str(f) for f in test_files])
    assert len(files) == 3, f"Expected 3 files, got {len(files)}"
    
    df, errors = process_files(files)
    assert not df.empty, "DataFrame should not be empty"
    
    # Generate charts
    charts = generate_all_charts(df)
    
    # Save images
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            image_files = save_charts_as_images(charts, tmpdir, format="png")
            assert len(image_files) > 0, "Should create at least one image file"
            print(f"✓ test_cli_multiple_files passed - Created {len(image_files)} images from {len(files)} files")
        except ImportError as e:
            print(f"⚠ test_cli_multiple_files skipped - kaleido not installed: {e}")
            return


def test_cli_end_to_end():
    """Test the complete CLI workflow end-to-end."""
    test_dir = Path(__file__).parent
    test_file = test_dir / "mock_tweets.js"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock command line arguments
        sys.argv = [
            "cli.py",
            str(test_file),
            "--output-dir", tmpdir,
        ]
        
        # Run the CLI
        result = main()
        
        # Verify successful execution
        assert result == 0, f"CLI should return 0, got {result}"
        
        # Verify output files were created
        output_files = list(Path(tmpdir).glob("*"))
        assert len(output_files) > 0, "Should create output files"
        
        # Check for CSV files
        csv_files = list(Path(tmpdir).glob("*.csv"))
        assert len(csv_files) > 0, "Should create at least one CSV file"
        
        # Check for report files
        html_files = list(Path(tmpdir).glob("*.html"))
        md_files = list(Path(tmpdir).glob("*.md"))
        assert len(html_files) > 0, "Should create HTML report"
        assert len(md_files) > 0, "Should create Markdown report"
        
        # Check for image files (if kaleido is installed)
        png_files = list(Path(tmpdir).glob("*.png"))
        if png_files:
            print(f"✓ test_cli_end_to_end passed - Created {len(png_files)} images, {len(csv_files)} CSVs, and reports")
        else:
            print(f"⚠ test_cli_end_to_end passed (no images) - Created {len(csv_files)} CSVs and reports")


def test_cli_no_images_flag():
    """Test CLI with --no-images flag."""
    test_dir = Path(__file__).parent
    test_file = test_dir / "mock_tweets.js"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock command line arguments
        sys.argv = [
            "cli.py",
            str(test_file),
            "--output-dir", tmpdir,
            "--no-images",
        ]
        
        # Run the CLI
        result = main()
        
        # Verify successful execution
        assert result == 0, f"CLI should return 0, got {result}"
        
        # Verify no PNG files were created
        png_files = list(Path(tmpdir).glob("*.png"))
        assert len(png_files) == 0, f"Should not create images with --no-images flag, but found {len(png_files)}"
        
        # Verify other files were still created
        csv_files = list(Path(tmpdir).glob("*.csv"))
        html_files = list(Path(tmpdir).glob("*.html"))
        assert len(csv_files) > 0, "Should still create CSV files"
        assert len(html_files) > 0, "Should still create HTML report"
        
        print("✓ test_cli_no_images_flag passed - No images created with --no-images flag")


def test_visualizations_all_chart_types():
    """Test that all chart types can be generated and saved."""
    test_dir = Path(__file__).parent
    
    # Load multiple files to get varied data
    files = load_files_from_paths([
        str(test_dir / "mock_tweets.js"),
        str(test_dir / "mock_deleted_tweets.js"),
        str(test_dir / "mock_note_tweets.js"),
    ])
    
    df, _ = process_files(files)
    charts = generate_all_charts(df)
    
    # Expected chart types
    expected_charts = [
        "monthly_counts",
        "text_length",
        "top_languages",
        "top_sources",
        "hourly_activity",
        "day_of_week",
    ]
    
    # Verify all chart types are present
    for chart_name in expected_charts:
        assert chart_name in charts, f"Missing chart: {chart_name}"
    
    # Count non-None charts
    non_none_charts = {k: v for k, v in charts.items() if v is not None}
    assert len(non_none_charts) > 0, "Should generate at least one chart"
    
    # Try to save them
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            image_files = save_charts_as_images(charts, tmpdir, format="png")
            assert len(image_files) == len(non_none_charts), \
                f"Should save {len(non_none_charts)} images, got {len(image_files)}"
            print(f"✓ test_visualizations_all_chart_types passed - Generated {len(non_none_charts)} chart types")
        except ImportError:
            print(f"⚠ test_visualizations_all_chart_types skipped - kaleido not installed")


def test_csv_export_separation():
    """Test that both archive-only and analysis CSV files are created."""
    test_dir = Path(__file__).parent
    test_file = test_dir / "mock_tweets.js"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock command line arguments
        sys.argv = [
            "cli.py",
            str(test_file),
            "--output-dir", tmpdir,
            "--no-images",  # Skip images for faster testing
        ]
        
        # Run the CLI
        result = main()
        
        # Verify successful execution
        assert result == 0, f"CLI should return 0, got {result}"
        
        # Check for CSV files
        csv_files = list(Path(tmpdir).glob("*.csv"))
        archive_csvs = [f for f in csv_files if "_analysis" not in f.name]
        analysis_csvs = [f for f in csv_files if "_analysis" in f.name]
        
        # Should have at least one archive CSV
        assert len(archive_csvs) > 0, f"Should create at least one archive CSV file, found {len(archive_csvs)}"
        
        # Should have at least one analysis CSV (since sentiment analysis runs by default)
        assert len(analysis_csvs) > 0, f"Should create at least one analysis CSV file, found {len(analysis_csvs)}"
        
        # Verify archive CSVs don't have analysis columns
        import pandas as pd
        from twitter_analyzer.core import ANALYSIS_COLUMNS
        
        for csv_file in archive_csvs:
            df = pd.read_csv(csv_file)
            analysis_cols_found = [col for col in df.columns if col in ANALYSIS_COLUMNS]
            assert len(analysis_cols_found) == 0, \
                f"Archive CSV {csv_file.name} should not have analysis columns, but found: {analysis_cols_found}"
        
        # Verify analysis CSVs have analysis columns
        for csv_file in analysis_csvs:
            df = pd.read_csv(csv_file)
            analysis_cols_found = [col for col in df.columns if col in ANALYSIS_COLUMNS]
            assert len(analysis_cols_found) > 0, \
                f"Analysis CSV {csv_file.name} should have analysis columns, but found none"
        
        print(f"✓ test_csv_export_separation passed - Created {len(archive_csvs)} archive CSVs and {len(analysis_csvs)} analysis CSVs")


def main_test():
    """Run all tests."""
    print("=" * 70)
    print("CLI Tests")
    print("=" * 70)
    
    tests = [
        test_load_files_from_paths,
        test_load_files_missing_file,
        test_load_files_wrong_extension,
        test_cli_image_generation,
        test_cli_multiple_files,
        test_cli_end_to_end,
        test_cli_no_images_flag,
        test_visualizations_all_chart_types,
        test_csv_export_separation,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed.append(test.__name__)
    
    print("=" * 70)
    if failed:
        print(f"FAILED: {len(failed)} test(s) failed:")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print(f"SUCCESS: All {len(tests)} tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main_test())
