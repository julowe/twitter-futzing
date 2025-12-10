#!/bin/bash
# Docker integration test for the Twitter Archive Analyzer
# This script builds and tests the Docker container to ensure PNG generation works

set -e  # Exit on error

echo "======================================================================"
echo "Twitter Archive Analyzer - Docker Integration Test"
echo "======================================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="twitter-analyzer-test"
CONTAINER_NAME="twitter-analyzer-test-container"
TEST_PORT=8765

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
}

# Set trap to cleanup on exit
trap cleanup EXIT

echo -e "\n${YELLOW}Step 1: Building Docker image...${NC}"
docker build -t $IMAGE_NAME . || {
    echo -e "${RED}✗ Docker build failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Docker image built successfully${NC}"

echo -e "\n${YELLOW}Step 2: Starting Docker container...${NC}"
docker run -d \
    --name $CONTAINER_NAME \
    -p $TEST_PORT:8080 \
    -e SECRET_KEY="test-secret-key-for-docker-testing" \
    $IMAGE_NAME || {
    echo -e "${RED}✗ Failed to start Docker container${NC}"
    exit 1
}
echo -e "${GREEN}✓ Docker container started${NC}"

# Wait for container to be ready
echo -e "\n${YELLOW}Step 3: Waiting for container to be ready...${NC}"
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:$TEST_PORT/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Container is ready${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo -n "."
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "\n${RED}✗ Container failed to become ready${NC}"
    docker logs $CONTAINER_NAME
    exit 1
fi

echo -e "\n${YELLOW}Step 4: Testing web UI access...${NC}"
response=$(curl -s -w "%{http_code}" -o /tmp/index_response.html http://localhost:$TEST_PORT/)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✓ Web UI is accessible${NC}"
else
    echo -e "${RED}✗ Web UI returned HTTP $response${NC}"
    exit 1
fi

echo -e "\n${YELLOW}Step 5: Testing file upload and download...${NC}"

# Create a test script to run inside the container
docker exec $CONTAINER_NAME bash -c "cat > /tmp/test_download.py << 'EOPYTHON'
import sys
import io
import zipfile
import requests
from pathlib import Path

# Test data
test_files = {
    'mock_tweets.js': open('/app/twitter_analyzer/../tests/mock_tweets.js', 'rb').read() if Path('/app/tests/mock_tweets.js').exists() else None
}

# If test files don't exist in expected location, try alternate paths
if test_files['mock_tweets.js'] is None:
    test_file_path = Path('/app/tests/mock_tweets.js')
    if not test_file_path.exists():
        # Create minimal test data
        test_data = '''window.YTD.tweets.part0 = [
  {
    \"tweet\": {
      \"id_str\": \"1234567890\",
      \"created_at\": \"Wed Nov 15 12:00:00 +0000 2023\",
      \"full_text\": \"Test tweet\",
      \"lang\": \"en\",
      \"source\": \"<a href=\\\"https://mobile.twitter.com\\\" rel=\\\"nofollow\\\">Twitter Web App</a>\",
      \"favorite_count\": \"10\",
      \"retweet_count\": \"5\"
    }
  }
]'''
        test_files['mock_tweets.js'] = test_data.encode('utf-8')

session = requests.Session()

# Upload file
print('Uploading test file...')
files = {'files': ('mock_tweets.js', test_files['mock_tweets.js'], 'application/javascript')}
response = session.post('http://localhost:8080/upload', files=files, allow_redirects=False)

if response.status_code != 302:
    print(f'✗ Upload failed with status {response.status_code}')
    sys.exit(1)

print('✓ File uploaded successfully')

# Download ZIP
print('Downloading ZIP file...')
response = session.get('http://localhost:8080/download')

if response.status_code != 200:
    print(f'✗ Download failed with status {response.status_code}')
    sys.exit(1)

print('✓ ZIP file downloaded successfully')

# Verify ZIP contents
print('Verifying ZIP contents...')
zip_data = io.BytesIO(response.content)
with zipfile.ZipFile(zip_data, 'r') as zip_file:
    file_list = zip_file.namelist()
    
    # Check for CSV files
    csv_files = [f for f in file_list if f.endswith('.csv')]
    if not csv_files:
        print('✗ No CSV files found in ZIP')
        sys.exit(1)
    print(f'✓ Found {len(csv_files)} CSV file(s)')
    
    # Check for PNG files
    png_files = [f for f in file_list if f.endswith('.png')]
    if not png_files:
        print('⚠ Warning: No PNG files found in ZIP')
        print('  PNG generation may have failed in Docker')
        sys.exit(1)
    print(f'✓ Found {len(png_files)} PNG file(s)')
    
    # Verify PNG files are valid
    for png_file in png_files:
        png_data = zip_file.read(png_file)
        if png_data[:8] != b'\\x89PNG\\r\\n\\x1a\\n':
            print(f'✗ {png_file} is not a valid PNG')
            sys.exit(1)
    print('✓ All PNG files are valid')
    
    # Check for HTML report
    html_files = [f for f in file_list if f.endswith('.html')]
    if not html_files:
        print('✗ No HTML report found in ZIP')
        sys.exit(1)
    print('✓ Found HTML report')
    
    # Check for Markdown report
    md_files = [f for f in file_list if f.endswith('.md')]
    if not md_files:
        print('✗ No Markdown report found in ZIP')
        sys.exit(1)
    print('✓ Found Markdown report')

print('\\n✓ All ZIP contents verified successfully')
EOPYTHON
" || {
    echo -e "${RED}✗ Failed to create test script${NC}"
    exit 1
}

# Run the test script
docker exec $CONTAINER_NAME python3 /tmp/test_download.py || {
    echo -e "\n${RED}✗ Download test failed${NC}"
    echo -e "\n${YELLOW}Container logs:${NC}"
    docker logs $CONTAINER_NAME | tail -50
    exit 1
}

echo -e "\n${GREEN}✓ File upload and download test passed${NC}"

echo -e "\n${YELLOW}Step 6: Checking container logs for errors...${NC}"
if docker logs $CONTAINER_NAME 2>&1 | grep -i "error\|warning.*png\|failed.*png" | grep -v "health"; then
    echo -e "${YELLOW}⚠ Found warnings/errors in logs${NC}"
else
    echo -e "${GREEN}✓ No PNG generation errors in logs${NC}"
fi

echo -e "\n======================================================================"
echo -e "${GREEN}✓ All Docker tests passed!${NC}"
echo -e "======================================================================"
