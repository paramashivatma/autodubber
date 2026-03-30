#!/usr/bin/env python3
"""Debug recent logs to see actual format"""

import os
import re
from datetime import datetime, timedelta

def get_recent_logs():
    """Get recent log entries"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print("No logs directory found")
        return
    
    # Find today's log file
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"{today}.txt")
    
    if not os.path.exists(log_file):
        print(f"No log file for today: {log_file}")
        return
    
    # Read last 200 lines
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except:
        try:
            with open(log_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()
        except:
            print(f"Could not read log file: {log_file}")
            return
    
    recent_lines = lines[-200:] if len(lines) > 200 else lines
    
    print("Recent log entries (last 200 lines):")
    print("=" * 80)
    
    for line in recent_lines:
        print(line.rstrip())
    
    # Test regex patterns
    print("\n" + "=" * 80)
    print("Testing regex patterns on recent logs:")
    print("=" * 80)
    
    log_text = "\n".join(recent_lines)
    
    # Test video title patterns
    download_pattern = r'DOWNLOAD\].*?→\s*(.+?\.mp4)'
    output_pattern = r'output\.mp4|workspace[\\/]([^\s\]]+\.mp4)'
    
    print(f"\n1. Video title patterns:")
    print(f"   DOWNLOAD pattern: {download_pattern}")
    download_matches = re.findall(download_pattern, log_text, re.IGNORECASE)
    print(f"   DOWNLOAD matches: {download_matches}")
    
    print(f"   OUTPUT pattern: {output_pattern}")
    output_matches = re.findall(output_pattern, log_text)
    print(f"   OUTPUT matches: {output_matches}")
    
    # Test language pattern
    lang_pattern = r'Lang detected:\s*(\w{2})'
    print(f"\n2. Language pattern: {lang_pattern}")
    lang_matches = re.findall(lang_pattern, log_text)
    print(f"   Language matches: {lang_matches}")
    
    # Test YouTube URL pattern
    yt_pattern = r'youtube\s+OK\s*-?\s*id[:\s]+(\w+)'
    print(f"\n3. YouTube URL pattern: {yt_pattern}")
    yt_matches = re.findall(yt_pattern, log_text, re.IGNORECASE)
    print(f"   YouTube matches: {yt_matches}")

if __name__ == "__main__":
    get_recent_logs()
