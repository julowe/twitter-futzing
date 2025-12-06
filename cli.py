#!/usr/bin/env python3
"""Twitter Archive Analyzer CLI.

Command-line interface for analyzing Twitter archive exports.
Outputs CSV files, visualizations, and reports to the exports/ directory.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from twitter_analyzer.core import (
    parse_twitter_export_file,
    normalize_items,
    coerce_types,
    summarize,
    process_files,
)
from twitter_analyzer.visualizations import generate_all_charts, save_charts_as_images


def load_files_from_paths(paths: List[str]) -> List[Tuple[str, bytes]]:
    """Load file contents from a list of paths.

    Args:
        paths: List of file paths to load.

    Returns:
        List of (filename, bytes) tuples.
    """
    files = []
    for path in paths:
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"Warning: File not found: {path}", file=sys.stderr)
            continue
        if not path_obj.suffix.lower() in (".js", ".json"):
            print(f"Warning: Skipping non-.js/.json file: {path}", file=sys.stderr)
            continue
        with open(path, "rb") as f:
            files.append((path_obj.name, f.read()))
    return files


def generate_markdown_report(
    df: pd.DataFrame,
    summary: str,
    image_files: List[str],
    timestamp: str,
) -> str:
    """Generate a Markdown report with analysis results.

    Args:
        df: DataFrame with Twitter data.
        summary: Summary text.
        image_files: List of image file paths.
        timestamp: Timestamp string for the report.

    Returns:
        Markdown string.
    """
    lines = [
        "# Twitter Archive Analysis Report",
        "",
        f"Generated: {timestamp}",
        "",
        "## Summary",
        "",
        "```",
        summary,
        "```",
        "",
    ]

    # Add record type breakdown table
    if "record_type" in df.columns:
        lines.extend(
            [
                "## Record Types",
                "",
                "| Type | Count |",
                "|------|-------|",
            ]
        )
        for typ, count in df["record_type"].value_counts().items():
            lines.append(f"| {typ} | {count:,} |")
        lines.append("")

    # Add top tweets by favorites
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        top_tweets = (
            df[df["record_type"] == "tweet"]
            .nlargest(5, "favorite_count")[
                ["id_str", "text", "favorite_count", "retweet_count", "created_at"]
            ]
            .copy()
        )
        if not top_tweets.empty:
            lines.extend(
                [
                    "## Top Tweets by Favorites",
                    "",
                    "| Tweet ID | Favorites | Retweets | Date |",
                    "|----------|-----------|----------|------|",
                ]
            )
            for _, row in top_tweets.iterrows():
                date_str = (
                    row["created_at"].strftime("%Y-%m-%d")
                    if pd.notna(row["created_at"])
                    else "N/A"
                )
                lines.append(
                    f"| {row['id_str']} | {int(row['favorite_count']):,} | {int(row['retweet_count'] or 0):,} | {date_str} |"
                )
            lines.append("")

    # Add visualization references
    if image_files:
        lines.extend(
            [
                "## Visualizations",
                "",
            ]
        )
        for img_path in image_files:
            img_name = os.path.basename(img_path)
            title = img_name.replace("_", " ").replace(".png", "").title()
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"![{title}]({img_name})")
            lines.append("")

    return "\n".join(lines)


def generate_html_report(
    df: pd.DataFrame,
    summary: str,
    charts_html: List[str],
    timestamp: str,
) -> str:
    """Generate an HTML report with analysis results and interactive charts.

    Args:
        df: DataFrame with Twitter data.
        summary: Summary text.
        charts_html: List of chart HTML strings.
        timestamp: Timestamp string for the report.

    Returns:
        HTML string.
    """
    charts_section = "\n".join(
        f'<div class="chart-container">{html}</div>' for html in charts_html if html
    )

    # Build tables
    type_table = ""
    if "record_type" in df.columns:
        type_rows = "\n".join(
            f"<tr><td>{typ}</td><td>{count:,}</td></tr>"
            for typ, count in df["record_type"].value_counts().items()
        )
        type_table = f"""
        <h2>Record Types</h2>
        <table>
            <thead><tr><th>Type</th><th>Count</th></tr></thead>
            <tbody>{type_rows}</tbody>
        </table>
        """

    top_tweets_table = ""
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        top_tweets = (
            df[df["record_type"] == "tweet"]
            .nlargest(10, "favorite_count")[
                ["id_str", "text", "favorite_count", "retweet_count", "created_at"]
            ]
            .copy()
        )
        if not top_tweets.empty:
            rows = []
            for _, row in top_tweets.iterrows():
                date_str = (
                    row["created_at"].strftime("%Y-%m-%d")
                    if pd.notna(row["created_at"])
                    else "N/A"
                )
                text_preview = (row["text"] or "")[:100] + (
                    "..." if len(row["text"] or "") > 100 else ""
                )
                rows.append(
                    f"<tr><td>{row['id_str']}</td><td>{text_preview}</td>"
                    f"<td>{int(row['favorite_count']):,}</td>"
                    f"<td>{int(row['retweet_count'] or 0):,}</td>"
                    f"<td>{date_str}</td></tr>"
                )
            top_tweets_table = f"""
            <h2>Top Tweets by Favorites</h2>
            <table>
                <thead><tr><th>ID</th><th>Text</th><th>Favorites</th><th>Retweets</th><th>Date</th></tr></thead>
                <tbody>{"".join(rows)}</tbody>
            </table>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twitter Archive Analysis Report</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1, h2 {{
            color: #1da1f2;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            white-space: pre-line;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #1da1f2;
            color: white;
        }}
        tr:hover {{
            background: #f0f8ff;
        }}
        .timestamp {{
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>Twitter Archive Analysis Report</h1>
    <p class="timestamp">Generated: {timestamp}</p>
    
    <h2>Summary</h2>
    <div class="summary">{summary}</div>
    
    {type_table}
    
    {top_tweets_table}
    
    <h2>Visualizations</h2>
    {charts_section}
</body>
</html>"""
    return html


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Twitter archive exports and generate reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s tweets.js
  %(prog)s tweets.js deleted-tweets.js note-tweets.js
  %(prog)s --output-dir ./my_exports tweets.js
  %(prog)s --filter-and blue --filter-and green --filter-or red tweets.js
  %(prog)s --filter-datetime-after "2023-01-01T00:00" tweets.js
        """,
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more .js or .json Twitter export files",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="exports",
        help="Output directory for exports (default: exports)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip generating image files (faster)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output",
    )
    parser.add_argument(
        "--filter-and",
        action="append",
        dest="filter_and",
        metavar="WORD",
        help="Filter tweets containing this word (all --filter-and words must be present). Can be specified multiple times.",
    )
    parser.add_argument(
        "--filter-or",
        action="append",
        dest="filter_or",
        metavar="WORD",
        help="Filter tweets containing this word (at least one --filter-or word must be present). Can be specified multiple times.",
    )
    parser.add_argument(
        "--filter-datetime-after",
        dest="datetime_after",
        metavar="DATETIME",
        help='Filter tweets created on or after this datetime (ISO format without seconds, e.g., "2023-01-01T12:30"). If no timezone specified, local timezone is used.',
    )
    parser.add_argument(
        "--filter-datetime-before",
        dest="datetime_before",
        metavar="DATETIME",
        help='Filter tweets created on or before this datetime (ISO format without seconds, e.g., "2023-12-31T23:59"). If no timezone specified, local timezone is used.',
    )

    args = parser.parse_args()

    # Load files
    print(f"Loading {len(args.files)} file(s)...")
    files = load_files_from_paths(args.files)

    if not files:
        print("Error: No valid files to process.", file=sys.stderr)
        sys.exit(1)

    # Process files
    print("Processing files...")
    df, errors = process_files(files)

    if errors:
        print("\nWarnings:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    if df.empty:
        print("Error: No records were extracted from the files.", file=sys.stderr)
        sys.exit(1)

    print(f"Processed {len(df):,} records from {len(files)} file(s)")

    # Apply filters
    filter_applied = False
    datetime_after = None
    datetime_before = None

    if args.datetime_after:
        try:
            # Parse datetime and make timezone-aware
            dt = pd.to_datetime(args.datetime_after)
            # If no timezone info, use local timezone
            if dt.tzinfo is None:
                dt = dt.tz_localize(datetime.now().astimezone().tzinfo)
            datetime_after = dt.to_pydatetime()
            filter_applied = True
        except Exception as e:
            print(f"Error parsing --filter-datetime-after: {e}", file=sys.stderr)
            sys.exit(1)

    if args.datetime_before:
        try:
            # Parse datetime and make timezone-aware
            dt = pd.to_datetime(args.datetime_before)
            # If no timezone info, use local timezone
            if dt.tzinfo is None:
                dt = dt.tz_localize(datetime.now().astimezone().tzinfo)
            datetime_before = dt.to_pydatetime()
            filter_applied = True
        except Exception as e:
            print(f"Error parsing --filter-datetime-before: {e}", file=sys.stderr)
            sys.exit(1)

    if args.filter_and or args.filter_or:
        filter_applied = True

    if filter_applied:
        from twitter_analyzer.core import filter_dataframe
        
        original_count = len(df)
        df = filter_dataframe(
            df,
            filter_and=args.filter_and,
            filter_or=args.filter_or,
            datetime_after=datetime_after,
            datetime_before=datetime_before,
        )
        
        if df.empty:
            print("Error: No records match the specified filters.", file=sys.stderr)
            sys.exit(1)
        
        print(f"Applied filters: {len(df):,} of {original_count:,} records match")
        
        if args.verbose:
            if args.filter_and:
                print(f"  - AND filter: {', '.join(args.filter_and)}")
            if args.filter_or:
                print(f"  - OR filter: {', '.join(args.filter_or)}")
            if datetime_after:
                print(f"  - After: {datetime_after}")
            if datetime_before:
                print(f"  - Before: {datetime_before}")

    # Generate summary
    summary = summarize(df)
    if args.verbose:
        print("\n" + summary)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Export CSV files
    print(f"\nExporting to {output_dir}/...")

    # All records
    csv_all = output_dir / f"twitter_records_{timestamp}.csv"
    df.to_csv(csv_all, index=False)
    print(f"  - {csv_all}")

    # Per type
    for typ in sorted(df["record_type"].dropna().unique()):
        df_sub = df[df["record_type"] == typ]
        csv_path = output_dir / f"{typ}_{timestamp}.csv"
        df_sub.to_csv(csv_path, index=False)
        print(f"  - {csv_path}")

    # Generate charts
    print("\nGenerating visualizations...")
    charts = generate_all_charts(df)

    image_files = []
    if not args.no_images:
        try:
            image_files = save_charts_as_images(charts, str(output_dir), format="png")
            for img in image_files:
                print(f"  - {img}")
        except ImportError as e:
            print(f"  Warning: {e}", file=sys.stderr)
            print("  Skipping image generation. Interactive charts will still be available in the HTML report.", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: Failed to save images: {e}", file=sys.stderr)
            print("  Skipping image generation. Interactive charts will still be available in the HTML report.", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()

    # Generate reports
    print("\nGenerating reports...")

    # Markdown report
    md_report = generate_markdown_report(df, summary, image_files, timestamp)
    md_path = output_dir / f"report_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"  - {md_path}")

    # HTML report with interactive charts
    from twitter_analyzer.visualizations import get_chart_html

    charts_html = []
    for name, fig in charts.items():
        if fig is not None:
            charts_html.append(get_chart_html(fig, include_plotlyjs=(len(charts_html) == 0)))

    html_report = generate_html_report(df, summary, charts_html, timestamp)
    html_path = output_dir / f"report_{timestamp}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"  - {html_path}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
