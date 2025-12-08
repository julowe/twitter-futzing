
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import generate_markdown_report, generate_html_report

class TestReporting(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "record_type": ["tweet", "tweet", "note"],
            "favorite_count": [10, 20, 5],
            "retweet_count": [1, 2, 0],
            "text": ["tweet1", "tweet2", "note1"],
            "created_at": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
            "id_str": ["1", "2", "3"]
        })
        self.summary = "Total records: 3"
        self.timestamp = "2023-01-01 12:00:00"

    def test_generate_markdown_report(self):
        """Test Markdown report generation."""
        image_files = ["chart1.png"]
        
        report = generate_markdown_report(
            self.df, 
            self.summary, 
            image_files, 
            self.timestamp
        )
        
        self.assertIn("# Twitter Archive Analysis Report", report)
        self.assertIn(self.timestamp, report)
        self.assertIn("Total records: 3", report)
        self.assertIn("chart1.png", report)
        self.assertIn("| tweet | 2 |", report)

    def test_generate_html_report(self):
        """Test HTML report generation."""
        charts_html = ["<div>chart</div>"]
        
        report = generate_html_report(
            self.df,
            self.summary,
            charts_html,
            self.timestamp
        )
        
        self.assertIn("<!DOCTYPE html>", report)
        self.assertIn(self.timestamp, report)
        self.assertIn("Total records: 3", report)
        self.assertIn("<div>chart</div>", report)
        self.assertIn("<td>tweet</td><td>2</td>", report)

if __name__ == "__main__":
    unittest.main()
