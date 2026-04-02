"""
Simple Zernio SDK Publisher
Replaces complex custom publishing with official SDK
"""

import os
import mimetypes
from zernio import Zernio, ZernioAPIError, ZernioAuthenticationError, ZernioConnectionError, ZernioRateLimitError, ZernioTimeoutError
from dubber.config import get_platform_accounts
from dubber.utils import log, PLATFORM_LIMITS

def _extract_public_url(upload_result):
    """Handle SDK upload responses returned as dicts or typed objects."""
    if isinstance(upload_result, dict):
        if upload_result.get("publicUrl") or upload_result.get("public_url"):
            return upload_result.get("publicUrl") or upload_result.get("public_url")
        files = upload_result.get("files")
        if isinstance(files, list) and files:
            first = files[0]
            if isinstance(first, dict):
                return first.get("url") or first.get("publicUrl") or first.get("public_url")
    direct = getattr(upload_result, "publicUrl", None) or getattr(upload_result, "public_url", None)
    if direct:
        return direct
    files_attr = getattr(upload_result, "files", None)
    if isinstance(files_attr, list) and files_attr:
        first = files_attr[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("publicUrl") or first.get("public_url")
        url_attr = getattr(first, "url", None) or getattr(first, "publicUrl", None) or getattr(first, "public_url", None)
        if url_attr:
            return str(url_attr)
    return None

def _fit_platform_content(platform, text):
    """Clamp content to platform hard limits."""
    content = str(text or "").strip()
    limit = PLATFORM_LIMITS.get(platform)
    if not limit or len(content) <= limit:
        return content
    ellipsis = "..."
    cut = max(0, limit - len(ellipsis))
    return content[:cut].rstrip() + ellipsis


def _is_unconfirmed_publish_error(exc):
    """Errors that may happen after the server accepted a publish request."""
    text = str(exc or "").strip().lower()
    return any(token in text for token in (
        "jsondecodeerror",
        "expecting value: line 1 column 1 (char 0)",
        "forcibly closed by the remote host",
        "winerror 10054",
        "connection reset",
        "remote host closed",
    ))

def _make_unconfirmed_results(platforms, reason, progress_cb=None, done=0, total=None):
    """Return per-platform unconfirmed results and surface progress."""
    total = total or len(platforms)
    results = {}
    for idx, platform in enumerate(platforms, start=1):
        if progress_cb:
            progress_cb(min(done + idx, total), total, platform, "unconfirmed")
        results[platform] = {
            "status": "unconfirmed",
            "platform": platform,
            "error": reason,
            "error_message": reason,
        }
    return results

def _extract_publish_results(post_result, requested_platforms, progress_cb=None, done=0, total=None):
    """Normalize SDK response into the app's publish result format."""
    total = total or len(requested_platforms)
    try:
        log("PUBLISH", f"🔍 Starting response parsing...")
        log("PUBLISH", f"  📊 Response type: {type(post_result)}")
        log("PUBLISH", f"  📄 Response content: {str(post_result)[:200]}...")

        published_platforms = []
        parent_post_id = None

        if hasattr(post_result, 'post'):
            log("PUBLISH", f"  🔗 Found post object")
            post_obj = post_result.post
            parent_post_id = getattr(post_obj, "id", None) or getattr(post_obj, "_id", None)
            if hasattr(post_obj, 'platforms'):
                published_platforms = post_obj.platforms
                log("PUBLISH", f"  📊 Got platforms from post.platforms: {len(published_platforms)}")
                log("PUBLISH", f"  📋 Platform objects: {published_platforms}")
            elif hasattr(post_obj, 'targets'):
                published_platforms = post_obj.targets
                log("PUBLISH", f"  📊 Got platforms from post.targets: {len(published_platforms)}")
            elif hasattr(post_obj, 'results'):
                published_platforms = post_obj.results
                log("PUBLISH", f"  📊 Got platforms from post.results: {len(published_platforms)}")
            else:
                log("PUBLISH", f"  ❌ No platforms attribute on post object")
                log("PUBLISH", f"  🔍 Post object attributes: {[attr for attr in dir(post_obj) if not attr.startswith('_')]}")
        elif isinstance(post_result, dict):
            log("PUBLISH", f"  📦 Response is dict")
            post = post_result.get('post', {})
            parent_post_id = post.get("id") or post.get("_id") or post_result.get("id") or post_result.get("_id")
            published_platforms = (
                post.get('platforms', [])
                or post.get("targets", [])
                or post.get("results", [])
                or post_result.get("platforms", [])
                or post_result.get("targets", [])
                or post_result.get("results", [])
            )
            log("PUBLISH", f"  📊 Got platforms from dict: {len(published_platforms)}")
            log("PUBLISH", f"  📋 Dict keys: {list(post_result.keys())}")
        elif hasattr(post_result, "platforms"):
            published_platforms = getattr(post_result, "platforms")
            parent_post_id = getattr(post_result, "id", None) or getattr(post_result, "_id", None)
            log("PUBLISH", f"  📊 Got platforms from response.platforms: {len(published_platforms)}")
        elif hasattr(post_result, "targets"):
            published_platforms = getattr(post_result, "targets")
            parent_post_id = getattr(post_result, "id", None) or getattr(post_result, "_id", None)
            log("PUBLISH", f"  📊 Got platforms from response.targets: {len(published_platforms)}")
        else:
            log("PUBLISH", f"  ❌ Unknown response format: {type(post_result)}")
            log("PUBLISH", f"  🔍 Available attributes: {[attr for attr in dir(post_result) if not attr.startswith('_')]}")

        log("PUBLISH", f"  📊 Platforms in response: {len(published_platforms)}")

    except Exception as e:
        log("PUBLISH", f"  ❌ Error parsing response: {e}")
        import traceback
        traceback.print_exc()
        published_platforms = []
        parent_post_id = None

    results = {}
    for i, platform_info in enumerate(published_platforms):
        try:
            if hasattr(platform_info, 'platform'):
                platform_name = platform_info.platform
                post_id = getattr(platform_info, 'platformPostId', 'unknown')
                status = getattr(platform_info, 'status', 'unknown')
                error_message = getattr(platform_info, 'errorMessage', None)
            elif isinstance(platform_info, dict):
                platform_name = platform_info.get("platform", "unknown")
                post_id = platform_info.get("platformPostId", platform_info.get("id", platform_info.get("_id", "unknown")))
                status = platform_info.get("status", "unknown")
                error_message = platform_info.get("errorMessage") or platform_info.get("error")
            else:
                platform_name = "unknown"
                post_id = "unknown"
                status = "error"
                error_message = "Unknown platform response format"

            status_l = str(status).lower()
            platform_l = str(platform_name).lower()
            error_text_l = str(error_message or "").lower()
            timeout_like = status_l in {"timeout", "timed_out", "timed-out"} or (
                "timeout" in error_text_l
            )
            duplicate_like = (
                "duplicate content" in error_text_l
                or "already published" in error_text_l
                or "being published" in error_text_l
            )
            bluesky_unconfirmed = platform_l == "bluesky" and (timeout_like or duplicate_like)

            if progress_cb:
                log("PUBLISH", f"  📱 Updating progress: {platform_name} -> {status}")
                if status_l == 'published':
                    progress_cb(min(done + i + 1, total), total, platform_name, "ok")
                elif bluesky_unconfirmed:
                    progress_cb(min(done + i + 1, total), total, platform_name, "unconfirmed")
                elif status_l == 'error' or status_l == 'failed':
                    progress_cb(min(done + i + 1, total), total, platform_name, "error")
                else:
                    progress_cb(min(done + i + 1, total), total, platform_name, "posting")

            hard_fail = status_l in {"error", "failed", "fail", "rejected"}
            success = (not hard_fail) and (
                status_l in {"published", "ok", "success", "submitted", "queued", "processing"}
                or (post_id and post_id != "unknown")
            )
            if bluesky_unconfirmed:
                success = False

            results[platform_name] = {
                "status": "unconfirmed" if bluesky_unconfirmed else ("ok" if success else "error"),
                "post_id": post_id,
                "platform": platform_name
            }
            if bluesky_unconfirmed:
                if duplicate_like:
                    results[platform_name]["error"] = (
                        "Bluesky reported duplicate content. The post may already be live or still settling. "
                        "Verify dashboard/profile before retrying."
                    )
                else:
                    results[platform_name]["error"] = (
                        "Bluesky is taking longer than usual; status unconfirmed. "
                        "Verify dashboard before retrying."
                    )
                results[platform_name]["error_message"] = results[platform_name]["error"]
            elif not success:
                results[platform_name]["error"] = error_message or f"Publish failed with status={status}"
                results[platform_name]["error_message"] = error_message or f"Publish failed with status={status}"

            if success:
                log("PUBLISH", f"  ✅ {platform_name}: ok (ID: {post_id})")
            elif bluesky_unconfirmed:
                log("PUBLISH", f"  ⚠️ {platform_name}: unconfirmed (slow processing)")
            else:
                log("PUBLISH", f"  ❌ {platform_name}: {results[platform_name]['error']}")

        except Exception as e:
            log("PUBLISH", f"  ❌ Error processing platform {platform_info}: {e}")

    if not results and requested_platforms:
        log("PUBLISH", "⚠️ No per-platform statuses returned; marking selected platforms as unconfirmed")
        fallback_post_id = parent_post_id or "submitted"
        for idx, platform in enumerate(requested_platforms, start=1):
            if progress_cb:
                progress_cb(min(done + idx, total), total, platform, "unconfirmed")
            results[platform] = {
                "status": "unconfirmed",
                "post_id": fallback_post_id,
                "platform": platform,
                "error": (
                    "Publish status unconfirmed: per-platform status missing from API response. "
                    "Verify on dashboard before retrying."
                ),
                "error_message": (
                    "Publish status unconfirmed: per-platform status missing from API response. "
                    "Verify on dashboard before retrying."
                ),
            }

    return results

def upload_large_file(client, file_path):
    """Upload large file using direct REST API presigned URL flow (20-50MB support)"""
    
    # Check file size
    file_size = os.path.getsize(file_path)
    log("PUBLISH", f"  📏 File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
    
    try:
        # Step 1: Call REST API directly to get presigned URL
        log("PUBLISH", f"  🔄 Getting presigned URL for {os.path.basename(file_path)}...")
        import requests
        import json
        
        guessed_content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        presign_response = requests.post(
            "https://zernio.com/api/v1/media/presign",
            headers={
                "Authorization": f"Bearer {client.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "filename": os.path.basename(file_path),
                "contentType": guessed_content_type
            },
            timeout=120
        )
        presign_response.raise_for_status()
        
        presign_data = presign_response.json()
        upload_url = presign_data["uploadUrl"]
        public_url = presign_data["publicUrl"]
        
        log("PUBLISH", f"  ✅ Presigned URL received: {upload_url[:50]}...")
        log("PUBLISH", f"  📍 Public URL will be: {public_url[:50]}...")
        
        # Step 2: Upload file bytes directly to storage (bypasses Vercel limits)
        log("PUBLISH", f"  📤 Uploading to direct storage URL...")
        with open(file_path, 'rb') as f:
            upload_response = requests.put(
                upload_url,
                data=f,
                headers={"Content-Type": guessed_content_type},
                timeout=600  # 10 minute timeout for large uploads
            )
            upload_response.raise_for_status()
        
        log("PUBLISH", f"  ✅ File uploaded successfully to direct storage")
        log("PUBLISH", f"  🔗 Public URL: {public_url[:50]}...")
        
        # Step 3: Return the public URL for media_urls=[public_url]
        return public_url
        
    except Exception as e:
        log("PUBLISH", f"  ❌ Presigned upload failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback error message with external hosting option
        error_msg = f"""Direct storage upload failed ({file_size/1024/1024:.1f} MB).

🚨 TECHNICAL ISSUE: {str(e)}

✅ ALTERNATIVE SOLUTIONS:

1. 🌐 EXTERNAL HOSTING (Immediate workaround):
   • Upload to: YouTube, Vimeo, S3, R2, or Vercel Blob
   • Get public URL
   • Use: media_urls=[https://your-cdn.com/video.mp4]

2. 📏 COMPRESS VIDEO:
   • Reduce to under 8MB for regular upload
   • Lower resolution/bitrate

3. 📞 CONTACT ZERNIO SUPPORT:
   • Reference: /api/v1/media/presign endpoint error
   • File size: {file_size/1024/1024:.1f} MB
   • Error: {str(e)}

📝 TEMPORARY: Host externally and use the public URL."""
        
        raise Exception(error_msg)

def publish_with_sdk(api_key, captions, platforms, upload_results=None, 
                    scheduled_for=None, publish_now=True, teaser_captions=None, 
                    output_dir="workspace", progress_cb=None, fallback_files=None):
    """
    Publish to all platforms using official Zernio SDK
    """
    log("PUBLISH", f"🎯 STARTING publish_with_sdk")
    log("PUBLISH", f"  🔑 API Key: {api_key[:10]}..." if api_key else "❌ No API key")
    log("PUBLISH", f"  📱 Platforms: {platforms}")
    log("PUBLISH", f"  📄 Upload results: {list(upload_results.keys()) if upload_results else None}")
    log("PUBLISH", f"  📄 Fallback files: {list(fallback_files.keys()) if fallback_files else None}")
    
    try:
        # Initialize Zernio client with timeout.
        # Bluesky can take noticeably longer for video processing.
        has_bluesky = any(str(p).lower() == "bluesky" for p in (platforms or []))
        sdk_timeout = 360.0 if has_bluesky else 120.0
        log("PUBLISH", f"  🔧 Initializing Zernio client with timeout={sdk_timeout}s...")
        client = Zernio(api_key=api_key, timeout=sdk_timeout)
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
        
        # If no media URLs, we need to upload the video or images
        if not media_urls and fallback_files:
            log("PUBLISH", "🔄 No media URLs found, need to upload files...")
            log("PUBLISH", f"  📄 Fallback files available: {list(fallback_files.keys())}")
            
            # Check if files exist
            for key, path in fallback_files.items():
                exists = os.path.exists(path) if path else False
                size = os.path.getsize(path) if exists and path else 0
                log("PUBLISH", f"  📁 {key}: {path} - {'✅' if exists else '❌'} ({size:,} bytes)")
            
            log("PUBLISH", "🔄 Starting media file upload process...")
            
            # Try video first
            main_video_path = fallback_files.get("main_video")
            if main_video_path and os.path.exists(main_video_path):
                try:
                    # Check file size
                    file_size = os.path.getsize(main_video_path)
                    log("PUBLISH", f"  📏 Video file size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
                    
                    if file_size > 4 * 1024 * 1024:  # 4MB limit - use presigned upload
                        log("PUBLISH", f"  📤 File too large for direct upload, using presigned URL...")
                        video_url = upload_large_file(client, main_video_path)
                    else:
                        result = client.media.upload(main_video_path)
                        video_url = _extract_public_url(result)
                        if not video_url:
                            raise ValueError(f"Upload response missing public URL: {result}")
                    
                    media_urls.append(video_url)  # Add single URL to list
                    log("PUBLISH", f"  ✅ Main video uploaded: {video_url[:50]}...")
                except Exception as e:
                    log("PUBLISH", f"  ❌ Upload failed: {e}")
                    return {"error": f"Media upload failed: {e}"}
            
            # Try images if no video
            elif not main_video_path:
                # Support multiple images
                main_image_path = fallback_files.get("main_image")
                if main_image_path and os.path.exists(main_image_path):
                    try:
                        # Check file size
                        file_size = os.path.getsize(main_image_path)
                        log("PUBLISH", f"  📏 Main image file size: {file_size:,} bytes")
                        
                        if file_size > 4 * 1024 * 1024:  # 4MB limit
                            log("PUBLISH", f"  📤 Main image too large, using upload_large...")
                            img_url = upload_large_file(client, main_image_path)
                        else:
                            result = client.media.upload(main_image_path)
                            img_url = _extract_public_url(result)
                            if not img_url:
                                raise ValueError(f"Upload response missing public URL: {result}")
                        
                        media_urls.append(img_url)
                        log("PUBLISH", f"  ✅ Main image uploaded: {img_url[:50]}...")
                    except Exception as e:
                        log("PUBLISH", f"  ❌ Upload failed: {e}")
                        return {"error": f"Media upload failed: {e}"}
                
                # Additional images
                additional_images = fallback_files.get("additional_images", [])
                for i, img_path in enumerate(additional_images):
                    if img_path and os.path.exists(img_path):
                        try:
                            # Check file size
                            file_size = os.path.getsize(img_path)
                            log("PUBLISH", f"  📏 Image {i+1} file size: {file_size:,} bytes")
                            
                            if file_size > 4 * 1024 * 1024:  # 4MB limit
                                log("PUBLISH", f"  📤 Image {i+1} too large, using upload_large...")
                                img_url = upload_large_file(client, img_path)
                            else:
                                result = client.media.upload(img_path)
                                img_url = _extract_public_url(result)
                                if not img_url:
                                    raise ValueError(f"Upload response missing public URL: {result}")
                            
                            media_urls.append(img_url)
                            log("PUBLISH", f"  ✅ Uploaded additional image {i+1}: {img_url[:50]}...")
                        except Exception as e:
                            log("PUBLISH", f"  ❌ Additional image {i+1} upload failed: {e}")
                            # Continue with other images instead of failing completely
        
        # Get default content (use first available caption as fallback)
        default_content = ""
        platform_specific_contents = {}
        
        for platform, platform_data in captions.items():
            if isinstance(platform_data, dict) and platform_data.get("caption"):
                caption_text = _fit_platform_content(platform, platform_data["caption"])
                if not default_content:
                    default_content = caption_text  # First one becomes default
                # Store platform-specific content (will be used if different from default)
                platform_specific_contents[platform] = caption_text
            elif isinstance(platform_data, str):
                caption_text = _fit_platform_content(platform, platform_data)
                if not default_content:
                    default_content = caption_text  # First one becomes default
                platform_specific_contents[platform] = caption_text
        
        if not default_content:
            default_content = "Published via AutoDubber"

        # Choose a safe shared content baseline for strict platforms.
        strict_selected = [p for p in platforms if p in PLATFORM_LIMITS]
        if strict_selected:
            strictest = min(strict_selected, key=lambda p: PLATFORM_LIMITS.get(p, 10_000))
            strict_caption = platform_specific_contents.get(strictest)
            if strict_caption:
                default_content = strict_caption
            else:
                default_content = _fit_platform_content(strictest, default_content)
        
        # Prepare platform list
        platform_accounts = get_platform_accounts()
        platform_list = []
        for platform in platforms:
            account_id = platform_accounts.get(platform)
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
        
        log("PUBLISH", f"🚀 Creating post for {len(platform_list)} platforms...")
        log("PUBLISH", f"  Content: {default_content[:100]}...")
        log("PUBLISH", f"  Media: {len(media_urls)} files")
        log("PUBLISH", f"  Platforms: {[p['platform'] for p in platform_list]}")
        log("PUBLISH", f"  Publish Now: {publish_now}")
        
        # Debug: Print the exact SDK call
        if media_urls:
            media_items_count = len(media_urls)
            log("PUBLISH", f"  SDK Call: client.posts.create(media_items={media_items_count} items, content={len(default_content)} chars, platforms={len(platform_list)} platforms)")
        else:
            log("PUBLISH", f"  SDK Call: client.posts.create(content={len(default_content)} chars, platforms={len(platform_list)} platforms)")
        
        media_items = [{"type": "video", "url": url} for url in media_urls] if media_urls else None
        if not media_items:
            video_required_platforms = ["youtube", "tiktok"]
            platforms_without_media = [
                p for p in platform_list
                if p["platform"] not in video_required_platforms
            ]
            skipped_video_required = [
                p for p in video_required_platforms
                if any(p2["platform"] == p for p2 in platform_list)
            ]
            if not platforms_without_media:
                error_msg = "No media uploaded but all selected platforms require video (youtube, tiktok)"
                log("PUBLISH", f"❌ {error_msg}")
                return {"error": error_msg}
            if skipped_video_required:
                log("PUBLISH", f"⚠️ Skipped video-required platforms without media: {skipped_video_required}")
            platform_list = platforms_without_media

        results = {}
        processed_count = 0

        for platform_entry in platform_list:
            platform_name = platform_entry["platform"]
            single_content = platform_specific_contents.get(platform_name) or default_content

            if progress_cb:
                progress_cb(processed_count, len(platforms), platform_name, "posting")

            log("PUBLISH", f"🚀 Starting SDK call for {platform_name}...")
            log("PUBLISH", f"  📱 Platform: {platform_name}")
            log("PUBLISH", f"  🎬 Media Items: {len(media_items) if media_items else 0} items")
            log("PUBLISH", f"  ⏰ Publish now: {publish_now}")
            log("PUBLISH", f"  📞 Calling client.posts.create()...")

            try:
                create_kwargs = {
                    "content": single_content,
                    "platforms": [platform_entry],
                    "publish_now": publish_now,
                }
                if media_items:
                    create_kwargs["media_items"] = media_items

                post_result = client.posts.create(**create_kwargs)
                log("PUBLISH", f"  ✅ SDK call successful for {platform_name}: {type(post_result)}")

                if scheduled_for and hasattr(post_result, 'post'):
                    log("PUBLISH", f"⚠️ Scheduling not fully implemented - using immediate publish")

                parsed = _extract_publish_results(
                    post_result,
                    [platform_name],
                    progress_cb=progress_cb,
                    done=processed_count,
                    total=len(platforms),
                )
                results.update(parsed)

            except ZernioAuthenticationError as e:
                log("PUBLISH", f"  ❌ Authentication failed: Invalid API key - {e}")
                raise ZernioAuthenticationError("Invalid Zernio API key. Please check your API key in the settings.")
            except ZernioRateLimitError as e:
                log("PUBLISH", f"  ❌ Rate limit exceeded: {e}")
                raise ZernioRateLimitError("Rate limit exceeded. Please wait before trying again.")
            except ZernioTimeoutError as e:
                reason = (
                    "Publish status unconfirmed: request timed out while the platform may still be processing. "
                    "Verify dashboard before retrying."
                )
                log("PUBLISH", f"  ⚠️ Timeout for {platform_name}: {e}")
                results.update(
                    _make_unconfirmed_results(
                        [platform_name], reason, progress_cb=progress_cb,
                        done=processed_count, total=len(platforms)
                    )
                )
            except ZernioConnectionError as e:
                reason = (
                    "Publish status unconfirmed: connection dropped after submit may have reached the server. "
                    "Verify dashboard before retrying."
                )
                log("PUBLISH", f"  ⚠️ Connection error for {platform_name}: {e}")
                results.update(
                    _make_unconfirmed_results(
                        [platform_name], reason, progress_cb=progress_cb,
                        done=processed_count, total=len(platforms)
                    )
                )
            except ZernioAPIError as e:
                log("PUBLISH", f"  ❌ API error for {platform_name}: {e}")
                if progress_cb:
                    progress_cb(processed_count + 1, len(platforms), platform_name, "error")
                results[platform_name] = {
                    "status": "error",
                    "platform": platform_name,
                    "error": f"Zernio API error: {e}",
                    "error_message": f"Zernio API error: {e}",
                }
            except Exception as sdk_error:
                if _is_unconfirmed_publish_error(sdk_error):
                    reason = (
                        "Publish status unconfirmed: SDK connection closed after submit. "
                        "Verify dashboard before retrying."
                    )
                    log("PUBLISH", f"  ⚠️ Unconfirmed publish outcome for {platform_name}: {sdk_error}")
                    results.update(
                        _make_unconfirmed_results(
                            [platform_name], reason, progress_cb=progress_cb,
                            done=processed_count, total=len(platforms)
                        )
                    )
                else:
                    log("PUBLISH", f"  ❌ Unexpected SDK error for {platform_name}: {sdk_error}")
                    if progress_cb:
                        progress_cb(processed_count + 1, len(platforms), platform_name, "error")
                    results[platform_name] = {
                        "status": "error",
                        "platform": platform_name,
                        "error": str(sdk_error),
                        "error_message": str(sdk_error),
                    }

            processed_count += 1

        if progress_cb:
            progress_cb(len(platforms), len(platforms), "sdk", "completed")

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
                            output_dir="workspace", progress_cb=None, fallback_files=None):
    """
    Simplified publishing using Zernio SDK
    """
    log("PUBLISH", f"🚀 STARTING publish_to_platforms_sdk")
    log("PUBLISH", f"  📹 Video path: {video_path}")
    log("PUBLISH", f"  📱 Platforms: {platforms}")
    log("PUBLISH", f"  📄 Fallback files: {list(fallback_files.keys()) if fallback_files else None}")
    
    try:
        # For now, we'll use upload_results if available, otherwise fallback to direct upload
        result = publish_with_sdk(
            api_key=api_key,
            captions=captions,
            platforms=platforms,
            scheduled_for=scheduled_for,
            publish_now=publish_now,
            output_dir=output_dir,
            progress_cb=progress_cb,
            fallback_files=fallback_files  # Pass through fallback files
        )
        if isinstance(result, dict) and "error" in result and len(result) == 1:
            log("PUBLISH", f"❌ publish_to_platforms_sdk FAILED: {result.get('error')}")
        else:
            has_unconfirmed = False
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, dict) and str(v.get("status", "")).lower() in {"unconfirmed", "submitted_unconfirmed"}:
                        has_unconfirmed = True
                        break
            if has_unconfirmed:
                log("PUBLISH", "⚠️ publish_to_platforms_sdk COMPLETED WITH UNCONFIRMED RESULTS")
            else:
                log("PUBLISH", "✅ publish_to_platforms_sdk COMPLETED")
        return result
    except Exception as e:
        log("PUBLISH", f"❌ publish_to_platforms_sdk FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise e
