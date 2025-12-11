# Docker Deployment Guide

## Building and Running

### Basic Usage

```bash
# Build the image
docker build -t twitter-analyzer .

# Run with tmpfs for better Chromium performance (recommended)
docker run -d \
  -p 8080:8080 \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --name twitter-analyzer \
  twitter-analyzer

# Or run without tmpfs (may have slower PNG generation)
docker run -d -p 8080:8080 --name twitter-analyzer twitter-analyzer
```

### With Custom Configuration

```bash
docker run -d \
  -p 8080:8080 \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  -e SECRET_KEY="your-secret-key-here" \
  -e GUNICORN_WORKERS=4 \
  --name twitter-analyzer \
  twitter-analyzer
```

## Troubleshooting PNG Generation

If PNG charts are not generating in the downloaded ZIP files:

### 1. Check Container Logs

```bash
docker logs twitter-analyzer 2>&1 | grep -i "png\|error\|kaleido\|chromium"
```

### 2. Verify Chromium is Working

```bash
# Test Chromium installation
docker exec twitter-analyzer chromium --version

# Test kaleido directly
docker exec twitter-analyzer python3 -c "
import plotly.graph_objects as go
fig = go.Figure(data=[go.Scatter(x=[1,2,3], y=[1,2,3])])
img = fig.to_image(format='png')
print(f'Success: {len(img)} bytes')
"
```

### 3. Common Issues

#### Issue: "chrome_crashpad_handler: --database is required"

**Solution**: Run container with tmpfs mount (recommended):

```bash
docker run -d -p 8080:8080 \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --name twitter-analyzer \
  twitter-analyzer
```

#### Issue: "Connection reset by peer" or Chromium crashes

**Solution**: Increase shared memory size:

```bash
docker run -d -p 8080:8080 \
  --shm-size=512m \
  --name twitter-analyzer \
  twitter-analyzer
```

#### Issue: Still getting BrowserDepsError

**Solution**: Try running container with privileged mode (development only):

```bash
docker run -d -p 8080:8080 \
  --privileged \
  --name twitter-analyzer \
  twitter-analyzer
```

**Note**: `--privileged` mode is not recommended for production. If this fixes the issue, it means there's a security/capability restriction. For production, use:

```bash
docker run -d -p 8080:8080 \
  --cap-add=SYS_ADMIN \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --name twitter-analyzer \
  twitter-analyzer
```

## Environment Variables

- `PORT`: Port to run the web server on (default: 8080)
- `SECRET_KEY`: Flask secret key for session management (auto-generated if not set)
- `GUNICORN_WORKERS`: Number of worker processes (default: 2)
- `BROWSER_PATH`: Path to Chromium binary (default: /usr/bin/chromium)
- `CHROMIUM_FLAGS`: Additional flags for Chromium (default: "--disable-dev-shm-usage --no-sandbox --disable-gpu")

## Session Management

The application uses unique session URLs to allow users to access their analysis results:

- When files are uploaded, a unique session ID is generated
- Users are redirected to `/session/<session_id>/results` to view their analysis
- This URL can be bookmarked or shared to access the same results later
- Session data is stored in `/tmp/twitter_analyzer_sessions/`
- Old session files (>30 days) are automatically deleted every 24 hours

**Note**: Session data is stored in memory/tmpfs and will be lost when the container restarts. For persistent sessions across container restarts, you can mount a volume:

```bash
docker run -d \
  -p 8080:8080 \
  -v twitter-sessions:/tmp/twitter_analyzer_sessions \
  --name twitter-analyzer \
  twitter-analyzer
```

**Security**: Each session ID is a cryptographically random 32-character hexadecimal string. Users cannot access other sessions without the unique URL.

## Health Check

The container includes a health check that runs every 30 seconds:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' twitter-analyzer
```

## Logs

```bash
# View all logs
docker logs twitter-analyzer

# Follow logs
docker logs -f twitter-analyzer

# View recent logs with timestamps
docker logs --since 10m --timestamps twitter-analyzer
```

## Cleanup

```bash
# Stop and remove container
docker stop twitter-analyzer
docker rm twitter-analyzer

# Remove image
docker rmi twitter-analyzer
```

## Production Deployment

For production deployments, consider:

1. **Use tmpfs or increase shm-size**: Chromium needs adequate shared memory
   ```bash
   --tmpfs /tmp:rw,noexec,nosuid,size=512m
   # or
   --shm-size=512m
   ```

2. **Set SECRET_KEY**: Use a secure random key
   ```bash
   -e SECRET_KEY="$(openssl rand -hex 32)"
   ```

3. **Configure workers**: Based on CPU cores (2 * cores + 1)
   ```bash
   -e GUNICORN_WORKERS=5  # for 2-core system
   ```

4. **Use HTTPS**: Put behind a reverse proxy like nginx with SSL/TLS

5. **Resource limits**: Set memory and CPU limits
   ```bash
   --memory="2g" --cpus="2"
   ```

## Example: Production Deployment with Docker Compose

```yaml
version: '3.8'

services:
  twitter-analyzer:
    build: .
    ports:
      - "8080:8080"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - GUNICORN_WORKERS=4
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=512m
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    restart: unless-stopped
```

Run with:
```bash
SECRET_KEY=$(openssl rand -hex 32) docker-compose up -d
```
