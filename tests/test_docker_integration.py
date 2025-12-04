#!/usr/bin/env python3
"""
Docker integration test for Twitter Archive Analyzer.

This test builds the Docker image and verifies that:
1. The container starts successfully
2. The web UI is accessible
3. File upload works
4. Download generates a ZIP with all expected files including PNGs
5. PNG files are valid

Run with: python tests/test_docker_integration.py

Note: This test requires Docker to be installed and running.
If the Docker build fails due to network/SSL issues, you can:
1. Build the image manually: docker build -t twitter-analyzer .
2. Run the container: docker run -d -p 8765:8080 --name test-container twitter-analyzer
3. Test manually using the steps shown in this script
"""

import subprocess
import sys
import time
import io
import zipfile
from pathlib import Path

import requests


def run_command(cmd, check=True, capture_output=True):
    """Run a shell command and return output."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=capture_output,
        text=True
    )
    if check and result.returncode != 0:
        print(f"✗ Command failed: {cmd}")
        if capture_output:
            print(f"  stdout: {result.stdout}")
            print(f"  stderr: {result.stderr}")
        return None
    return result


def main():
    """Run Docker integration tests."""
    print("=" * 70)
    print("Twitter Archive Analyzer - Docker Integration Test")
    print("=" * 70)
    
    # Configuration
    image_name = "twitter-analyzer-test"
    container_name = "twitter-analyzer-test-container"
    test_port = 8765
    
    try:
        # Step 1: Build Docker image
        print("\nStep 1: Building Docker image...")
        print("  This may take several minutes...")
        result = run_command(f"docker build -t {image_name} . 2>&1 | tail -50", check=False)
        
        if result is None or result.returncode != 0:
            print("\n✗ Docker build failed!")
            print("\nThis is usually caused by:")
            print("  1. Network connectivity issues")
            print("  2. SSL certificate problems (corporate proxies)")
            print("  3. Docker not running")
            print("\nTo test manually:")
            print(f"  1. Build: docker build -t {image_name} .")
            print(f"  2. Run: docker run -d -p {test_port}:8080 --name {container_name} {image_name}")
            print(f"  3. Test: curl http://localhost:{test_port}/health")
            print(f"  4. Access: http://localhost:{test_port}/")
            print("\nIf build succeeds but PNG generation fails, check container logs:")
            print(f"  docker logs {container_name}")
            sys.exit(1)
        
        print("✓ Docker image built successfully")
        
        # Step 2: Start container
        print("\nStep 2: Starting Docker container...")
        result = run_command(
            f"docker run -d --name {container_name} "
            f"-p {test_port}:8080 "
            f"-e SECRET_KEY=test-secret-key-for-docker-testing "
            f"{image_name}"
        )
        if result is None:
            print("✗ Failed to start container")
            sys.exit(1)
        print("✓ Docker container started")
        
        # Step 3: Wait for container to be ready
        print("\nStep 3: Waiting for container to be ready...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                response = requests.get(f"http://localhost:{test_port}/health", timeout=2)
                if response.status_code == 200:
                    print("✓ Container is ready")
                    break
            except requests.RequestException:
                pass
            print(".", end="", flush=True)
            time.sleep(1)
        else:
            print("\n✗ Container failed to become ready")
            print("\nContainer logs:")
            run_command(f"docker logs {container_name}", check=False, capture_output=False)
            sys.exit(1)
        
        # Step 4: Test web UI access
        print("\nStep 4: Testing web UI access...")
        response = requests.get(f"http://localhost:{test_port}/")
        if response.status_code == 200:
            print("✓ Web UI is accessible")
        else:
            print(f"✗ Web UI returned HTTP {response.status_code}")
            sys.exit(1)
        
        # Step 5: Test file upload and download
        print("\nStep 5: Testing file upload and download...")
        
        # Create minimal test data
        test_data = '''window.YTD.tweets.part0 = [
  {
    "tweet": {
      "id_str": "1234567890",
      "created_at": "Wed Nov 15 12:00:00 +0000 2023",
      "full_text": "Test tweet for Docker integration",
      "lang": "en",
      "source": "<a href=\\"https://mobile.twitter.com\\" rel=\\"nofollow\\">Twitter Web App</a>",
      "favorite_count": "10",
      "retweet_count": "5"
    }
  }
]'''
        
        session = requests.Session()
        
        # Upload file
        print("  Uploading test file...")
        files = {'files': ('mock_tweets.js', test_data.encode('utf-8'), 'application/javascript')}
        response = session.post(
            f"http://localhost:{test_port}/upload",
            files=files,
            allow_redirects=False
        )
        
        if response.status_code != 302:
            print(f"  ✗ Upload failed with status {response.status_code}")
            sys.exit(1)
        print("  ✓ File uploaded successfully")
        
        # Download ZIP
        print("  Downloading ZIP file...")
        response = session.get(f"http://localhost:{test_port}/download")
        
        if response.status_code != 200:
            print(f"  ✗ Download failed with status {response.status_code}")
            sys.exit(1)
        print("  ✓ ZIP file downloaded successfully")
        
        # Verify ZIP contents
        print("  Verifying ZIP contents...")
        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            file_list = zip_file.namelist()
            
            print(f"    Files in ZIP: {len(file_list)}")
            for filename in sorted(file_list):
                print(f"      - {filename}")
            
            # Check for CSV files
            csv_files = [f for f in file_list if f.endswith('.csv')]
            if not csv_files:
                print("  ✗ No CSV files found in ZIP")
                sys.exit(1)
            print(f"  ✓ Found {len(csv_files)} CSV file(s)")
            
            # Check for PNG files
            png_files = [f for f in file_list if f.endswith('.png')]
            if not png_files:
                print("  ✗ No PNG files found in ZIP")
                print("    PNG generation failed in Docker!")
                print("\n  Checking container logs for PNG errors...")
                result = run_command(
                    f"docker logs {container_name} 2>&1 | grep -i 'warning.*png\\|error.*png\\|kaleido\\|chromium' | tail -20",
                    check=False
                )
                if result and result.stdout.strip():
                    print("  Error messages found:")
                    print(result.stdout)
                print("\n  Troubleshooting steps:")
                print("    1. Check if Chromium is installed:")
                print(f"       docker exec {container_name} chromium --version")
                print("    2. Check for missing libraries:")
                print(f"       docker exec {container_name} ldd /usr/bin/chromium | grep 'not found'")
                print("    3. Test kaleido manually:")
                print(f"       docker exec {container_name} python3 -c \"import plotly.graph_objects as go; fig = go.Figure(data=[go.Scatter(x=[1,2,3], y=[1,2,3])]); print('Generating...'); img = fig.to_image(format='png'); print(f'Success: {{len(img)}} bytes')\"")
                sys.exit(1)
            print(f"  ✓ Found {len(png_files)} PNG file(s)")
            
            # Verify PNG files are valid
            for png_file in png_files:
                png_data = zip_file.read(png_file)
                if png_data[:8] != b'\x89PNG\r\n\x1a\n':
                    print(f"  ✗ {png_file} is not a valid PNG")
                    sys.exit(1)
            print("  ✓ All PNG files are valid")
            
            # Check for HTML report
            html_files = [f for f in file_list if f.endswith('.html')]
            if not html_files:
                print("  ✗ No HTML report found in ZIP")
                sys.exit(1)
            print("  ✓ Found HTML report")
            
            # Check for Markdown report
            md_files = [f for f in file_list if f.endswith('.md')]
            if not md_files:
                print("  ✗ No Markdown report found in ZIP")
                sys.exit(1)
            print("  ✓ Found Markdown report")
        
        print("\n✓ File upload and download test passed")
        
        # Step 6: Check logs
        print("\nStep 6: Checking container logs for errors...")
        result = run_command(
            f"docker logs {container_name} 2>&1 | grep -i 'warning.*png\\|error.*png' | head -5 || true",
            check=False
        )
        if result and result.stdout.strip():
            print("  ⚠ Found PNG-related warnings/errors in logs:")
            print(f"    {result.stdout}")
        else:
            print("  ✓ No PNG generation errors in logs")
        
        print("\n" + "=" * 70)
        print("✓ All Docker tests passed!")
        print("=" * 70)
        
    finally:
        # Cleanup
        print("\nCleaning up...")
        run_command(f"docker stop {container_name}", check=False)
        run_command(f"docker rm {container_name}", check=False)
        print("✓ Cleanup complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        # Cleanup
        run_command("docker stop twitter-analyzer-test-container", check=False)
        run_command("docker rm twitter-analyzer-test-container", check=False)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup
        run_command("docker stop twitter-analyzer-test-container", check=False)
        run_command("docker rm twitter-analyzer-test-container", check=False)
        sys.exit(1)
