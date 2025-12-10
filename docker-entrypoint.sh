#!/bin/sh
# Wrapper script to run cleanup in background and start the web server

# Function to run cleanup periodically
run_cleanup() {
    while true; do
        # Sleep for 24 hours (86400 seconds)
        sleep 86400
        
        # Run cleanup script
        echo "Running session cleanup..."
        python cleanup_sessions.py || echo "Cleanup failed with exit code $?"
    done
}

# Start cleanup loop in background
run_cleanup &

# Start the web application
exec python -m gunicorn --bind 0.0.0.0:${PORT:-8080} --workers ${GUNICORN_WORKERS:-2} --timeout 120 webapp:app
