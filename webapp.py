"""Twitter Archive Analyzer Web Application.

Flask-based web application for uploading and analyzing Twitter archive exports.
Provides interactive visualizations and data tables.
"""

import io
import os
import secrets
from datetime import datetime
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
)
from werkzeug.utils import secure_filename

import pandas as pd

from twitter_analyzer.core import (
    parse_twitter_export_bytes,
    normalize_items,
    coerce_types,
    summarize,
    process_files,
)
from twitter_analyzer.visualizations import generate_all_charts, get_chart_html


app = Flask(__name__)

# Secret key configuration - in production, always set SECRET_KEY environment variable
# to a consistent value to preserve sessions across restarts
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import warnings
    warnings.warn(
        "SECRET_KEY not set. Using randomly generated key. "
        "Sessions will be invalidated on restart. "
        "Set SECRET_KEY environment variable for production.",
        RuntimeWarning
    )
    _secret_key = secrets.token_hex(32)
app.secret_key = _secret_key

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max upload

# Session data storage
# NOTE: This in-memory storage is suitable for single-instance demo deployments.
# For production with multiple workers/instances, use Redis, database, or
# client-side session storage (e.g., Flask-Session with Redis backend).
# Data is isolated per session ID and automatically cleaned on browser close.
session_data: Dict[str, Dict] = {}

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
        header h1 {
            margin: 0;
            color: #1da1f2;
            font-size: 1.8em;
        }
        header p {
            margin: 10px 0 0;
            color: #666;
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
            <h1>🐦 Twitter Archive Analyzer</h1>
            <p>Upload your Twitter archive files (.js or .json) for analysis and visualization</p>
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
    <h2>Analysis Results</h2>
    <a href="{{ url_for('index') }}" class="btn btn-secondary" style="margin-bottom: 20px;">← Upload More Files</a>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{{ total_records | format_number }}</div>
            <div class="stat-label">Total Records</div>
        </div>
        {% for type, count in type_counts.items() %}
        <div class="stat-card">
            <div class="stat-value">{{ count | format_number }}</div>
            <div class="stat-label">{{ type | title }}</div>
        </div>
        {% endfor %}
    </div>
    
    <div class="tabs">
        <div class="tab active" data-tab="summary">Summary</div>
        <div class="tab" data-tab="charts">Visualizations</div>
        <div class="tab" data-tab="top-tweets">Top Tweets</div>
        <div class="tab" data-tab="data">Data Preview</div>
    </div>
    
    <div id="summary" class="tab-content active">
        <div class="summary-box">{{ summary }}</div>
    </div>
    
    <div id="charts" class="tab-content">
        {{ charts_html | safe }}
    </div>
    
    <div id="top-tweets" class="tab-content">
        <h3>Top Tweets by Favorites</h3>
        {% if top_tweets %}
        <div class="table-container">
            <table class="data-table" id="top-tweets-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Text</th>
                        <th>Favorites</th>
                        <th>Retweets</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody id="top-tweets-body">
                    {% for tweet in top_tweets %}
                    <tr>
                        <td>{{ tweet.id_str }}</td>
                        <td>{{ tweet.text[:100] }}{% if tweet.text|length > 100 %}...{% endif %}</td>
                        <td>{{ tweet.favorite_count | format_number }}</td>
                        <td>{{ tweet.retweet_count | format_number }}</td>
                        <td>{{ tweet.date }}</td>
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
        <h3>Data Preview (First 100 records)</h3>
        <div class="table-container">
            <table class="data-table" id="data-preview-table">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>ID</th>
                        <th>Date</th>
                        <th>Text</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody id="data-preview-body">
                    {% for row in preview_data %}
                    <tr>
                        <td>{{ row.record_type }}</td>
                        <td>{{ row.id_str }}</td>
                        <td>{{ row.date }}</td>
                        <td>{{ row.text[:80] }}{% if row.text|length > 80 %}...{% endif %}</td>
                        <td>{{ row.source }}</td>
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

RESULTS_SCRIPTS = """
<script>
document.addEventListener('DOMContentLoaded', function() {
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
                const response = await fetch(`/api/top-tweets?offset=${offset}&limit=${tweetsPageSize}`);
                const data = await response.json();
                
                if (data.tweets && data.tweets.length > 0) {
                    data.tweets.forEach(tweet => {
                        const row = document.createElement('tr');
                        const text = tweet.text.length > 100 ? tweet.text.substring(0, 100) + '...' : tweet.text;
                        row.innerHTML = `
                            <td>${tweet.id_str}</td>
                            <td>${text}</td>
                            <td>${tweet.favorite_count.toLocaleString()}</td>
                            <td>${tweet.retweet_count.toLocaleString()}</td>
                            <td>${tweet.date}</td>
                        `;
                        tbody.appendChild(row);
                    });
                    
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
                const response = await fetch(`/api/data-preview?offset=${offset}&limit=${dataPageSize}`);
                const data = await response.json();
                
                if (data.records && data.records.length > 0) {
                    data.records.forEach(record => {
                        const row = document.createElement('tr');
                        const text = record.text.length > 80 ? record.text.substring(0, 80) + '...' : record.text;
                        row.innerHTML = `
                            <td>${record.record_type}</td>
                            <td>${record.id_str}</td>
                            <td>${record.date}</td>
                            <td>${text}</td>
                            <td>${record.source}</td>
                        `;
                        tbody.appendChild(row);
                    });
                    
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


@app.route("/")
def index():
    """Render the upload page."""
    return render_template_string(
        BASE_TEMPLATE,
        title="Upload",
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

        # Store in session
        session_id = secrets.token_hex(16)
        session["data_id"] = session_id
        session_data[session_id] = {
            "df": df,
            "timestamp": datetime.now().isoformat(),
        }

        flash(f"Successfully processed {len(df):,} records from {len(file_data)} file(s)", "success")
        return redirect(url_for("results"))

    except Exception as e:
        flash(f"Error processing files: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/results")
def results():
    """Render analysis results."""
    data_id = session.get("data_id")
    if not data_id or data_id not in session_data:
        flash("No data available. Please upload files first.", "info")
        return redirect(url_for("index"))

    data = session_data[data_id]
    df = data["df"]

    # Generate summary
    summary_text = summarize(df)

    # Generate charts
    charts = generate_all_charts(df)
    charts_html = ""
    first_chart = True
    for name, fig in charts.items():
        if fig is not None:
            chart_html = get_chart_html(fig, include_plotlyjs=first_chart)
            charts_html += f'<div class="chart-container">{chart_html}</div>'
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
                    "id_str": row.get("id_str", ""),
                    "text": row.get("text", ""),
                    "favorite_count": row.get("favorite_count", 0),
                    "retweet_count": row.get("retweet_count", 0) or 0,
                    "date": date_str,
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
                "id_str": row.get("id_str", ""),
                "date": date_str,
                "text": row.get("text", "") or "",
                "source": row.get("source", "") or "",
            }
        )

    return render_template_string(
        BASE_TEMPLATE,
        title="Results",
        content=render_template_string(
            RESULTS_CONTENT,
            total_records=len(df),
            type_counts=type_counts,
            summary=summary_text,
            charts_html=charts_html,
            top_tweets=top_tweets,
            preview_data=preview_data,
        ),
        scripts=RESULTS_SCRIPTS,
    )


@app.route("/api/top-tweets")
def api_top_tweets():
    """API endpoint for paginated top tweets."""
    data_id = session.get("data_id")
    if not data_id or data_id not in session_data:
        return jsonify({"error": "No data available"}), 404
    
    data = session_data[data_id]
    df = data["df"]
    
    # Get pagination parameters
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 20, type=int)
    
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
                    "id_str": row.get("id_str", ""),
                    "text": row.get("text", ""),
                    "favorite_count": row.get("favorite_count", 0),
                    "retweet_count": row.get("retweet_count", 0) or 0,
                    "date": date_str,
                }
            )
        
        return jsonify({
            "tweets": top_tweets,
            "has_more": offset + limit < len(all_top),
            "total": len(all_top),
        })
    
    return jsonify({"tweets": [], "has_more": False, "total": 0})


@app.route("/api/data-preview")
def api_data_preview():
    """API endpoint for paginated data preview."""
    data_id = session.get("data_id")
    if not data_id or data_id not in session_data:
        return jsonify({"error": "No data available"}), 404
    
    data = session_data[data_id]
    df = data["df"]
    
    # Get pagination parameters
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    
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
                "id_str": row.get("id_str", ""),
                "date": date_str,
                "text": row.get("text", "") or "",
                "source": row.get("source", "") or "",
            }
        )
    
    return jsonify({
        "records": preview_data,
        "has_more": offset + limit < len(df),
        "total": len(df),
    })


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


def create_app():
    """Application factory for WSGI servers."""
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
