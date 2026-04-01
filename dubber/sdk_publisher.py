"""
Simple Zernio SDK Publisher
Replaces complex custom publishing with official SDK
"""

import os
from zernio import Zernio
from dubber.utils import log, PLATFORM_ACCOUNTS

def publish_with_sdk(api_key, captions, platforms, upload_results=None, 
                    scheduled_for=None, publish_now=True, teaser_captions=None, 
                    output_dir="workspace", progress_cb=None, fallback_files=None):
    """
    Publish to all platforms using official Zernio SDK
    """
    try:
        # Initialize Zernio client
        client = Zernio(api_key=api_key)
        log("PUBLISH", "✅ Zernio SDK initialized")
        
        if progress_cb:
            progress_cb(0, len(platforms), "sdk", "initializing")
        
        # Prepare media URLs - upload video if needed
        media_urls = []
        if upload_results:
            # Add main video
            main_video_url = upload_results.get("main_video")
            if main_video_url:
                media_urls.append(main_video_url)
                log("PUBLISH", f"  ✅ Main video: {main_video_url[:50]}...")
            
            # Add teaser videos
            for platform, teaser_url in upload_results.items():
                if platform.startswith("teaser_") and teaser_url:
                    media_urls.append(teaser_url)
                    log("PUBLISH", f"  ✅ Teaser {platform}: {teaser_url[:50]}...")
        
        # If no media URLs, we need to upload the video
        if not media_urls and fallback_files:
            log("PUBLISH", "🔄 Uploading media files...")
            main_video_path = fallback_files.get("main_video")
            if main_video_path and os.path.exists(main_video_path):
                try:
                    result = client.media.upload(main_video_path)
                    media_urls.append(result["publicUrl"])
                    log("PUBLISH", f"  ✅ Uploaded main video: {result['publicUrl'][:50]}...")
                except Exception as e:
                    log("PUBLISH", f"  ❌ Upload failed: {e}")
                    return {"error": f"Media upload failed: {e}"}
        
        # Get default content (use first available caption as fallback)
        default_content = ""
        platform_specific_contents = {}
        
        for platform, platform_data in captions.items():
            if isinstance(platform_data, dict) and platform_data.get("caption"):
                caption_text = platform_data["caption"]
                if not default_content:
                    default_content = caption_text  # First one becomes default
                # Store platform-specific content (will be used if different from default)
                platform_specific_contents[platform] = caption_text
            elif isinstance(platform_data, str):
                if not default_content:
                    default_content = platform_data  # First one becomes default
                platform_specific_contents[platform] = platform_data
        
        if not default_content:
            default_content = "Published via AutoDubber"
        
        # Prepare platform list
        platform_list = []
        for platform in platforms:
            account_id = PLATFORM_ACCOUNTS.get(platform)
            if account_id:
                platform_entry = {
                    "platform": platform,
                    "accountId": account_id
                }
                
                # Add platform-specific content if different from default
                platform_content = platform_specific_contents.get(platform, "")
                if platform_content and platform_content != default_content:
                    platform_entry["platformSpecificContent"] = platform_content
                
                # Add YouTube-specific fields
                if platform == "youtube":
                    yt_data = captions.get("youtube", {})
                    if isinstance(yt_data, dict) and yt_data.get("title"):
                        platform_entry["youtubeTitle"] = yt_data["title"]
                
                platform_list.append(platform_entry)
                log("PUBLISH", f"  ✅ {platform}: {account_id}")
            else:
                log("PUBLISH", f"  ❌ {platform}: No account ID configured")
        
        if not platform_list:
            error_msg = "No valid platform accounts configured"
            log("PUBLISH", f"❌ {error_msg}")
            return {"error": error_msg}
        
        if progress_cb:
            progress_cb(1, len(platforms), "sdk", "uploading_media")
        
        if progress_cb:
            progress_cb(2, len(platforms), "sdk", "creating_post")
        
        # Create the post using SDK
        post_data = {
            "content": default_content,
            "platforms": platform_list,
            "publish_now": publish_now,
        }
        
        # Add scheduling if provided
        if scheduled_for:
            post_data["scheduled_for"] = scheduled_for
        
        log("PUBLISH", f"🚀 Creating post for {len(platform_list)} platforms...")
        log("PUBLISH", f"  Content: {default_content[:100]}...")
        log("PUBLISH", f"  Media: {len(media_urls)} files")
        
        # Create the post - media_urls passed as separate parameter
        if media_urls:
            post_result = client.posts.create(media_urls=media_urls, **post_data)
        else:
            post_result = client.posts.create(**post_data)
        
        if progress_cb:
            progress_cb(len(platforms), len(platforms), "sdk", "completed")
        
        # Extract results
        post = post_result.get("post", {})
        published_platforms = post.get("platforms", [])
        
        results = {}
        for platform_info in published_platforms:
            platform_name = platform_info.get("platform", "unknown")
            post_id = platform_info.get("id", "unknown")
            status = "ok" if post_id != "unknown" else "error"
            
            results[platform_name] = {
                "status": status,
                "post_id": post_id,
                "platform": platform_name
            }
            
            log("PUBLISH", f"  ✅ {platform_name}: {status} (ID: {post_id})")
        
        log("PUBLISH", f"🎉 SDK publishing completed! {len(results)} platforms")
        return results
        
    except Exception as e:
        error_msg = f"SDK publishing failed: {str(e)}"
        log("PUBLISH", f"❌ {error_msg}")
        if progress_cb:
            progress_cb(len(platforms), len(platforms), "sdk", "error")
        return {"error": error_msg}

# Simple wrapper function for app.py
def publish_to_platforms_sdk(api_key, video_path, captions, platforms,
                            scheduled_for=None, publish_now=True,
                            teaser_path=None, teaser_paths=None,
                            teaser_captions=None, image_paths=None,
                            output_dir="workspace", progress_cb=None):
    """
    Simplified publishing using Zernio SDK
    """
    # For now, we'll use upload_results if available, otherwise fallback to direct upload
    return publish_with_sdk(
        api_key=api_key,
        captions=captions,
        platforms=platforms,
        scheduled_for=scheduled_for,
        publish_now=publish_now,
        output_dir=output_dir,
        progress_cb=progress_cb
    )
