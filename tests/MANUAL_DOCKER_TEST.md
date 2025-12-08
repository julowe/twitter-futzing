# Manual Docker Testing Guide

Since automated Docker tests may fail due to network/environment issues, here's how to manually test PNG generation in Docker:

## Quick Test

```bash
# 1. Build the image
docker build -t twitter-analyzer-test .

# 2. Run the container with tmpfs mount (recommended for Chromium)
docker run -d -p 8765:8080 \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --name test-container \
  twitter-analyzer-test

# Alternative: Run with increased shared memory
docker run -d -p 8765:8080 \
  --shm-size=512m \
  --name test-container \
  twitter-analyzer-test

# 3. Wait a few seconds, then check if it's running
docker ps | grep test-container

# 4. Test the web UI
curl http://localhost:8765/health

# 5. Open in browser
# Visit: http://localhost:8765/

# 6. Upload a test file and download the ZIP
# Check if PNG files are included

# 7. Check logs for errors
docker logs test-container 2>&1 | grep -i "png\|error\|warning\|kaleido\|chromium"

# 8. Clean up
docker stop test-container
docker rm test-container
```

## Detailed Troubleshooting

If PNG generation fails, run these diagnostic commands:

### 1. Check if Chromium is installed
```bash
docker exec test-container chromium --version
```
Expected output: `Chromium 142.0.7444.175` (or similar)

### 2. Check for missing libraries
```bash
docker exec test-container ldd /usr/bin/chromium | grep "not found"
```
Expected output: (none - no missing libraries)

### 3. Test kaleido directly
```bash
docker exec test-container python3 -c "
import plotly.graph_objects as go
print('Creating figure...')
fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[1, 2, 3])])
print('Generating PNG...')
try:
    img_bytes = fig.to_image(format='png')
    print(f'✓ Success! Generated {len(img_bytes)} bytes')
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
"
```

### 4. Check environment variables
```bash
docker exec test-container env | grep BROWSER
```
Expected: `BROWSER_PATH=/usr/bin/chromium`

### 5. Test Chromium in headless mode
```bash
docker exec test-container chromium --headless --disable-gpu --no-sandbox --dump-dom about:blank
```
Should output HTML without errors

### 6. Check Python packages
```bash
docker exec test-container python3 -c "import kaleido; print(kaleido.__version__)"
```

## Common Issues and Solutions

### Issue: "chrome_crashpad_handler: --database is required" or "Connection reset by peer"
**Solution**: Chromium needs adequate shared memory for headless operation
- **Option 1 (Recommended)**: Use tmpfs mount
  ```bash
  docker run -d -p 8765:8080 \
    --tmpfs /tmp:rw,noexec,nosuid,size=512m \
    --name test-container \
    twitter-analyzer-test
  ```
- **Option 2**: Increase shared memory size
  ```bash
  docker run -d -p 8765:8080 \
    --shm-size=512m \
    --name test-container \
    twitter-analyzer-test
  ```

### Issue: "Kaleido requires Google Chrome to be installed"
**Solution**: Chromium not installed or `BROWSER_PATH` not set
- Check Dockerfile includes `chromium` package
- Check `ENV BROWSER_PATH=/usr/bin/chromium` is set

### Issue: "Missing common dependencies"
**Solution**: System libraries missing
- Ensure all dependencies from Dockerfile are installed:
  - libnss3, libatk-bridge2.0-0, libcups2, libxcomposite1
  - libxdamage1, libxfixes3, libxrandr2, libgbm1
  - libxkbcommon0, libpango-1.0-0, libcairo2, libasound2
  - libx11-6, libx11-xcb1, libxcb1, libxext6
  - libdbus-1-3, libglib2.0-0, fonts-liberation

### Issue: "Permission denied" or "Failed to move to new namespace"
**Solution**: Add `--no-sandbox` flag to Chrome
- This requires code changes in webapp.py to set additional kaleido options
- Or run container with `--privileged` (not recommended for production)

## Expected Test Results

When everything works correctly:

1. **Container logs**: No "Warning: Could not generate PNG" messages
2. **ZIP file**: Contains 6 PNG files:
   - monthly_counts.png
   - text_length.png
   - top_languages.png
   - top_sources.png
   - hourly_activity.png
   - day_of_week.png
3. **PNG files**: Valid (magic bytes: `89 50 4E 47 0D 0A 1A 0A`)

## Interactive Testing

```bash
# Start container interactively
docker run -it --rm -p 8765:8080 twitter-analyzer-test bash

# Inside container, test manually:
python3 -c "
from webapp import app
import io, zipfile

# Import test data
test_data = '''window.YTD.tweets.part0 = [{
    \"tweet\": {
        \"id_str\": \"123\",
        \"created_at\": \"Wed Nov 15 12:00:00 +0000 2023\",
        \"full_text\": \"Test\",
        \"lang\": \"en\",
        \"source\": \"<a href='http://twitter.com'>Twitter Web App</a>\",
        \"favorite_count\": \"10\",
        \"retweet_count\": \"5\"
    }
}]'''

# Process and generate ZIP
from twitter_analyzer.core import process_files
df, errors = process_files([('test.js', test_data.encode())])
print(f'Records: {len(df)}')

# Try to generate charts
from twitter_analyzer.visualizations import generate_all_charts
charts = generate_all_charts(df)
print(f'Charts: {list(charts.keys())}')

# Try to generate PNG
for name, fig in charts.items():
    if fig:
        try:
            img_bytes = fig.to_image(format='png')
            print(f'✓ {name}: {len(img_bytes)} bytes')
        except Exception as e:
            print(f'✗ {name}: {e}')
        break
"
```

This will show exactly where PNG generation fails if there's an issue.
