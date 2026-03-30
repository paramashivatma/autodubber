#!/usr/bin/env python3
"""Check logs for encoding errors"""

import os

def check_logs():
    log_file = os.path.join("logs", "2026-03-30.txt")
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        print("Recent log entries with encoding issues:")
        print("=" * 60)
        
        for line in lines[-100:]:  # Last 100 lines
            if "ascii" in line and "encode" in line:
                print(f"ENCODING ERROR: {line.strip()}")
            elif "caption" in line and ("FAIL" in line or "RETRY" in line):
                print(f"CAPTION ISSUE: {line.strip()}")
                
    except Exception as e:
        print(f"Error reading logs: {e}")

if __name__ == "__main__":
    check_logs()
