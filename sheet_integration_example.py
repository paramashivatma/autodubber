"""Example: Run sheet logger after successful publish.

Add this to your pipeline after publish_to_platforms() succeeds:
"""
import os
from dubber import publish_to_platforms, quick_update_from_publish_result, log
from dubber.sheet_logger import update_video_tracker

def run_pipeline_with_sheet_logging():
    """Example showing how to integrate sheet logging after publish."""
    
    # ... your pipeline code ...
    # After successful publish:
    
    # Option 1: Use publish results dict directly (recommended)
    publish_results = {
        "youtube": {"post_id": "abc123", "url": "https://youtube.com/shorts/abc123"},
        "instagram": {"post_id": "def456", "url": "https://instagram.com/p/def456"},
        # ... other platforms
    }
    
    success, msg = quick_update_from_publish_result(
        video_title="C Paramashivatma dubguiv4gui.mp4",
        publish_results=publish_results,
        duration="00:44",
        source_lang="ta",
        target_lang="gu",
    )
    log("SHEET", msg)
    
    # Option 2: Parse from log buffer (if you capture logs)
    log_buffer = []  # Your captured log lines
    success, msg = update_video_tracker(log_buffer)
    log("SHEET", msg)


# Integration for auto_publish.py or app.py after ReviewDialog approval:
"""
# In your done callback after publish_to_platforms_async:

async def publish_and_log(video_path, captions, teasers):
    # Publish to platforms
    results = await publish_to_platforms_async(
        video_path=video_path,
        captions=captions,
        teasers=teasers,
    )
    
    # Log to Google Sheet
    from dubber.sheet_logger import quick_update_from_publish_result
    
    video_title = os.path.basename(video_path)
    
    # Extract duration from your pipeline data
    duration = "00:44"  # From your build logs
    source_lang = "ta"   # From transcribe
    target_lang = "gu"   # From TTS voice
    
    success, msg = quick_update_from_publish_result(
        video_title=video_title,
        publish_results=results,
        duration=duration,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    
    print(f"[SHEET] {msg}")
    return results
"""
