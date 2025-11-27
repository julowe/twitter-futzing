"""Twitter Archive Analyzer - Core module for parsing and analyzing Twitter archives."""

from twitter_analyzer.core import (
    detect_and_decode,
    strip_js_wrapper,
    parse_twitter_export_bytes,
    parse_twitter_export_file,
    html_strip,
    safe_get,
    normalize_items,
    coerce_types,
    summarize,
    process_files,
)

__version__ = "1.0.0"

__all__ = [
    "detect_and_decode",
    "strip_js_wrapper",
    "parse_twitter_export_bytes",
    "parse_twitter_export_file",
    "html_strip",
    "safe_get",
    "normalize_items",
    "coerce_types",
    "summarize",
    "process_files",
]
