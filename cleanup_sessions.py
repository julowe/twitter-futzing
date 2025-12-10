#!/usr/bin/env python3
"""Cleanup script to remove old session data files.

This script removes session data files that are older than a specified age
(default: 30 days). It's designed to be run periodically via cron in Docker.
"""

import os
import sys
import time
from pathlib import Path
from typing import Tuple
import tempfile

# Default age threshold in seconds (30 days)
DEFAULT_MAX_AGE_DAYS = 30
MAX_AGE_SECONDS = DEFAULT_MAX_AGE_DAYS * 24 * 60 * 60


def cleanup_old_sessions(session_dir: Path, max_age_seconds: int = MAX_AGE_SECONDS) -> Tuple[int, int]:
    """Remove session files older than max_age_seconds.
    
    Args:
        session_dir: Directory containing session files
        max_age_seconds: Maximum age in seconds before deletion
        
    Returns:
        Tuple of (files_removed, errors_encountered)
    """
    if not session_dir.exists():
        print(f"Session directory does not exist: {session_dir}")
        return 0, 0
    
    current_time = time.time()
    files_removed = 0
    errors = 0
    
    # Iterate through all .pkl files in the session directory
    for session_file in session_dir.glob("*.pkl"):
        try:
            # Get file modification time
            file_mtime = session_file.stat().st_mtime
            file_age = current_time - file_mtime
            
            # Remove if older than threshold
            if file_age > max_age_seconds:
                session_file.unlink()
                files_removed += 1
                print(f"Removed: {session_file.name} (age: {file_age / 86400:.1f} days)")
        except OSError as e:
            print(f"Error removing {session_file.name}: {e}", file=sys.stderr)
            errors += 1
    
    return files_removed, errors


def main():
    """Main entry point for the cleanup script."""
    # Use the same session directory as the webapp
    session_dir = Path(tempfile.gettempdir()) / "twitter_analyzer_sessions"
    
    print(f"Starting session cleanup at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Session directory: {session_dir}")
    print(f"Max age: {DEFAULT_MAX_AGE_DAYS} days")
    
    files_removed, errors = cleanup_old_sessions(session_dir)
    
    print(f"Cleanup complete: {files_removed} file(s) removed, {errors} error(s)")
    
    # Exit with error code if there were errors
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
