#!/usr/bin/env python3
"""
Manually update Google Sheet for the last processed video.
Run this to backfill sheet data if auto-update failed.
"""
import os
import json
import glob
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from dubber.sheet_logger import quick_update_from_publish_result

def find_last_video_info():
    """Find the most recently processed video in workspace."""
    workspace = "workspace"
    
    # Find all video files
    videos = glob.glob(os.path.join(workspace, "*.mp4"))
    if not videos:
        print("[ERROR] No videos found in workspace")
        return None
    
    # Get most recent
    latest_video = max(videos, key=os.path.getmtime)
    video_name = os.path.basename(latest_video)
    
    # Check for vision.json to get metadata
    vision_path = os.path.join(workspace, "vision.json")
    title = video_name
    if os.path.exists(vision_path):
        try:
            with open(vision_path, 'r', encoding='utf-8') as f:
                vision = json.load(f)
                title = vision.get('main_topic', video_name)[:50]
        except:
            pass
    
    # Find transcript for duration estimate
    transcript_path = os.path.join(workspace, "transcript.json")
    duration = ""
    if os.path.exists(transcript_path):
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = json.load(f)
                if isinstance(transcript, list) and len(transcript) > 0:
                    last_seg = transcript[-1]
                    duration_sec = last_seg.get('end', 0)
                    duration = f"{int(duration_sec // 60)}:{int(duration_sec % 60):02d}"
        except:
            pass
    
    return {
        'video_title': title,
        'duration': duration,
        'video_path': latest_video,
        'source_lang': os.getenv('DUB_SOURCE_LANG', 'en'),
        'target_lang': os.getenv('DUB_TARGET_LANG', 'gu'),
    }

def main():
    print("[SHEET_BACKFILL] Looking for last processed video...")
    
    info = find_last_video_info()
    if not info:
        print("[ERROR] Could not find video info")
        return
    
    print(f"[SHEET_BACKFILL] Video: {info['video_title']}")
    print(f"[SHEET_BACKFILL] Duration: {info['duration']}")
    
    # Create dummy publish results (since we're backfilling)
    publish_results = {
        'youtube': {'status': 'ready', 'url': 'pending_manual_publish'},
        'instagram': {'status': 'ready', 'url': 'pending_manual_publish'},
        'tiktok': {'status': 'ready', 'url': 'pending_manual_publish'},
        'facebook': {'status': 'ready', 'url': 'pending_manual_publish'},
        'twitter': {'status': 'ready', 'url': 'pending_manual_publish'},
        'threads': {'status': 'ready', 'url': 'pending_manual_publish'},
        'bluesky': {'status': 'ready', 'url': 'pending_manual_publish'},
    }
    
    print("[SHEET_BACKFILL] Updating Google Sheet...")
    try:
        success, msg = quick_update_from_publish_result(
            video_title=info['video_title'],
            publish_results=publish_results,
            duration=info['duration'],
            source_lang=info['source_lang'],
            target_lang=info['target_lang'],
        )
        
        if success:
            print(f"[SHEET_BACKFILL] ✅ SUCCESS: {msg}")
        else:
            print(f"[SHEET_BACKFILL] ❌ FAILED: {msg}")
            
    except Exception as e:
        print(f"[SHEET_BACKFILL] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
