# Twitter Archive Analyzer

A comprehensive tool for analyzing and visualizing Twitter/X archive exports.
Supports command-line interface for batch processing and a web application for
interactive analysis.

## Features

- **Parse Twitter Archives**: Handles `.js` and `.json` files from Twitter data exports
- **Data Analysis**: Generates statistics on tweets, deleted tweets, and notes
- **Visualizations**: Interactive charts using Plotly
- **CSV Export**: Export cleaned data to CSV files
- **Multiple Interfaces**: CLI for scripting, web app for interactive use
- **Docker Support**: Easy deployment with containerization

## Quick Start

### Installation

Run the below commands if you intend to use the Command Line Interface (CLI) or
run the web application locally.
You can skip this section if you plan to use the Docker image.

```bash
# Clone the repository
git clone https://github.com/julowe/twitter-futzing.git
cd twitter-futzing

# Create and Activate Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Note on Image Generation:**

- The CLI generates PNG images of visualizations using [kaleido](https://github.com/plotly/Kaleido)
- Kaleido 1.0.0+ requires Chrome/Chromium to be installed.
  If you do not have it installed, or if the version installed does not work
  with Kaleido then this script will download its own copy into the venv
- Interactive charts are always available in the generated HTML report

### Command Line Usage

```bash
# Analyze a single file
python cli.py tweets.js

# Analyze multiple files
python cli.py tweets.js deleted-tweets.js note-tweets.js

# Specify output directory
python cli.py --output-dir ./my_exports tweets.js

# Skip image generation (faster)
python cli.py --no-images tweets.js

# Verbose output
python cli.py -v tweets.js
```

The CLI will generate in the `exports/` directory:

- CSV files for all records and per-type breakdowns
- PNG images of visualizations
- HTML report with interactive charts
- Markdown report with tables and image references

### Web Application

```bash
# Run locally (development)
python webapp.py

# Or with gunicorn (production)
# IMPORTANT: Set SECRET_KEY for multi-worker deployments
export SECRET_KEY="your-secret-key-here"
gunicorn --bind 0.0.0.0:5000 --workers 2 webapp:app
```

Then open [http://localhost:5000] in your browser to upload files
and view interactive results.

**Session URLs:**

- When you upload files, a unique session URL is generated (e.g., `/session/abc123.../results`)
- Bookmark this URL to return to your analysis later
- Each session is isolated and can only be accessed with the correct unique URL
- Sessions are automatically cleaned up after 30 days (in Docker deployments)

**Production Notes:**

- Always set the `SECRET_KEY` environment variable when running with multiple workers
- Without SECRET_KEY, a persistent key file is created automatically in the
  system temp directory
- Use `--workers` appropriate for your server (typically 2-4 workers)
- Session data is stored in the system temp directory (`/tmp/` on Linux) under
  `twitter_analyzer_sessions/` and shared across workers
- Old session files (>30 days) are automatically cleaned up in Docker deployments

### Docker

#### Using Pre-built Image from GitHub Container Registry

```bash
# Pull the latest image
docker pull ghcr.io/julowe/twitter-futzing:latest

# Run the container
docker run -p 8080:8080 ghcr.io/julowe/twitter-futzing:latest
```

#### Building Locally

```bash
# Build the image
docker build -t twitter-analyzer .

# Run the container
docker run -p 8080:8080 twitter-analyzer

# Or use docker-compose
docker-compose up
```

## Getting Your Twitter Archive

1. Go to Twitter/X Settings → Your Account → Download an archive of your data
2. Wait for Twitter to prepare your archive (may take a few days)
3. Download and extract the archive
4. Find the `data/` folder containing files like:
   - `tweets.js` - Your tweets
   - `deleted-tweets.js` - Deleted tweets
   - `note-tweets.js` - Twitter Notes
   - And other data files

## Project Structure

```
twitter-futzing/
├── twitter_analyzer/       # Core library
│   ├── __init__.py
│   ├── core.py            # Parsing and analysis functions
│   └── visualizations.py  # Chart generation
├── cli.py                 # Command-line interface
├── webapp.py              # Flask web application
├── Dockerfile             # Container configuration
├── requirements.txt       # Python dependencies
├── exports/               # Output directory (gitignored)
└── Twitter_Archive_Analyzer.ipynb  # Legacy Jupyter notebook
```

## Development

```bash
# Create and Activate Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements.txt

# Run tests (if any)
python -m pytest

# Run the web app in debug mode
DEBUG=true python webapp.py
```

## CI/CD

This project uses GitHub Actions to automatically build and publish Docker
images to the GitHub Container Registry (ghcr.io).

### Automated Docker Builds

- **Trigger**: Automatic builds occur on every push to the `main` branch
- **Registry**: Images are published to `ghcr.io/julowe/twitter-futzing`
- **Tags**:
  - `latest` - Most recent build from main branch
  - `main-<sha>` - Specific commit SHA from main branch
  - `<branch>` - Branch name for non-main branches

### Manual Workflow Trigger

You can also manually trigger the Docker build workflow from the Actions tab in GitHub.

## License

See [LICENSE](LICENSE) file.
