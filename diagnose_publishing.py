#!/usr/bin/env python3
"""
Diagnostic script to check publishing hang issue
"""

import os
import time
import subprocess
from datetime import datetime

def diagnose_publishing_hang():
    """Diagnose why publishing is hanging"""
    
    print('=== PUBLISHING HANG DIAGNOSTIC ===')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    
    workspace_dir = 'workspace'
    
    # Check file sizes
    print('📁 FILE SIZES:')
    for file in os.listdir(workspace_dir):
        if file.endswith('.mp4'):
            size_mb = os.path.getsize(os.path.join(workspace_dir, file)) / (1024*1024)
            print(f'  {file}: {size_mb:.1f}MB')
            if size_mb > 15:
                print(f'    ⚠️  LARGE FILE - may cause upload timeout')
    
    print()
    
    # Test network connectivity
    print('🌐 NETWORK CONNECTIVITY:')
    try:
        import requests
        start = time.time()
        r = requests.get('https://zernio.com', timeout=5)
        elapsed = time.time() - start
        print(f'  zernio.com: {elapsed:.2f}s ✅')
    except Exception as e:
        print(f'  zernio.com: ERROR - {e}')
    
    try:
        start = time.time()
        r = requests.get('https://www.googleapis.com', timeout=5)
        elapsed = time.time() - start
        print(f'  GCS (Google APIs): {elapsed:.2f}s ✅')
    except Exception as e:
        print(f'  GCS (Google APIs): ERROR - {e}')
    
    print()
    
    # Check current timeout settings
    print('⏱️  TIMEOUT SETTINGS:')
    try:
        from dubber.publisher import POST_TIMEOUT, PLATFORM_TIMEOUTS
        print(f'  POST_TIMEOUT: {POST_TIMEOUT}s ({POST_TIMEOUT//60} min)')
        print(f'  Bluesky timeout: {PLATFORM_TIMEOUTS.get("bluesky")}s ({PLATFORM_TIMEOUTS.get("bluesky")//60} min)')
        print('  GCS upload timeout: 180s (3 min)')
    except Exception as e:
        print(f'  Error reading timeouts: {e}')
    
    print()
    
    # Estimate upload time
    print('📊 UPLOAD TIME ESTIMATE:')
    video_file = os.path.join(workspace_dir, 'source.mp4')
    if os.path.exists(video_file):
        size_mb = os.path.getsize(video_file) / (1024*1024)
        
        # Rough estimates based on connection speeds
        speeds = {
            'Fast (10 Mbps)': size_mb * 8 / 10,
            'Medium (5 Mbps)': size_mb * 8 / 5,
            'Slow (2 Mbps)': size_mb * 8 / 2,
            'Very Slow (1 Mbps)': size_mb * 8 / 1
        }
        
        print(f'  Source video: {size_mb:.1f}MB')
        for speed, time_sec in speeds.items():
            if time_sec < 180:
                print(f'  {speed}: {time_sec:.1f}s ✅')
            else:
                print(f'  {speed}: {time_sec:.1f}s ❌ (will timeout)')
    
    print()
    
    # Recommendations
    print('💡 RECOMMENDATIONS:')
    
    video_file = os.path.join(workspace_dir, 'source.mp4')
    if os.path.exists(video_file):
        size_mb = os.path.getsize(video_file) / (1024*1024)
        if size_mb > 15:
            print('  ⚠️  Video file is large - consider compressing')
            print('  ⚠️  Increase upload timeout to 300s (5 min)')
            print('  ⚠️  Try publishing to fewer platforms at once')
    
    print('  🔧 Check internet connection stability')
    print('  🔧 Monitor upload progress in terminal')
    print('  🔧 If stuck, kill process and try again')
    
    print()
    print('🎯 NEXT STEPS:')
    print('1. Kill current process (Ctrl+C)')
    print('2. Check internet speed')
    print('3. Try with smaller video or increase timeout')
    print('4. Monitor the upload progress carefully')

if __name__ == "__main__":
    diagnose_publishing_hang()
