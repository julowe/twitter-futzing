# Twitter Archive Analyzer

A comprehensive tool for analyzing and visualizing Twitter/X archive exports. Supports command-line interface for batch processing and a web application for interactive analysis.

## Features

- **Parse Twitter Archives**: Handles `.js` and `.json` files from Twitter data exports
- **Data Analysis**: Generates statistics on tweets, deleted tweets, and notes
- **Visualizations**: Interactive charts using Plotly
- **CSV Export**: Export cleaned data to CSV files
- **Multiple Interfaces**: CLI for scripting, web app for interactive use
- **Docker Support**: Easy deployment with containerization

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/julowe/twitter-futzing.git
cd twitter-futzing

# Install dependencies
pip install -r requirements.txt
```

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
# Run locally
python webapp.py

# Or with gunicorn (production)
gunicorn --bind 0.0.0.0:5000 webapp:app
```

Then open http://localhost:5000 in your browser to upload files and view interactive results.

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
# Install development dependencies
pip install -r requirements.txt

# Run tests (if any)
python -m pytest

# Run the web app in debug mode
DEBUG=true python webapp.py
```

## CI/CD

This project uses GitHub Actions to automatically build and publish Docker images to the GitHub Container Registry (ghcr.io).

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
