# Twitter Archive Analyzer
# Multi-stage build for smaller, more secure container

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt


# Production image
FROM python:3.12-slim

# Install Chromium and its dependencies for kaleido (needed for PNG chart generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
  chromium \
  chromium-driver \
  # Chromium dependencies for headless mode
  libnss3 \
  libatk-bridge2.0-0 \
  libcups2 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libxkbcommon0 \
  libpango-1.0-0 \
  libcairo2 \
  libasound2 \
  # Additional dependencies for X11 and fonts
  libx11-6 \
  libx11-xcb1 \
  libxcb1 \
  libxext6 \
  libdbus-1-3 \
  libglib2.0-0 \
  fonts-liberation \
  # Additional dependencies for Chromium stability
  libdrm2 \
  libxshmfence1 \
  libexpat1 \
  && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY twitter_analyzer/ ./twitter_analyzer/
COPY webapp.py .
COPY cli.py .

# Create exports directory with proper permissions
RUN mkdir -p exports && chown -R appuser:appuser /app

# Create directory for Chromium crash dumps (as root before switching user)
RUN mkdir -p /tmp/.chromium && chmod 1777 /tmp/.chromium

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
# Point kaleido (choreographer) to the Chromium binary
ENV BROWSER_PATH=/usr/bin/chromium
# Chromium flags for headless operation
ENV CHROMIUM_FLAGS="--disable-dev-shm-usage --no-sandbox --disable-gpu"
# SECRET_KEY: Not set by default. The app will create a persistent key file.
# For production deployments, set SECRET_KEY environment variable for better security:
# docker run -e SECRET_KEY="your-secret-key" -p 8080:8080 twitter-analyzer

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Default command runs the web app
# Workers can be configured via GUNICORN_WORKERS environment variable
# Default: 2 workers, suitable for light loads. For production, set based on CPU cores (2*cores+1)
CMD ["sh", "-c", "python -m gunicorn --bind 0.0.0.0:${PORT:-8080} --workers ${GUNICORN_WORKERS:-2} --timeout 120 webapp:app"]
