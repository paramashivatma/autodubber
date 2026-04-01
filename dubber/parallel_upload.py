#!/usr/bin/env python3
"""
Parallel upload manager - uploads files while user reviews captions
"""

import os
import json
import asyncio
import threading
import time
from datetime import datetime
from dubber.publisher import upload_media

class ParallelUploadManager:
    """Manages parallel file uploads during caption review"""
    
    def __init__(self, api_key, video_path, teaser_paths=None, image_paths=None, mock_mode=False):
        self.api_key = api_key
        self.video_path = video_path
        self.teaser_paths = teaser_paths or {}
        self.image_paths = image_paths or []
        self.mock_mode = mock_mode  # Add mock mode for testing
        
        self.upload_results = {}
        self.upload_status = {}
        self.upload_thread = None
        self.is_running = False
        self.progress_callback = None
        
    def start_uploads(self, progress_callback=None):
        """Start parallel uploads in background thread"""
        if self.is_running:
            return
            
        self.progress_callback = progress_callback
        self.is_running = True
        self.upload_thread = threading.Thread(target=self._run_uploads)
        self.upload_thread.daemon = True
        self.upload_thread.start()
        
    def _run_uploads(self):
        """Run all uploads in parallel"""
        try:
            # Create async event loop
            asyncio.run(self._upload_all_files())
        except Exception as e:
            if self.progress_callback:
                self.progress_callback(f"Upload error: {e}", None, "error")
                
    async def _upload_all_files(self):
        """Upload all files in parallel"""
        
        # Update status
        if self.progress_callback:
            self.progress_callback("Starting parallel uploads...", None, "uploading")
            
        # Create upload tasks
        tasks = []
        
        # Main video upload
        if os.path.exists(self.video_path):
            tasks.append(self._upload_file("main_video", self.video_path))
            
        # Teaser uploads
        for platform, teaser_path in self.teaser_paths.items():
            if os.path.exists(teaser_path):
                tasks.append(self._upload_file(f"teaser_{platform}", teaser_path))
                
        # Image uploads
        for i, img_path in enumerate(self.image_paths):
            if os.path.exists(img_path):
                tasks.append(self._upload_file(f"image_{i}", img_path))
        
        # Wait for all uploads to complete
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results - handle both successful uploads and failures
            successful_uploads = 0
            failed_uploads = 0
            
            for result in results:
                if isinstance(result, Exception):
                    failed_uploads += 1
                    if self.progress_callback:
                        self.progress_callback(f"⚠️ Upload exception: {result}", None, "error")
                elif result is not None:
                    successful_uploads += 1
                    if self.progress_callback:
                        self.progress_callback(f"✅ Upload successful: {result}", None, "ok")
                else:
                    failed_uploads += 1
                    # None result means upload failed but was handled gracefully
            
            # Summary
            if self.progress_callback:
                if successful_uploads > 0:
                    self.progress_callback(
                        f"📊 Upload summary: {successful_uploads} successful, {failed_uploads} failed", 
                        None, 
                        "completed"
                    )
                else:
                    self.progress_callback(
                        f"❌ All uploads failed. Will use fallback mode.", 
                        None, 
                        "error"
                    )
        else:
            if self.progress_callback:
                self.progress_callback("No files to upload", None, "ok")
                
        self.is_running = False
        
    async def _upload_file(self, file_type, file_path):
        """Upload single file and track progress"""
        try:
            if self.progress_callback:
                self.progress_callback(f"Uploading {file_type}...", file_type, "uploading")
            
            start_time = time.time()
            
            # Mock mode for testing
            if self.mock_mode:
                # Simulate upload delay
                await asyncio.sleep(0.5)
                # Generate mock URL
                url = f"https://mock-storage.com/{file_type}_{int(time.time())}.mp4"
                if self.progress_callback:
                    self.progress_callback(
                        f"✅ {file_type} uploaded in 0.5s (mock)", 
                        file_type, 
                        "completed"
                    )
            else:
                # Real upload
                url = upload_media(self.api_key, file_path)
                upload_time = time.time() - start_time
                if self.progress_callback:
                    self.progress_callback(
                        f"✅ {file_type} uploaded in {upload_time:.1f}s", 
                        file_type, 
                        "completed"
                    )
            
            # Store result
            self.upload_results[file_type] = url
            self.upload_status[file_type] = "completed"
            
            return url
            
        except Exception as e:
            self.upload_status[file_type] = "failed"
            # Don't raise exception, handle it gracefully
            if self.progress_callback:
                self.progress_callback(
                    f"⚠️ {file_type} upload failed: {str(e)}", 
                    file_type, 
                    "error"
                )
            # Return None instead of raising
            return None
            
    def get_upload_results(self):
        """Get completed upload results"""
        return self.upload_results.copy()
        
    def get_upload_status(self):
        """Get current upload status"""
        return {
            "is_running": self.is_running,
            "status": self.upload_status.copy(),
            "results": self.upload_results.copy()
        }
        
    def wait_for_uploads(self, timeout=300):
        """Wait for uploads to complete (with timeout)"""
        if not self.is_running:
            return True
            
        start_time = time.time()
        while self.is_running and (time.time() - start_time) < timeout:
            time.sleep(0.5)
            
        return not self.is_running

def create_parallel_upload_manager(api_key, video_path, teaser_paths=None, image_paths=None, mock_mode=False):
    """Factory function to create upload manager"""
    return ParallelUploadManager(api_key, video_path, teaser_paths, image_paths, mock_mode)

def publish_with_preuploaded_urls(api_key, captions, platforms, upload_results,
                                 scheduled_for=None, publish_now=True,
                                 teaser_captions=None, output_dir="workspace",
                                 progress_cb=None, fallback_files=None):
    """
    Publish to platforms using pre-uploaded URLs (no file uploads needed)
    
    Args:
        api_key: Zernio API key
        captions: Platform-specific captions
        platforms: List of platforms to publish to
        upload_results: Dict of pre-uploaded URLs from ParallelUploadManager
        scheduled_for: Optional scheduled datetime
        publish_now: Whether to publish immediately
        teaser_captions: Optional teaser captions
        output_dir: Output directory for lock files
        progress_cb: Progress callback function
        fallback_files: Dict of local file paths for fallback when uploads fail
        
    Returns:
        Dict of platform results
    """
    import os
    import json
    import time
    import requests
    import asyncio
    from dubber.publisher import _build_entry, _write_platform_lock, _json_headers, BASE_URL, upload_media
    
    if not api_key:
        raise RuntimeError("No Zernio API key.")
    if not platforms:
        raise RuntimeError("No platforms selected.")
    
    # Build media items from upload results
    media_items = []
    
    # Add main video
    main_url = upload_results.get("main_video")
    if main_url:
        media_items.append({"url": main_url, "type": "video"})
    elif fallback_files and fallback_files.get("main_video"):
        # Fallback: upload main video now
        if progress_cb:
            progress_cb("Main video upload failed, uploading now...", None, "uploading")
        try:
            main_url = upload_media(api_key, fallback_files["main_video"])
            media_items.append({"url": main_url, "type": "video"})
            if progress_cb:
                progress_cb("✅ Main video uploaded successfully", None, "ok")
        except Exception as e:
            if progress_cb:
                progress_cb(f"❌ Main video upload failed: {e}", None, "error")
            return {"error": f"Main video upload failed: {e}"}
    
    # Add teasers
    for platform in platforms:
        teaser_key = f"teaser_{platform}"
        teaser_url = upload_results.get(teaser_key)
        if teaser_url:
            media_items.append({"url": teaser_url, "type": "video"})
        elif fallback_files and fallback_files.get(teaser_key):
            # Fallback: upload teaser now
            if progress_cb:
                progress_cb(f"Teaser upload failed for {platform}, uploading now...", None, "uploading")
            try:
                teaser_url = upload_media(api_key, fallback_files[teaser_key])
                media_items.append({"url": teaser_url, "type": "video"})
                if progress_cb:
                    progress_cb(f"✅ {platform} teaser uploaded successfully", None, "ok")
            except Exception as e:
                if progress_cb:
                    progress_cb(f"⚠️ {platform} teaser upload failed: {e}", None, "error")
                # Continue without this teaser
    
    # Add images
    for key, url in upload_results.items():
        if key.startswith("image_") and url:
            media_items.append({"url": url, "type": "image"})
        elif fallback_files and fallback_files.get(key):
            # Fallback: upload image now
            if progress_cb:
                progress_cb(f"Image upload failed, uploading now...", None, "uploading")
            try:
                image_url = upload_media(api_key, fallback_files[key])
                media_items.append({"url": image_url, "type": "image"})
                if progress_cb:
                    progress_cb("✅ Image uploaded successfully", None, "ok")
            except Exception as e:
                if progress_cb:
                    progress_cb(f"⚠️ Image upload failed: {e}", None, "error")
                # Continue without this image
    
    if not media_items:
        error_msg = "No media items available and all fallback uploads failed"
        if progress_cb:
            progress_cb(f"❌ {error_msg}", None, "error")
        return {"error": error_msg}
    
    async def _publish_single_platform(api_key, platform, captions, media_items,
                                     publish_now, scheduled_for, output_dir,
                                     progress_cb, done_count, total_count):
        """Publish to single platform using pre-uploaded media"""
        try:
            entry = _build_entry(platform, captions, {})
            if not entry:
                result = {"error": "no account ID configured"}
                if progress_cb:
                    progress_cb(done_count + 1, total_count, platform, "error")
                return platform, result

            payload = {
                "content": "",
                "mediaItems": media_items,
                "platforms": [entry],
            }
            if publish_now:
                payload["publishNow"] = True
            elif scheduled_for:
                payload["scheduledFor"] = scheduled_for

            if progress_cb:
                progress_cb(done_count + 1, total_count, platform, "posting")

            # Run the blocking request in thread pool
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{BASE_URL}/posts",
                    headers=_json_headers(api_key),
                    json=payload,
                    timeout=120,  # 2 minute timeout for posting only
                )
            )

            if r.ok:
                result = r.json()
                post_id = (result.get("post") or {}).get("_id") or result.get("_id", "?")
                _write_platform_lock(output_dir, platform, "ok", post_id=post_id)
                if progress_cb:
                    progress_cb(done_count + 1, total_count, platform, "ok")
                return platform, result
            else:
                err = f"HTTP {r.status_code}: {r.text[:200]}"
                result = {"error": err}
                if progress_cb:
                    progress_cb(done_count + 1, total_count, platform, "error")
                return platform, result

        except Exception as e:
            if progress_cb:
                progress_cb(done_count + 1, total_count, platform, "error")
            return platform, {"error": str(e)}

    async def _publish_all_platforms():
        """Publish to all platforms concurrently"""
        tasks = []
        for i, platform in enumerate(platforms):
            task = _publish_single_platform(
                api_key, platform, captions, media_items,
                publish_now, scheduled_for, output_dir,
                progress_cb, i, len(platforms)
            )
            tasks.append(task)

        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert results to dict
        results = {}
        for result in results_list:
            if isinstance(result, Exception):
                continue
            platform, platform_result = result
            results[platform] = platform_result

        return results

    return asyncio.run(_publish_all_platforms())

def publish_with_preuploaded_urls_sync(api_key, captions, platforms, upload_results,
                                      scheduled_for=None, publish_now=True,
                                      teaser_captions=None, output_dir="workspace",
                                      progress_cb=None, fallback_files=None):
    """
    Sync wrapper for publish_with_preuploaded_urls to work in GUI context
    Uses threading to avoid blocking the GUI thread
    """
    import threading
    import time
    
    result_container = {}
    exception_container = {}
    thread_done = threading.Event()
    
    def run_in_thread():
        try:
            result = publish_with_preuploaded_urls(
                api_key, captions, platforms, upload_results,
                scheduled_for, publish_now, teaser_captions, output_dir,
                progress_cb, fallback_files
            )
            result_container['result'] = result
        except Exception as e:
            exception_container['exception'] = e
        finally:
            thread_done.set()  # Signal that thread is done
    
    # Start thread in background (don't block GUI)
    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True  # Allow main program to exit even if thread is running
    thread.start()
    
    # Wait for thread to complete but allow GUI to remain responsive
    while not thread_done.is_set():
        if progress_cb:
            # Keep GUI responsive by yielding control
            time.sleep(0.1)
        else:
            # If no progress callback, just wait efficiently
            thread_done.wait(timeout=0.1)
    
    # Check for exceptions
    if 'exception' in exception_container:
        raise exception_container['exception']
    
    return result_container.get('result', {})
