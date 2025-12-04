# Docker Integration Tests

This directory contains tests for verifying the Docker container functionality, specifically for PNG chart generation.

## Test Files

### `test_docker_integration.py`
Python-based Docker integration test that:
- Builds the Docker image
- Starts a container
- Tests file upload
- Downloads and verifies the ZIP file contains all expected files including PNG charts
- Validates PNG files are properly formatted

**Run with:**
```bash
python tests/test_docker_integration.py
```

**Prerequisites:**
- Docker installed and running
- Python 3.8+ with `requests` package
- Port 8765 available (or modify TEST_PORT in the script)

### `test_docker.sh`
Bash script version of the Docker integration test. Performs the same checks as the Python version.

**Run with:**
```bash
./tests/test_docker.sh
```

**Prerequisites:**
- Docker installed and running
- curl installed
- Port 8765 available

## What These Tests Verify

1. **Docker Build**: Ensures the Dockerfile builds successfully with all dependencies
2. **Container Startup**: Verifies the container starts and becomes healthy
3. **Web UI Access**: Checks the web interface is accessible
4. **File Upload**: Tests uploading Twitter archive files
5. **ZIP Download**: Verifies the download endpoint works
6. **PNG Generation**: **Most importantly**, verifies that PNG charts are generated correctly in the Docker environment
7. **File Validation**: Ensures all expected files are in the ZIP (CSVs, PNGs, HTML, Markdown)

## Why Docker-Specific Tests?

PNG generation using kaleido requires Chromium and specific system dependencies. These tests ensure:
- All required dependencies are installed in the Docker image
- Chromium can run in headless mode
- kaleido can successfully generate PNG charts
- The non-root user (`appuser`) has the necessary permissions

## Troubleshooting

If the tests fail with PNG generation errors:

1. Check the container logs:
   ```bash
   docker logs twitter-analyzer-test-container
   ```

2. Verify Chromium is installed:
   ```bash
   docker exec twitter-analyzer-test-container chromium --version
   ```

3. Test kaleido manually in the container:
   ```bash
   docker exec -it twitter-analyzer-test-container python3 -c "
   import plotly.graph_objects as go
   fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[1, 2, 3])])
   img_bytes = fig.to_image(format='png')
   print(f'Generated {len(img_bytes)} bytes')
   "
   ```

4. Check for missing dependencies:
   ```bash
   docker exec twitter-analyzer-test-container bash -c "
   ldd /usr/bin/chromium | grep 'not found'
   "
   ```

## Expected Output

When tests pass, you should see:
```
======================================================================
Twitter Archive Analyzer - Docker Integration Test
======================================================================

Step 1: Building Docker image...
✓ Docker image built successfully

Step 2: Starting Docker container...
✓ Docker container started

Step 3: Waiting for container to be ready...
✓ Container is ready

Step 4: Testing web UI access...
✓ Web UI is accessible

Step 5: Testing file upload and download...
  Uploading test file...
  ✓ File uploaded successfully
  Downloading ZIP file...
  ✓ ZIP file downloaded successfully
  Verifying ZIP contents...
    Files in ZIP: 10
      - day_of_week.png
      - hourly_activity.png
      - monthly_counts.png
      - report_20251204-123456.html
      - report_20251204-123456.md
      - text_length.png
      - top_languages.png
      - top_sources.png
      - tweet_20251204-123456.csv
      - twitter_records_20251204-123456.csv
  ✓ Found 2 CSV file(s)
  ✓ Found 6 PNG file(s)
  ✓ All PNG files are valid
  ✓ Found HTML report
  ✓ Found Markdown report

✓ File upload and download test passed

Step 6: Checking container logs for errors...
  ✓ No PNG generation errors in logs

======================================================================
✓ All Docker tests passed!
======================================================================
```
