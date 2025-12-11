"""Twitter Archive Analyzer Web Application.

Flask-based web application for uploading and analyzing Twitter archive exports.
Provides interactive visualizations and data tables.
"""

import io
import os
import pickle
import re
import secrets
import tempfile
import warnings
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import (
    Flask,
    flash,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
    jsonify,
    send_file,
)
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

import pandas as pd

from cli import generate_html_report, generate_markdown_report
from twitter_analyzer.core import (
    parse_twitter_export_bytes,
    normalize_items,
    coerce_types,
    summarize,
    process_files,
    get_archive_columns,
    get_analysis_columns,
)
from twitter_analyzer.visualizations import generate_all_charts, get_chart_html
from twitter_analyzer.analysis import analyze_sentiment, generate_wordcloud


app = Flask(__name__)

# Secret key validation pattern - 64 hex chars from secrets.token_hex(32)
SECRET_KEY_PATTERN = r'[a-f0-9]{64}'


def read_and_validate_secret_key(file_path: Path) -> Optional[str]:
    """Read and validate secret key from file.
    
    Args:
        file_path: Path to the secret key file
        
    Returns:
        Valid secret key string or None if invalid/not found
    """
    try:
        with open(file_path, 'r') as f:
            key = f.read().strip()
        
        # Validate the key format
        if re.fullmatch(SECRET_KEY_PATTERN, key):
            return key
    except (OSError, IOError):
        pass
    
    return None


# Secret key configuration - in production, always set SECRET_KEY environment variable
# to a consistent value to preserve sessions across restarts and workers
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    # Use a persistent secret key file for multi-worker consistency
    # This ensures all gunicorn workers use the same secret key
    # Note: For better security, set SECRET_KEY environment variable explicitly
    secret_key_file = Path(tempfile.gettempdir()) / "twitter_analyzer_secret.key"
    
    try:
        # Try to read existing key
        _secret_key = read_and_validate_secret_key(secret_key_file)
        
        if not _secret_key:
            # Generate and save new secret key atomically
            warnings.warn(
                "SECRET_KEY not set. Generating persistent key for multi-worker support. "
                "For production, set SECRET_KEY environment variable for better security.",
                RuntimeWarning
            )
            _secret_key = secrets.token_hex(32)
            
            # Atomic write: open with exclusive creation and restrictive permissions
            # Use try-finally to ensure file descriptor cleanup
            fd = None
            try:
                fd = os.open(str(secret_key_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                # Transfer fd ownership to fdopen
                with os.fdopen(fd, 'w') as f:
                    fd = None  # fd now owned by file object, will be closed by context manager
                    f.write(_secret_key)
            finally:
                # Ensure fd is closed if fdopen failed
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
    
    except FileExistsError:
        # File was created between check and creation (race condition)
        # Read and validate the existing file
        _secret_key = read_and_validate_secret_key(secret_key_file)
        if not _secret_key:
            raise ValueError("Invalid secret key format in persistent key file")
    
    except (OSError, IOError) as e:
        # Fall back to runtime-only key if file operations fail
        warnings.warn(
            "Failed to access persistent secret key file. Using runtime-only key. "
            "Sessions will not persist across worker restarts.",
            RuntimeWarning
        )
        _secret_key = secrets.token_hex(32)

app.secret_key = _secret_key

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max upload

# Session ID configuration
# Session IDs are generated using secrets.token_hex(SESSION_ID_BYTES)
# which produces SESSION_ID_BYTES * 2 hex characters
SESSION_ID_BYTES = 16  # Results in 32-character hex string

# Session data storage directory
# Uses a shared temporary directory that works across gunicorn workers
# Security note: pickle is used for efficient DataFrame serialization.
# This is safe because:
# 1. Session IDs are cryptographically random (secrets.token_hex)
# 2. Session IDs are strictly validated (32-char hex only)
# 3. Directory has restrictive permissions (0o700, owner-only)
# 4. Path traversal is prevented via validation
# 5. Only application-generated data (DataFrames) is pickled, not user input
# 6. Pickle files are never directly accessible to users
SESSION_DATA_DIR = Path(tempfile.gettempdir()) / "twitter_analyzer_sessions"
SESSION_DATA_DIR.mkdir(mode=0o700, exist_ok=True)


def is_valid_session_id(session_id: str) -> bool:
    """Validate session ID to prevent directory traversal attacks."""
    # Only allow hexadecimal characters (from secrets.token_hex), 32 chars length
    expected_length = SESSION_ID_BYTES * 2
    return bool(re.match(rf'^[a-f0-9]{{{expected_length}}}$', session_id))


def save_session_data(session_id: str, data: Dict) -> None:
    """Save session data to disk for multi-worker compatibility.
    
    Security: Uses pickle for DataFrame serialization. Session IDs are validated
    and directory has restrictive permissions to prevent unauthorized access.
    """
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session ID")
    
    file_path = SESSION_DATA_DIR / f"{session_id}.pkl"
    with open(file_path, 'wb') as f:
        pickle.dump(data, f)


def load_session_data(session_id: str) -> Optional[Dict]:
    """Load session data from disk.
    
    Security: Session ID is validated before use. Path verification prevents
    directory traversal. Only loads files from protected session directory.
    """
    if not is_valid_session_id(session_id):
        return None
    
    file_path = SESSION_DATA_DIR / f"{session_id}.pkl"
    if not file_path.exists():
        return None
    
    # Verify the file is within our session directory to prevent traversal
    try:
        if not file_path.resolve().parent.samefile(SESSION_DATA_DIR):
            return None
    except (OSError, ValueError):
        return None
    
    try:
        with open(file_path, 'rb') as f:
            return pickle.load(f)
    except (pickle.PickleError, EOFError, OSError):
        # Handle expected errors: corrupted pickle, truncated file, I/O errors
        return None


def delete_session_data(session_id: str) -> None:
    """Delete session data file."""
    if not is_valid_session_id(session_id):
        return
    
    file_path = SESSION_DATA_DIR / f"{session_id}.pkl"
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass


ALLOWED_EXTENSIONS = {".js", ".json"}


def allowed_file(filename: str) -> bool:
    """Check if a file has an allowed extension."""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


# HTML Templates
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Twitter Archive Analyzer</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: rgba(255,255,255,0.95);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        header .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
        }
        header h1 {
            margin: 0;
            color: #1da1f2;
            font-size: 1.8em;
            flex: 1;
        }
        header .header-button {
            flex-shrink: 0;
        }
        header p {
            margin: 10px 0 0;
            color: #666;
        }
        header .header-stats {
            margin: 10px 0 0;
            color: #333;
            font-size: 0.95em;
        }
        .card {
            background: rgba(255,255,255,0.95);
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .card h2 {
            margin-top: 0;
            color: #333;
        }
        .upload-zone {
            border: 3px dashed #1da1f2;
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .upload-zone:hover, .upload-zone.dragover {
            background: #e8f5fe;
            border-color: #0d8ecf;
        }
        .upload-zone input[type="file"] {
            display: none;
        }
        .upload-zone label {
            cursor: pointer;
            display: block;
        }
        .upload-zone .icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #1da1f2;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            text-decoration: none;
            transition: background 0.3s ease;
        }
        .btn:hover {
            background: #0d8ecf;
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .btn-secondary {
            background: #6c757d;
        }
        .btn-secondary:hover {
            background: #545b62;
        }
        .file-list {
            margin: 20px 0;
            padding: 0;
            list-style: none;
        }
        .file-list li {
            padding: 10px 15px;
            background: #f8f9fa;
            border-radius: 6px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .file-list li .file-name {
            font-weight: 500;
        }
        .file-list li .file-size {
            color: #666;
            font-size: 0.9em;
        }
        .progress-container {
            margin: 20px 0;
            display: none;
        }
        .progress-bar {
            height: 24px;
            background: #e9ecef;
            border-radius: 12px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #1da1f2, #667eea);
            width: 0%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 500;
        }
        .progress-text {
            margin-top: 10px;
            text-align: center;
            color: #666;
        }
        .flash-messages {
            list-style: none;
            padding: 0;
            margin: 0 0 20px;
        }
        .flash-messages li {
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash-messages .error {
            background: #fee2e2;
            color: #dc2626;
        }
        .flash-messages .success {
            background: #d1fae5;
            color: #059669;
        }
        .flash-messages .info {
            background: #dbeafe;
            color: #2563eb;
        }
        .summary-box {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            white-space: pre-line;
            font-family: monospace;
            font-size: 14px;
            line-height: 1.6;
        }
        .chart-container {
            margin-bottom: 30px;
        }
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .data-table th, .data-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .data-table th {
            background: #1da1f2;
            color: white;
            position: sticky;
            top: 0;
        }
        .data-table tr:hover {
            background: #f0f8ff;
        }
        .data-table .text-cell {
            white-space: normal;
            word-wrap: break-word;
        }
        .count-badge {
            font-size: 0.7em;
            font-weight: normal;
            color: #666;
        }
        .table-container {
            max-height: calc(100vh - 500px);
            min-height: 300px;
            overflow-y: auto;
            border-radius: 8px;
            border: 1px solid #ddd;
        }
        .load-more-btn {
            margin-top: 15px;
            text-align: center;
        }
        .load-more-btn button {
            padding: 10px 20px;
            background: #1da1f2;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s ease;
        }
        .load-more-btn button:hover {
            background: #0d8ecf;
        }
        .load-more-btn button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #1da1f2, #667eea);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .stat-card .stat-label {
            opacity: 0.9;
        }
        .tabs {
            display: flex;
            border-bottom: 2px solid #e9ecef;
            margin-bottom: 20px;
        }
        .tab {
            padding: 12px 24px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: all 0.3s ease;
        }
        .tab:hover {
            background: #f8f9fa;
        }
        .tab.active {
            border-bottom-color: #1da1f2;
            color: #1da1f2;
            font-weight: 500;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .collapsible-section {
            margin-bottom: 20px;
        }
        .collapsible-header {
            background: #f8f9fa;
            padding: 12px 20px;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
            transition: background 0.3s ease;
        }
        .collapsible-header:hover {
            background: #e9ecef;
        }
        .collapsible-header .title {
            font-weight: 500;
            color: #333;
        }
        .collapsible-header .toggle-icon {
            transition: transform 0.3s ease;
            font-size: 1.2em;
        }
        .collapsible-header.expanded .toggle-icon {
            transform: rotate(180deg);
        }
        .collapsible-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }
        .collapsible-content.expanded {
            max-height: 2000px;
            overflow: visible;
        }
        .collapsible-content-inner {
            padding: 20px;
            background: #f8f9fa;
            border-radius: 0 0 8px 8px;
            margin-top: -8px;
        }
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            .card {
                padding: 20px;
            }
            .upload-zone {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-content">
                <h1>{{ header_title | default('🐦 Twitter Archive Analyzer') }}</h1>
                {% if header_button %}
                <div class="header-button">
                    {{ header_button | safe }}
                </div>
                {% endif %}
            </div>
            {% if header_description %}
            <p>{{ header_description }}</p>
            {% endif %}
            {% if header_stats %}
            <div class="header-stats">{{ header_stats | safe }}</div>
            {% endif %}
        </header>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <ul class="flash-messages">
                {% for category, message in messages %}
                    <li class="{{ category }}">{{ message }}</li>
                {% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
        {{ content | safe }}
    </div>
    {{ scripts | safe }}
</body>
</html>
"""

UPLOAD_CONTENT = """
<div class="card">
    <h2>Upload Files</h2>
    <form id="upload-form" action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
        <div class="upload-zone" id="drop-zone">
            <label for="files">
                <div class="icon">📁</div>
                <p><strong>Click to select files</strong> or drag and drop</p>
                <p style="color: #666; font-size: 0.9em;">Supports .js and .json files from Twitter data export</p>
            </label>
            <input type="file" name="files" id="files" multiple accept=".js,.json">
        </div>
        <ul class="file-list" id="file-list"></ul>
        <div class="progress-container" id="progress-container">
            <div class="progress-bar">
                <div class="progress-bar-fill" id="progress-fill">0%</div>
            </div>
            <p class="progress-text" id="progress-text">Uploading...</p>
        </div>
        <button type="submit" class="btn" id="submit-btn" disabled>Analyze Files</button>
    </form>
</div>

<div class="card">
    <h2>How to get your Twitter archive</h2>
    <ol>
        <li>Go to Twitter/X Settings → Your Account → Download an archive of your data</li>
        <li>Wait for Twitter to prepare your archive (may take a few days)</li>
        <li>Download and extract the archive</li>
        <li>Find the <code>data/</code> folder with files like <code>tweets.js</code>, <code>deleted-tweets.js</code>, etc.</li>
        <li>Upload those files here!</li>
    </ol>
</div>
"""

UPLOAD_SCRIPTS = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('files');
    const fileList = document.getElementById('file-list');
    const submitBtn = document.getElementById('submit-btn');
    const form = document.getElementById('upload-form');
    const progressContainer = document.getElementById('progress-container');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    let selectedFiles = [];
    
    // Drag and drop handlers
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });
    
    function handleFiles(files) {
        selectedFiles = Array.from(files).filter(f => 
            f.name.endsWith('.js') || f.name.endsWith('.json')
        );
        updateFileList();
    }
    
    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
    
    function updateFileList() {
        fileList.innerHTML = '';
        selectedFiles.forEach((file, i) => {
            const li = document.createElement('li');
            li.innerHTML = `
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatSize(file.size)}</span>
            `;
            fileList.appendChild(li);
        });
        submitBtn.disabled = selectedFiles.length === 0;
    }
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (selectedFiles.length === 0) return;
        
        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });
        
        submitBtn.disabled = true;
        progressContainer.style.display = 'block';
        
        try {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = percent + '%';
                    progressFill.textContent = percent + '%';
                    progressText.textContent = 'Uploading...';
                }
            });
            
            xhr.onload = function() {
                if (xhr.status === 200) {
                    progressText.textContent = 'Processing complete! Redirecting...';
                    window.location.href = xhr.responseURL;
                } else {
                    progressText.textContent = 'Error: ' + xhr.statusText;
                    submitBtn.disabled = false;
                }
            };
            
            xhr.onerror = function() {
                progressText.textContent = 'Upload failed. Please try again.';
                submitBtn.disabled = false;
            };
            
            xhr.open('POST', form.action);
            xhr.send(formData);
            
        } catch (err) {
            progressText.textContent = 'Error: ' + err.message;
            submitBtn.disabled = false;
        }
    });
});
</script>
"""

RESULTS_CONTENT = """
<div class="card">
    <div class="collapsible-section">
        <div class="collapsible-header" id="filters-toggle">
            <span class="title">Filters</span>
            <span class="toggle-icon">▼</span>
        </div>
        <div class="collapsible-content" id="filters-content">
            <div class="collapsible-content-inner">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="filter-datetime-after" style="display: block; margin-bottom: 5px; font-weight: 500;">Date After:</label>
                        <input type="datetime-local" id="filter-datetime-after" class="filter-input" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                        <small style="color: #666;">Select both date and time</small>
                    </div>
                    <div>
                        <label for="filter-datetime-before" style="display: block; margin-bottom: 5px; font-weight: 500;">Date Before:</label>
                        <input type="datetime-local" id="filter-datetime-before" class="filter-input" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                        <small style="color: #666;">Select both date and time</small>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="filter-and-words" style="display: block; margin-bottom: 5px; font-weight: 500;">AND Words (all must be present):</label>
                        <input type="text" id="filter-and-words" class="filter-input" placeholder="e.g., blue, green" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                        <small style="color: #666;">Separate multiple words with commas</small>
                    </div>
                    <div>
                        <label for="filter-or-words" style="display: block; margin-bottom: 5px; font-weight: 500;">OR Words (at least one must be present):</label>
                        <input type="text" id="filter-or-words" class="filter-input" placeholder="e.g., red, purple blue" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                        <small style="color: #666;">Separate multiple words with commas</small>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="filter-polarity-min" style="display: block; margin-bottom: 5px; font-weight: 500;" title="Minimum sentiment polarity: -1.0 (most negative) to 1.0 (most positive)">Polarity Min:</label>
                        <input type="number" id="filter-polarity-min" class="filter-input" placeholder="e.g., -0.5" step="0.1" min="-1" max="1" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;" title="Range: -1.0 (most negative) to 1.0 (most positive)">
                        <small style="color: #666;">Range: -1.0 (negative) to 1.0 (positive)</small>
                    </div>
                    <div>
                        <label for="filter-polarity-max" style="display: block; margin-bottom: 5px; font-weight: 500;" title="Maximum sentiment polarity: -1.0 (most negative) to 1.0 (most positive)">Polarity Max:</label>
                        <input type="number" id="filter-polarity-max" class="filter-input" placeholder="e.g., 0.5" step="0.1" min="-1" max="1" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;" title="Range: -1.0 (most negative) to 1.0 (most positive)">
                        <small style="color: #666;">Range: -1.0 (negative) to 1.0 (positive)</small>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="filter-subjectivity-min" style="display: block; margin-bottom: 5px; font-weight: 500;" title="Minimum sentiment subjectivity: 0.0 (most objective) to 1.0 (most subjective)">Subjectivity Min:</label>
                        <input type="number" id="filter-subjectivity-min" class="filter-input" placeholder="e.g., 0.3" step="0.1" min="0" max="1" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;" title="Range: 0.0 (most objective) to 1.0 (most subjective)">
                        <small style="color: #666;">Range: 0.0 (objective) to 1.0 (subjective)</small>
                    </div>
                    <div>
                        <label for="filter-subjectivity-max" style="display: block; margin-bottom: 5px; font-weight: 500;" title="Maximum sentiment subjectivity: 0.0 (most objective) to 1.0 (most subjective)">Subjectivity Max:</label>
                        <input type="number" id="filter-subjectivity-max" class="filter-input" placeholder="e.g., 0.7" step="0.1" min="0" max="1" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;" title="Range: 0.0 (most objective) to 1.0 (most subjective)">
                        <small style="color: #666;">Range: 0.0 (objective) to 1.0 (subjective)</small>
                    </div>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button id="apply-filters" class="btn" style="flex: 0 0 auto;">Apply Filters</button>
                    <button id="clear-filters" class="btn btn-secondary" style="flex: 0 0 auto;">Clear Filters</button>
                    <div id="filter-status" style="display: flex; align-items: center; margin-left: 15px; color: #666; font-size: 14px;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="tabs">
        <div class="tab active" data-tab="summary">Summary</div>
        <div class="tab" data-tab="charts">Visualizations</div>
        <div class="tab" data-tab="nlp">NLP Analysis</div>
        <div class="tab" data-tab="top-tweets">Top Tweets</div>
        <div class="tab" data-tab="data">Data Preview</div>
    </div>
    
    <div id="summary" class="tab-content active">
        <div class="summary-box" id="summary-box">{{ summary }}</div>
    </div>

    <div id="charts" class="tab-content">
        <div id="charts-container">
            {{ charts_html | safe }}
        </div>
    </div>

    <div id="nlp" class="tab-content">
        <div class="card">
            <h2>Word Cloud</h2>
            <div style="text-align: center;">
                <img id="wordcloud-img" src="{{ url_for('get_wordcloud_image', session_id=session_id) }}" alt="Word Cloud" style="max-width: 100%; height: auto; border-radius: 8px;">
            </div>
        </div>
        <div id="nlp-charts-container">
            {{ nlp_charts_html | safe }}
        </div>
    </div>
    
    <div id="charts" class="tab-content">
        <div id="charts-container">{{ charts_html | safe }}</div>
    </div>
    
    <div id="top-tweets" class="tab-content">
        <h3>Top Tweets by Favorites <span id="top-tweets-count" class="count-badge">(Showing {{ top_tweets|length }})</span></h3>
        {% if top_tweets %}
        <div class="table-container">
            <table class="data-table" id="top-tweets-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Text</th>
                        <th>Favorites</th>
                        <th>Retweets</th>
                        <th title="Sentiment Analysis with TextBlob's default settings. The polarity score goes from -1.0 to 1.0 for Negative to Positive">Polarity</th>
                        <th title="Sentiment Analysis with TextBlob's default settings. The Subjectivity score goes from 0 to 1, very objective to very subjective">Subjectivity</th>
                    </tr>
                </thead>
                <tbody id="top-tweets-body">
                    {% for tweet in top_tweets %}
                    <tr>
                        <td>{{ tweet.date }}</td>
                        <td class="text-cell">{{ tweet.text }}</td>
                        <td>{{ tweet.favorite_count | format_number }}</td>
                        <td>{{ tweet.retweet_count | format_number }}</td>
                        <td>{{ "%.2f"|format(tweet.sentiment_polarity) if tweet.sentiment_polarity is not none else 'N/A' }}</td>
                        <td>{{ "%.2f"|format(tweet.sentiment_subjectivity) if tweet.sentiment_subjectivity is not none else 'N/A' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="load-more-btn">
            <button id="load-more-tweets" data-offset="20">Load More...</button>
        </div>
        {% else %}
        <p>No tweets with engagement data available.</p>
        {% endif %}
    </div>
    
    <div id="data" class="tab-content">
        <h3>Data Preview <span id="data-preview-count" class="count-badge">(Showing {{ preview_data|length }})</span></h3>
        <div class="table-container">
            <table class="data-table" id="data-preview-table">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Date</th>
                        <th>Text</th>
                        <th>Source</th>
                        <th title="Sentiment Analysis with TextBlob's default settings. The polarity score goes from -1.0 to 1.0 for Negative to Positive">Polarity</th>
                        <th title="Sentiment Analysis with TextBlob's default settings. The Subjectivity score goes from 0 to 1, very objective to very subjective">Subjectivity</th>
                    </tr>
                </thead>
                <tbody id="data-preview-body">
                    {% for row in preview_data %}
                    <tr>
                        <td>{{ row.record_type }}</td>
                        <td>{{ row.date }}</td>
                        <td class="text-cell">{{ row.text }}</td>
                        <td>{{ row.source }}</td>
                        <td>{{ "%.2f"|format(row.sentiment_polarity) if row.sentiment_polarity is not none else 'N/A' }}</td>
                        <td>{{ "%.2f"|format(row.sentiment_subjectivity) if row.sentiment_subjectivity is not none else 'N/A' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="load-more-btn">
            <button id="load-more-data" data-offset="100">Load More...</button>
        </div>
    </div>
</div>
"""

RESULTS_SCRIPTS = r"""
<script>
document.addEventListener('DOMContentLoaded', function() {
    const sessionId = {{ session_id | tojson }};
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.dataset.tab;
            
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(targetId).classList.add('active');
        });
    });
    
    // Collapsible filter section
    const filtersToggle = document.getElementById('filters-toggle');
    const filtersContent = document.getElementById('filters-content');
    
    if (filtersToggle && filtersContent) {
        filtersToggle.addEventListener('click', function() {
            this.classList.toggle('expanded');
            filtersContent.classList.toggle('expanded');
        });
    }
    
    // Function to escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Function to update count badges
    function updateCount(elementId, count) {
        const countElement = document.getElementById(elementId);
        if (countElement) {
            countElement.textContent = `(Showing ${count})`;
        }
    }
    
    // Filter functionality
    let currentFilters = {
        datetime_after: null,
        datetime_before: null,
        filter_and: null,
        filter_or: null,
        polarity_min: null,
        polarity_max: null,
        subjectivity_min: null,
        subjectivity_max: null
    };
    
    function buildFilterParams() {
        const params = new URLSearchParams();
        if (currentFilters.datetime_after) {
            params.append('datetime_after', currentFilters.datetime_after);
        }
        if (currentFilters.datetime_before) {
            params.append('datetime_before', currentFilters.datetime_before);
        }
        if (currentFilters.filter_and) {
            params.append('filter_and', currentFilters.filter_and);
        }
        if (currentFilters.filter_or) {
            params.append('filter_or', currentFilters.filter_or);
        }
        if (currentFilters.polarity_min !== null) {
            params.append('polarity_min', currentFilters.polarity_min);
        }
        if (currentFilters.polarity_max !== null) {
            params.append('polarity_max', currentFilters.polarity_max);
        }
        if (currentFilters.subjectivity_min !== null) {
            params.append('subjectivity_min', currentFilters.subjectivity_min);
        }
        if (currentFilters.subjectivity_max !== null) {
            params.append('subjectivity_max', currentFilters.subjectivity_max);
        }
        return params.toString();
    }
    
    async function applyFilters() {
        const filterStatus = document.getElementById('filter-status');
        filterStatus.textContent = 'Applying filters...';
        filterStatus.style.color = '#666';
        
        // Get filter values
        const datetimeAfterInput = document.getElementById('filter-datetime-after');
        const datetimeBeforeInput = document.getElementById('filter-datetime-before');
        const datetimeAfter = datetimeAfterInput.value;
        const datetimeBefore = datetimeBeforeInput.value;
        const andWords = document.getElementById('filter-and-words').value;
        const orWords = document.getElementById('filter-or-words').value;
        
        // Get sentiment filter values
        const polarityMinInput = document.getElementById('filter-polarity-min');
        const polarityMaxInput = document.getElementById('filter-polarity-max');
        const subjectivityMinInput = document.getElementById('filter-subjectivity-min');
        const subjectivityMaxInput = document.getElementById('filter-subjectivity-max');
        
        const polarityMin = polarityMinInput.value !== '' ? parseFloat(polarityMinInput.value) : null;
        const polarityMax = polarityMaxInput.value !== '' ? parseFloat(polarityMaxInput.value) : null;
        const subjectivityMin = subjectivityMinInput.value !== '' ? parseFloat(subjectivityMinInput.value) : null;
        const subjectivityMax = subjectivityMaxInput.value !== '' ? parseFloat(subjectivityMaxInput.value) : null;
        
        // Validate sentiment filter ranges
        if (polarityMin !== null && (polarityMin < -1.0 || polarityMin > 1.0)) {
            filterStatus.textContent = 'Error: Polarity Min must be between -1.0 and 1.0';
            filterStatus.style.color = '#dc2626';
            polarityMinInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (polarityMax !== null && (polarityMax < -1.0 || polarityMax > 1.0)) {
            filterStatus.textContent = 'Error: Polarity Max must be between -1.0 and 1.0';
            filterStatus.style.color = '#dc2626';
            polarityMaxInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (polarityMin !== null && polarityMax !== null && polarityMin > polarityMax) {
            filterStatus.textContent = 'Error: Polarity Min cannot be greater than Polarity Max';
            filterStatus.style.color = '#dc2626';
            polarityMinInput.style.borderColor = '#dc2626';
            polarityMaxInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (subjectivityMin !== null && (subjectivityMin < 0.0 || subjectivityMin > 1.0)) {
            filterStatus.textContent = 'Error: Subjectivity Min must be between 0.0 and 1.0';
            filterStatus.style.color = '#dc2626';
            subjectivityMinInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (subjectivityMax !== null && (subjectivityMax < 0.0 || subjectivityMax > 1.0)) {
            filterStatus.textContent = 'Error: Subjectivity Max must be between 0.0 and 1.0';
            filterStatus.style.color = '#dc2626';
            subjectivityMaxInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (subjectivityMin !== null && subjectivityMax !== null && subjectivityMin > subjectivityMax) {
            filterStatus.textContent = 'Error: Subjectivity Min cannot be greater than Subjectivity Max';
            filterStatus.style.color = '#dc2626';
            subjectivityMinInput.style.borderColor = '#dc2626';
            subjectivityMaxInput.style.borderColor = '#dc2626';
            return;
        }
        
        // Validate datetime inputs
        // datetime-local input returns empty string if invalid or incomplete
        // We need to check if the input looks like it has partial data
        const afterInputRaw = datetimeAfterInput.value;
        const beforeInputRaw = datetimeBeforeInput.value;
        
        // If input appears to have been touched but is invalid/incomplete
        if (datetimeAfterInput.validity && !datetimeAfterInput.validity.valid && datetimeAfterInput.value === '') {
            // Check if user might have entered partial data
            const afterRawValue = datetimeAfterInput.getAttribute('value');
            if (afterRawValue && afterRawValue !== '') {
                filterStatus.textContent = 'Error: Date After field is incomplete. Please select both date and time.';
                filterStatus.style.color = '#dc2626';
                datetimeAfterInput.style.borderColor = '#dc2626';
                return;
            }
        }
        
        if (datetimeBeforeInput.validity && !datetimeBeforeInput.validity.valid && datetimeBeforeInput.value === '') {
            const beforeRawValue = datetimeBeforeInput.getAttribute('value');
            if (beforeRawValue && beforeRawValue !== '') {
                filterStatus.textContent = 'Error: Date Before field is incomplete. Please select both date and time.';
                filterStatus.style.color = '#dc2626';
                datetimeBeforeInput.style.borderColor = '#dc2626';
                return;
            }
        }
        
        // Additional validation: datetime-local should have format YYYY-MM-DDTHH:MM
        // If the value is set but doesn't match the expected format, it's incomplete
        if (afterInputRaw && afterInputRaw.length > 0 && afterInputRaw.length < 16) {
            filterStatus.textContent = 'Error: Date After field is incomplete. Please select both date and time.';
            filterStatus.style.color = '#dc2626';
            datetimeAfterInput.style.borderColor = '#dc2626';
            return;
        }
        
        if (beforeInputRaw && beforeInputRaw.length > 0 && beforeInputRaw.length < 16) {
            filterStatus.textContent = 'Error: Date Before field is incomplete. Please select both date and time.';
            filterStatus.style.color = '#dc2626';
            datetimeBeforeInput.style.borderColor = '#dc2626';
            return;
        }
        
        // Reset border colors on successful validation
        datetimeAfterInput.style.borderColor = '#ddd';
        datetimeBeforeInput.style.borderColor = '#ddd';
        polarityMinInput.style.borderColor = '#ddd';
        polarityMaxInput.style.borderColor = '#ddd';
        subjectivityMinInput.style.borderColor = '#ddd';
        subjectivityMaxInput.style.borderColor = '#ddd';
        
        // Update current filters
        currentFilters.datetime_after = datetimeAfter || null;
        currentFilters.datetime_before = datetimeBefore || null;
        currentFilters.filter_and = andWords || null;
        currentFilters.filter_or = orWords || null;
        currentFilters.polarity_min = polarityMin;
        currentFilters.polarity_max = polarityMax;
        currentFilters.subjectivity_min = subjectivityMin;
        currentFilters.subjectivity_max = subjectivityMax;
        
        try {
            // Fetch filtered data
            const filterParams = buildFilterParams();
            const response = await fetch(`/session/${sessionId}/api/filter-data?${filterParams}`);
            const data = await response.json();
            
            if (data.error) {
                filterStatus.textContent = `Error: ${data.error}`;
                filterStatus.style.color = '#dc2626';
                return;
            }
            
            // Update stats
            updateStats(data.stats);
            
            // Update summary
            document.getElementById('summary-box').textContent = data.summary;
            
            // Update charts
            updateCharts(data.charts_html);
            
            // Update NLP charts
            updateNlpCharts(data.nlp_charts_html);
            
            // Update top tweets
            updateTopTweets(data.top_tweets);
            
            // Update data preview
            updateDataPreview(data.preview_data);
            
            // Update wordcloud with filter parameters
            const wordcloudImg = document.getElementById('wordcloud-img');
            if (wordcloudImg) {
                wordcloudImg.src = `/session/${sessionId}/wordcloud.png?${filterParams}&t=${Date.now()}`;
            }
            
            // Update status
            const hasFilters = datetimeAfter || datetimeBefore || andWords || orWords || 
                               polarityMin !== null || polarityMax !== null || 
                               subjectivityMin !== null || subjectivityMax !== null;
            if (hasFilters) {
                filterStatus.textContent = `Showing ${data.stats.total_records.toLocaleString()} of ${data.stats.unfiltered_total.toLocaleString()} records`;
                filterStatus.style.color = '#1da1f2';
            } else {
                filterStatus.textContent = '';
            }
        } catch (err) {
            console.error('Error applying filters:', err);
            filterStatus.textContent = 'Error applying filters';
            filterStatus.style.color = '#dc2626';
        }
    }
    
    function updateStats(stats) {
        // Update header stats text
        const headerStats = document.querySelector('header .header-stats');
        if (headerStats) {
            let statsParts = [`Total Records: ${stats.total_records.toLocaleString()}`];
            for (const [type, count] of Object.entries(stats.type_counts)) {
                statsParts.push(`${type.charAt(0).toUpperCase() + type.slice(1)}: ${count.toLocaleString()}`);
            }
            headerStats.textContent = statsParts.join(' | ');
        }
    }
    
    function updateCharts(chartsHtml) {
        const chartsContainer = document.getElementById('charts-container');
        
        if (!chartsContainer) {
            return;
        }
        
        // Clear existing charts
        chartsContainer.innerHTML = '';
        
        if (!chartsHtml) {
            return;
        }
        
        // Create a temporary container to parse the HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = chartsHtml;
        
        // Extract and append all chart containers
        const chartDivs = tempDiv.querySelectorAll('.chart-container');
        chartDivs.forEach(chartDiv => {
            chartsContainer.appendChild(chartDiv.cloneNode(true));
        });
        
        // Execute all script tags from the charts HTML
        const scripts = tempDiv.querySelectorAll('script');
        scripts.forEach(oldScript => {
            const newScript = document.createElement('script');
            if (oldScript.src) {
                newScript.src = oldScript.src;
            } else {
                newScript.textContent = oldScript.textContent;
            }
            document.body.appendChild(newScript);
            // Remove the script after a short delay to avoid accumulation
            setTimeout(() => {
                if (newScript.parentNode) {
                    newScript.parentNode.removeChild(newScript);
                }
            }, 100);
        });
    }
    
    function updateNlpCharts(nlpChartsHtml) {
        const nlpChartsContainer = document.getElementById('nlp-charts-container');
        
        if (!nlpChartsContainer) {
            return;
        }
        
        // Clear existing NLP charts
        nlpChartsContainer.innerHTML = '';
        
        if (!nlpChartsHtml) {
            return;
        }
        
        // Create a temporary container to parse the HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = nlpChartsHtml;
        
        // Extract and append all chart containers
        const chartDivs = tempDiv.querySelectorAll('.chart-container');
        chartDivs.forEach(chartDiv => {
            nlpChartsContainer.appendChild(chartDiv.cloneNode(true));
        });
        
        // Execute all script tags from the NLP charts HTML
        const scripts = tempDiv.querySelectorAll('script');
        scripts.forEach(oldScript => {
            const newScript = document.createElement('script');
            if (oldScript.src) {
                newScript.src = oldScript.src;
            } else {
                newScript.textContent = oldScript.textContent;
            }
            document.body.appendChild(newScript);
            // Remove the script after a short delay to avoid accumulation
            setTimeout(() => {
                if (newScript.parentNode) {
                    newScript.parentNode.removeChild(newScript);
                }
            }, 100);
        });
    }
    
    function updateTopTweets(tweets) {
        const tbody = document.getElementById('top-tweets-body');
        const loadMoreBtn = document.getElementById('load-more-tweets');
        
        tbody.innerHTML = '';
        tweets.forEach(tweet => {
            const row = document.createElement('tr');
            const polarity = tweet.sentiment_polarity != null ? tweet.sentiment_polarity.toFixed(2) : 'N/A';
            const subjectivity = tweet.sentiment_subjectivity != null ? tweet.sentiment_subjectivity.toFixed(2) : 'N/A';
            row.innerHTML = `
                <td>${escapeHtml(tweet.date)}</td>
                <td class="text-cell">${escapeHtml(tweet.text)}</td>
                <td>${escapeHtml(tweet.favorite_count.toLocaleString())}</td>
                <td>${escapeHtml(tweet.retweet_count.toLocaleString())}</td>
                <td>${escapeHtml(polarity)}</td>
                <td>${escapeHtml(subjectivity)}</td>
            `;
            tbody.appendChild(row);
        });
        
        updateCount('top-tweets-count', tweets.length);
        
        // Reset load more button
        if (loadMoreBtn) {
            loadMoreBtn.dataset.offset = '20';
            loadMoreBtn.disabled = false;
            loadMoreBtn.textContent = 'Load More...';
        }
    }
    
    function updateDataPreview(records) {
        const tbody = document.getElementById('data-preview-body');
        const loadMoreBtn = document.getElementById('load-more-data');
        
        tbody.innerHTML = '';
        records.forEach(record => {
            const row = document.createElement('tr');
            const polarity = record.sentiment_polarity != null ? record.sentiment_polarity.toFixed(2) : 'N/A';
            const subjectivity = record.sentiment_subjectivity != null ? record.sentiment_subjectivity.toFixed(2) : 'N/A';
            row.innerHTML = `
                <td>${escapeHtml(record.record_type)}</td>
                <td>${escapeHtml(record.date)}</td>
                <td class="text-cell">${escapeHtml(record.text)}</td>
                <td>${escapeHtml(record.source)}</td>
                <td>${escapeHtml(polarity)}</td>
                <td>${escapeHtml(subjectivity)}</td>
            `;
            tbody.appendChild(row);
        });
        
        updateCount('data-preview-count', records.length);
        
        // Reset load more button
        if (loadMoreBtn) {
            loadMoreBtn.dataset.offset = '100';
            loadMoreBtn.disabled = false;
            loadMoreBtn.textContent = 'Load More...';
        }
    }
    
    function clearFilters() {
        const datetimeAfterInput = document.getElementById('filter-datetime-after');
        const datetimeBeforeInput = document.getElementById('filter-datetime-before');
        const polarityMinInput = document.getElementById('filter-polarity-min');
        const polarityMaxInput = document.getElementById('filter-polarity-max');
        const subjectivityMinInput = document.getElementById('filter-subjectivity-min');
        const subjectivityMaxInput = document.getElementById('filter-subjectivity-max');
        const filterStatus = document.getElementById('filter-status');
        
        datetimeAfterInput.value = '';
        datetimeBeforeInput.value = '';
        document.getElementById('filter-and-words').value = '';
        document.getElementById('filter-or-words').value = '';
        polarityMinInput.value = '';
        polarityMaxInput.value = '';
        subjectivityMinInput.value = '';
        subjectivityMaxInput.value = '';
        
        // Reset border colors
        datetimeAfterInput.style.borderColor = '#ddd';
        datetimeBeforeInput.style.borderColor = '#ddd';
        polarityMinInput.style.borderColor = '#ddd';
        polarityMaxInput.style.borderColor = '#ddd';
        subjectivityMinInput.style.borderColor = '#ddd';
        subjectivityMaxInput.style.borderColor = '#ddd';
        
        // Reset status
        filterStatus.textContent = '';
        filterStatus.style.color = '#666';
        
        currentFilters = {
            datetime_after: null,
            datetime_before: null,
            filter_and: null,
            filter_or: null,
            polarity_min: null,
            polarity_max: null,
            subjectivity_min: null,
            subjectivity_max: null
        };
        
        applyFilters();
    }
    
    // Attach event listeners
    document.getElementById('apply-filters').addEventListener('click', applyFilters);
    document.getElementById('clear-filters').addEventListener('click', clearFilters);
    
    // Load More Top Tweets
    const loadMoreTweets = document.getElementById('load-more-tweets');
    if (loadMoreTweets) {
        const tweetsPageSize = 20;
        loadMoreTweets.addEventListener('click', async function() {
            const offset = parseInt(this.dataset.offset);
            const tbody = document.getElementById('top-tweets-body');
            
            this.disabled = true;
            this.textContent = 'Loading...';
            
            try {
                const filterParams = buildFilterParams();
                const url = `/session/${sessionId}/api/top-tweets?offset=${offset}&limit=${tweetsPageSize}${filterParams ? '&' + filterParams : ''}`;
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.tweets && data.tweets.length > 0) {
                    data.tweets.forEach(tweet => {
                        const row = document.createElement('tr');
                        const polarity = tweet.sentiment_polarity != null ? tweet.sentiment_polarity.toFixed(2) : 'N/A';
                        const subjectivity = tweet.sentiment_subjectivity != null ? tweet.sentiment_subjectivity.toFixed(2) : 'N/A';
                        row.innerHTML = `
                            <td>${escapeHtml(tweet.date)}</td>
                            <td class="text-cell">${escapeHtml(tweet.text)}</td>
                            <td>${escapeHtml(tweet.favorite_count.toLocaleString())}</td>
                            <td>${escapeHtml(tweet.retweet_count.toLocaleString())}</td>
                            <td>${escapeHtml(polarity)}</td>
                            <td>${escapeHtml(subjectivity)}</td>
                        `;
                        tbody.appendChild(row);
                    });
                    
                    // Update count
                    const currentCount = tbody.querySelectorAll('tr').length;
                    updateCount('top-tweets-count', currentCount);
                    
                    this.dataset.offset = offset + tweetsPageSize;
                    this.disabled = false;
                    this.textContent = 'Load More...';
                    
                    if (!data.has_more) {
                        this.disabled = true;
                        this.textContent = `All ${data.total} tweets loaded`;
                    }
                } else {
                    this.disabled = true;
                    this.textContent = 'No more tweets';
                }
            } catch (err) {
                console.error('Error loading tweets:', err);
                this.disabled = false;
                this.textContent = 'Error loading tweets. Try again?';
            }
        });
    }
    
    // Load More Data Preview
    const loadMoreData = document.getElementById('load-more-data');
    if (loadMoreData) {
        const dataPageSize = 100;
        loadMoreData.addEventListener('click', async function() {
            const offset = parseInt(this.dataset.offset);
            const tbody = document.getElementById('data-preview-body');
            
            this.disabled = true;
            this.textContent = 'Loading...';
            
            try {
                const filterParams = buildFilterParams();
                const url = `/session/${sessionId}/api/data-preview?offset=${offset}&limit=${dataPageSize}${filterParams ? '&' + filterParams : ''}`;
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.records && data.records.length > 0) {
                    data.records.forEach(record => {
                        const row = document.createElement('tr');
                        const polarity = record.sentiment_polarity != null ? record.sentiment_polarity.toFixed(2) : 'N/A';
                        const subjectivity = record.sentiment_subjectivity != null ? record.sentiment_subjectivity.toFixed(2) : 'N/A';
                        row.innerHTML = `
                            <td>${escapeHtml(record.record_type)}</td>
                            <td>${escapeHtml(record.date)}</td>
                            <td class="text-cell">${escapeHtml(record.text)}</td>
                            <td>${escapeHtml(record.source)}</td>
                            <td>${escapeHtml(polarity)}</td>
                            <td>${escapeHtml(subjectivity)}</td>
                        `;
                        tbody.appendChild(row);
                    });
                    
                    // Update count
                    const currentCount = tbody.querySelectorAll('tr').length;
                    updateCount('data-preview-count', currentCount);
                    
                    this.dataset.offset = offset + dataPageSize;
                    this.disabled = false;
                    this.textContent = 'Load More...';
                    
                    if (!data.has_more) {
                        this.disabled = true;
                        this.textContent = `All ${data.total} records loaded`;
                    }
                } else {
                    this.disabled = true;
                    this.textContent = 'No more records';
                }
            } catch (err) {
                console.error('Error loading data:', err);
                this.disabled = false;
                this.textContent = 'Error loading data. Try again?';
            }
        });
    }
});
</script>
"""


def format_number(value):
    """Format a number with thousands separator."""
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


app.jinja_env.filters["format_number"] = format_number


def parse_filter_params():
    """Parse filter parameters from request arguments.
    
    Returns:
        Dictionary with filter parameters ready for filter_dataframe function.
    """
    import pytz
    
    filters = {}
    
    # Parse datetime filters
    datetime_after_str = request.args.get("datetime_after")
    if datetime_after_str:
        try:
            # Parse the datetime string
            dt = pd.to_datetime(datetime_after_str)
            # Make timezone-aware if not already
            if dt.tzinfo is None:
                dt = dt.tz_localize(pytz.UTC)
            filters["datetime_after"] = dt.to_pydatetime()
        except Exception:
            pass  # Ignore invalid datetime
    
    datetime_before_str = request.args.get("datetime_before")
    if datetime_before_str:
        try:
            dt = pd.to_datetime(datetime_before_str)
            if dt.tzinfo is None:
                dt = dt.tz_localize(pytz.UTC)
            filters["datetime_before"] = dt.to_pydatetime()
        except Exception:
            pass
    
    # Parse text filters
    filter_and_str = request.args.get("filter_and")
    if filter_and_str:
        # Split by comma and strip whitespace
        filters["filter_and"] = [w.strip() for w in filter_and_str.split(",") if w.strip()]
    
    filter_or_str = request.args.get("filter_or")
    if filter_or_str:
        filters["filter_or"] = [w.strip() for w in filter_or_str.split(",") if w.strip()]
    
    # Parse sentiment polarity filters
    polarity_min_str = request.args.get("polarity_min")
    if polarity_min_str:
        try:
            polarity_min = float(polarity_min_str)
            if -1.0 <= polarity_min <= 1.0:
                filters["polarity_min"] = polarity_min
        except (ValueError, TypeError):
            pass  # Ignore invalid values
    
    polarity_max_str = request.args.get("polarity_max")
    if polarity_max_str:
        try:
            polarity_max = float(polarity_max_str)
            if -1.0 <= polarity_max <= 1.0:
                filters["polarity_max"] = polarity_max
        except (ValueError, TypeError):
            pass
    
    # Parse sentiment subjectivity filters
    subjectivity_min_str = request.args.get("subjectivity_min")
    if subjectivity_min_str:
        try:
            subjectivity_min = float(subjectivity_min_str)
            if 0.0 <= subjectivity_min <= 1.0:
                filters["subjectivity_min"] = subjectivity_min
        except (ValueError, TypeError):
            pass
    
    subjectivity_max_str = request.args.get("subjectivity_max")
    if subjectivity_max_str:
        try:
            subjectivity_max = float(subjectivity_max_str)
            if 0.0 <= subjectivity_max <= 1.0:
                filters["subjectivity_max"] = subjectivity_max
        except (ValueError, TypeError):
            pass
    
    # Validate min/max relationships
    if "polarity_min" in filters and "polarity_max" in filters:
        if filters["polarity_min"] > filters["polarity_max"]:
            # Remove invalid filters
            del filters["polarity_min"]
            del filters["polarity_max"]
    
    if "subjectivity_min" in filters and "subjectivity_max" in filters:
        if filters["subjectivity_min"] > filters["subjectivity_max"]:
            # Remove invalid filters
            del filters["subjectivity_min"]
            del filters["subjectivity_max"]
    
    return filters


@app.route("/")
def index():
    """Render the upload page."""
    return render_template_string(
        BASE_TEMPLATE,
        title="Upload",
        header_title="🐦 Twitter Archive Analyzer",
        header_description="Upload your Twitter archive files (.js or .json) for analysis and visualization",
        content=render_template_string(UPLOAD_CONTENT),
        scripts=UPLOAD_SCRIPTS,
    )


@app.route("/upload", methods=["POST"])
def upload():
    """Handle file uploads and process data."""
    if "files" not in request.files:
        flash("No files selected", "error")
        return redirect(url_for("index"))

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        flash("No files selected", "error")
        return redirect(url_for("index"))

    # Collect file data
    file_data = []
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            data = f.read()
            file_data.append((filename, data))

    if not file_data:
        flash("No valid .js or .json files found", "error")
        return redirect(url_for("index"))

    # Process files
    try:
        df, errors = process_files(file_data)

        if errors:
            for err in errors:
                flash(f"Warning: {err}", "info")

        if df.empty:
            flash("No records were extracted from the files", "error")
            return redirect(url_for("index"))

        # Run sentiment analysis
        df = analyze_sentiment(df)
        
        # Store in session with unique ID
        session_id = secrets.token_hex(SESSION_ID_BYTES)
        save_session_data(session_id, {
            "df": df,
            "timestamp": datetime.now().isoformat(),
        })

        flash(f"Successfully processed {len(df):,} records from {len(file_data)} file(s)", "success")
        return redirect(url_for("results", session_id=session_id))

    except Exception as e:
        flash(f"Error processing files: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/session/<session_id>/results")
def results(session_id):
    """Render analysis results."""
    if not is_valid_session_id(session_id):
        flash("Invalid session ID.", "error")
        return redirect(url_for("index"))
    
    data = load_session_data(session_id)
    if not data:
        flash("Session not found or expired. Please upload files again.", "info")
        return redirect(url_for("index"))

    df = data["df"]

    # Generate summary
    summary_text = summarize(df)

    # Generate charts
    charts = generate_all_charts(df)
    std_charts_html = ""
    nlp_charts_html = ""
    first_chart = True
    for name, fig in charts.items():
        if fig is not None:
            chart_html = get_chart_html(fig, include_plotlyjs=first_chart)
            
            if name.startswith("sentiment"):
                nlp_charts_html += f'<div class="chart-container">{chart_html}</div>'
            else:
                std_charts_html += f'<div class="chart-container">{chart_html}</div>'
                first_chart = False

    # Get type counts
    type_counts = df["record_type"].value_counts().to_dict() if "record_type" in df.columns else {}

    # Get top tweets
    top_tweets = []
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        tweets_only = df[df["record_type"] == "tweet"] if "record_type" in df.columns else df
        top = tweets_only.nlargest(20, "favorite_count")
        for _, row in top.iterrows():
            date_str = (
                row["created_at"].strftime("%Y-%m-%d %H:%M")
                if pd.notna(row.get("created_at"))
                else "N/A"
            )
            top_tweets.append(
                {
                    "text": row.get("text", ""),
                    "favorite_count": row.get("favorite_count", 0),
                    "retweet_count": row.get("retweet_count", 0) or 0,
                    "date": date_str,
                    "sentiment_polarity": row.get("sentiment_polarity"),
                    "sentiment_subjectivity": row.get("sentiment_subjectivity"),
                }
            )

    # Get preview data
    preview_data = []
    for _, row in df.head(100).iterrows():
        date_str = (
            row["created_at"].strftime("%Y-%m-%d %H:%M")
            if pd.notna(row.get("created_at"))
            else "N/A"
        )
        preview_data.append(
            {
                "record_type": row.get("record_type", ""),
                "date": date_str,
                "text": row.get("text", "") or "",
                "source": row.get("source", "") or "",
                "sentiment_polarity": row.get("sentiment_polarity"),
                "sentiment_subjectivity": row.get("sentiment_subjectivity"),
            }
        )

    # Build header stats text (escape for safety even though record_type is controlled)
    stats_parts = [f"Total Records: {escape(format_number(len(df)))}"]
    for record_type, count in type_counts.items():
        stats_parts.append(f"{escape(record_type.title())}: {escape(format_number(count))}")
    header_stats = Markup(" | ".join(stats_parts))
    
    # Build header button
    header_button = Markup(f'<a href="{url_for("index")}" class="btn btn-secondary">← Return to File Upload</a> <a href="{url_for("download", session_id=session_id)}" class="btn">📥 Download Output Data</a>')
    
    return render_template_string(
        BASE_TEMPLATE,
        title="Results",
        header_title="🐦 Twitter Archive Analyzer - Results",
        header_button=header_button,
        header_stats=header_stats,
        content=render_template_string(
            RESULTS_CONTENT,
            summary=summary_text,
            charts_html=std_charts_html,
            nlp_charts_html=nlp_charts_html,
            top_tweets=top_tweets,
            preview_data=preview_data,
            session_id=session_id,
        ),
        scripts=render_template_string(RESULTS_SCRIPTS, session_id=session_id),
    )


@app.route("/session/<session_id>/api/filter-data")
def api_filter_data(session_id):
    """API endpoint to get filtered data with all components updated."""
    if not is_valid_session_id(session_id):
        return jsonify({"error": "Invalid session ID"}), 400
    
    data = load_session_data(session_id)
    if not data:
        return jsonify({"error": "Session expired"}), 404
    
    original_df = data["df"]
    unfiltered_total = len(original_df)
    
    # Parse and apply filters
    from twitter_analyzer.core import filter_dataframe
    filter_params = parse_filter_params()
    
    if filter_params:
        df = filter_dataframe(original_df, **filter_params)
    else:
        df = original_df
    
    # Generate summary
    summary_text = summarize(df)
    
    # Generate charts
    charts = generate_all_charts(df)
    std_charts_html = ""
    nlp_charts_html = ""
    first_chart = True
    for name, fig in charts.items():
        if fig is not None:
            chart_html = get_chart_html(fig, include_plotlyjs=first_chart)
            
            if name.startswith("sentiment"):
                nlp_charts_html += f'<div class="chart-container">{chart_html}</div>'
            else:
                std_charts_html += f'<div class="chart-container">{chart_html}</div>'
                first_chart = False
    
    # Get type counts
    type_counts = df["record_type"].value_counts().to_dict() if "record_type" in df.columns else {}
    
    # Get top tweets
    top_tweets = []
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        tweets_only = df[df["record_type"] == "tweet"] if "record_type" in df.columns else df
        top = tweets_only.nlargest(20, "favorite_count")
        for _, row in top.iterrows():
            date_str = (
                row["created_at"].strftime("%Y-%m-%d %H:%M")
                if pd.notna(row.get("created_at"))
                else "N/A"
            )
            top_tweets.append(
                {
                    "text": row.get("text", ""),
                    "favorite_count": row.get("favorite_count", 0),
                    "retweet_count": row.get("retweet_count", 0) or 0,
                    "date": date_str,
                    "sentiment_polarity": row.get("sentiment_polarity"),
                    "sentiment_subjectivity": row.get("sentiment_subjectivity"),
                }
            )
    
    # Get preview data
    preview_data = []
    for _, row in df.head(100).iterrows():
        date_str = (
            row["created_at"].strftime("%Y-%m-%d %H:%M")
            if pd.notna(row.get("created_at"))
            else "N/A"
        )
        preview_data.append(
            {
                "record_type": row.get("record_type", ""),
                "date": date_str,
                "text": row.get("text", "") or "",
                "source": row.get("source", "") or "",
                "sentiment_polarity": row.get("sentiment_polarity"),
                "sentiment_subjectivity": row.get("sentiment_subjectivity"),
            }
        )
    
    return jsonify({
        "stats": {
            "total_records": len(df),
            "unfiltered_total": unfiltered_total,
            "type_counts": type_counts,
        },
        "summary": summary_text,
        "summary": summary_text,
        "charts_html": std_charts_html,
        "nlp_charts_html": nlp_charts_html,
        "top_tweets": top_tweets,
        "top_tweets": top_tweets,
        "preview_data": preview_data,
    })


@app.route("/session/<session_id>/api/top-tweets")
def api_top_tweets(session_id):
    """API endpoint for paginated top tweets."""
    if not is_valid_session_id(session_id):
        return jsonify({"error": "Invalid session ID"}), 400
    
    data = load_session_data(session_id)
    if not data:
        return jsonify({"error": "Session expired"}), 404
    
    original_df = data["df"]
    
    # Parse and apply filters
    from twitter_analyzer.core import filter_dataframe
    filter_params = parse_filter_params()
    
    if filter_params:
        df = filter_dataframe(original_df, **filter_params)
    else:
        df = original_df
    
    # Get pagination parameters with validation
    offset = max(0, request.args.get("offset", 0, type=int))
    limit = max(1, min(1000, request.args.get("limit", 20, type=int)))  # Cap at 1000
    
    # Get top tweets
    top_tweets = []
    if "favorite_count" in df.columns and df["favorite_count"].notna().any():
        tweets_only = df[df["record_type"] == "tweet"] if "record_type" in df.columns else df
        all_top = tweets_only.nlargest(min(len(tweets_only), 1000), "favorite_count")  # Limit to top 1000
        
        # Paginate
        paginated = all_top.iloc[offset:offset + limit]
        
        for _, row in paginated.iterrows():
            date_str = (
                row["created_at"].strftime("%Y-%m-%d %H:%M")
                if pd.notna(row.get("created_at"))
                else "N/A"
            )
            top_tweets.append(
                {
                    "text": row.get("text", ""),
                    "favorite_count": row.get("favorite_count", 0),
                    "retweet_count": row.get("retweet_count", 0) or 0,
                    "date": date_str,
                    "sentiment_polarity": row.get("sentiment_polarity"),
                    "sentiment_subjectivity": row.get("sentiment_subjectivity"),
                }
            )
        
        return jsonify({
            "tweets": top_tweets,
            "has_more": offset + limit < len(all_top),
            "total": len(all_top),
        })
    
    return jsonify({"tweets": [], "has_more": False, "total": 0})


@app.route("/session/<session_id>/api/data-preview")
def api_data_preview(session_id):
    """API endpoint for paginated data preview."""
    if not is_valid_session_id(session_id):
        return jsonify({"error": "Invalid session ID"}), 400
    
    data = load_session_data(session_id)
    if not data:
        return jsonify({"error": "Session expired"}), 404
    
    original_df = data["df"]
    
    # Parse and apply filters
    from twitter_analyzer.core import filter_dataframe
    filter_params = parse_filter_params()
    
    if filter_params:
        df = filter_dataframe(original_df, **filter_params)
    else:
        df = original_df
    
    # Get pagination parameters with validation
    offset = max(0, request.args.get("offset", 0, type=int))
    limit = max(1, min(1000, request.args.get("limit", 100, type=int)))  # Cap at 1000
    
    # Get preview data
    preview_data = []
    paginated = df.iloc[offset:offset + limit]
    
    for _, row in paginated.iterrows():
        date_str = (
            row["created_at"].strftime("%Y-%m-%d %H:%M")
            if pd.notna(row.get("created_at"))
            else "N/A"
        )
        preview_data.append(
            {
                "record_type": row.get("record_type", ""),
                "date": date_str,
                "text": row.get("text", "") or "",
                "source": row.get("source", "") or "",
                "sentiment_polarity": row.get("sentiment_polarity"),
                "sentiment_subjectivity": row.get("sentiment_subjectivity"),
            }
        )
    
    return jsonify({
        "records": preview_data,
        "has_more": offset + limit < len(df),
        "total": len(df),
    })


@app.route("/session/<session_id>/download")
def download(session_id):
    """Generate and download a ZIP file containing all output files."""
    if not is_valid_session_id(session_id):
        flash("Invalid session ID.", "error")
        return redirect(url_for("index"))
    
    data = load_session_data(session_id)
    if not data:
        flash("Session expired. Please upload files again.", "info")
        return redirect(url_for("index"))
    
    df = data["df"]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    
    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Get column lists
        archive_cols = get_archive_columns(df)
        analysis_cols = get_analysis_columns(df)
        has_analysis = len(analysis_cols) > 0
        
        # Generate and add CSV files
        # Export archive-only data (original Twitter data)
        # All records - archive only
        csv_all_archive = io.StringIO()
        df[archive_cols].to_csv(csv_all_archive, index=False)
        zip_file.writestr(f"twitter_records_{timestamp}.csv", csv_all_archive.getvalue())
        
        # Per-type CSV files - archive only
        if "record_type" in df.columns:
            for typ in sorted(df["record_type"].dropna().unique()):
                df_sub = df[df["record_type"] == typ]
                csv_type = io.StringIO()
                df_sub[archive_cols].to_csv(csv_type, index=False)
                zip_file.writestr(f"{typ}_{timestamp}.csv", csv_type.getvalue())
        
        # Export data with analysis columns (if any analysis was performed)
        if has_analysis:
            # All records - with analysis
            csv_all_analysis = io.StringIO()
            df.to_csv(csv_all_analysis, index=False)
            zip_file.writestr(f"twitter_records_{timestamp}_analysis.csv", csv_all_analysis.getvalue())
            
            # Per-type CSV files - with analysis
            if "record_type" in df.columns:
                for typ in sorted(df["record_type"].dropna().unique()):
                    df_sub = df[df["record_type"] == typ]
                    csv_type_analysis = io.StringIO()
                    df_sub.to_csv(csv_type_analysis, index=False)
                    zip_file.writestr(f"{typ}_{timestamp}_analysis.csv", csv_type_analysis.getvalue())
        
        # Generate summary
        summary_text = summarize(df)
        
        # Generate charts
        charts = generate_all_charts(df)
        
        # Generate charts as PNG images directly to ZIP (no temp files needed)
        image_names = []
        try:
            import kaleido
            for name, fig in charts.items():
                if fig is not None:
                    try:
                        # Generate PNG image directly to bytes (no file I/O)
                        img_bytes = fig.to_image(format="png")
                        image_name = f"{name}.png"
                        zip_file.writestr(image_name, img_bytes)
                        image_names.append(image_name)
                    except Exception as chart_error:
                        # Log error for this specific chart but continue with others
                        print(f"Warning: Could not generate PNG for '{name}': {chart_error}")
        except ImportError:
            # kaleido not available - skip PNG generation, will have HTML charts instead
            print("Info: kaleido not installed, skipping PNG generation (HTML report will have interactive charts)")
        except Exception as e:
            # Unexpected error with kaleido
            print(f"Warning: Could not generate PNG images: {e}")
        
        # Generate and add word cloud image
        try:
            wc = generate_wordcloud(df)
            if wc:
                wc_img_io = io.BytesIO()
                wc.to_image().save(wc_img_io, 'PNG')
                wc_img_io.seek(0)
                wordcloud_filename = f"wordcloud_{timestamp}.png"
                zip_file.writestr(wordcloud_filename, wc_img_io.getvalue())
                image_names.append(wordcloud_filename)
        except Exception as wc_error:
            print(f"Warning: Could not generate word cloud: {wc_error}")
        
        # Generate Markdown report (reusing CLI function)
        md_report = generate_markdown_report(df, summary_text, image_names, timestamp)
        zip_file.writestr(f"report_{timestamp}.md", md_report)
        
        # Generate HTML report (reusing CLI function)
        charts_html = []
        for name, fig in charts.items():
            if fig is not None:
                charts_html.append(get_chart_html(fig, include_plotlyjs=(len(charts_html) == 0)))
        
        html_report = generate_html_report(df, summary_text, charts_html, timestamp)
        zip_file.writestr(f"report_{timestamp}.html", html_report)
    
    # Prepare the ZIP file for download
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'twitter_analysis_{timestamp}.zip'
    )


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route("/session/<session_id>/wordcloud.png")
def get_wordcloud_image(session_id):
    """Serve the word cloud image."""
    if not is_valid_session_id(session_id):
        return "", 404
    
    data = load_session_data(session_id)
    if not data:
        return "", 404
        
    df = data["df"]
    
    # Check if filters are applied via query params, similar to api endpoints
    # This allows the wordcloud to update when filters change
    from twitter_analyzer.core import filter_dataframe
    filter_params = parse_filter_params()
    
    if filter_params:
        df = filter_dataframe(df, **filter_params)
    
    wc = generate_wordcloud(df)
    if not wc:
        # Return a blank 1x1 pixel image if no data
        return "", 204
        
    img_io = io.BytesIO()
    wc.to_image().save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')


def create_app():
    """Application factory for WSGI servers."""
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
