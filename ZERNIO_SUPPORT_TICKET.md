# Zernio Large File Upload Support Ticket

## 🚨 ISSUE: Large File Upload Not Working (20-50MB Videos)

### 🔍 Root Cause Identified
**X-Vercel-Error: FUNCTION_PAYLOAD_TOO_LARGE**

The upload endpoint `https://zernio.com/upload/{token}` is hosted on Vercel serverless functions with ~8MB payload limit, making it unsuitable for video shorts (20-50MB).

### 📊 Current Upload Flow Analysis
```
POST /v1/media/upload-token ✅ (works)
PUT https://zernio.com/upload/{token} ❌ (413 at 8.4MB due to Vercel function limit)
POST /v1/media/upload/{token}/check ✅ (returns pending, files: [])
```

### 🎯 Requested Solutions

#### Option A: Direct-to-Storage Upload API (Preferred)
```
POST /v1/media/uploads (enhanced)
→ Returns: {
  "uploadUrl": "https://s3.amazonaws.com/...",
  "headers": {"Content-Type": "video/mp4"},
  "method": "PUT"
}
PUT to storage URL (bypasses Vercel limits)
POST /v1/media/uploads/{id}/complete
→ Returns: {"url": "https://cdn.zernio.com/video.mp4"}
```

#### Option B: External Media URL Support
```
POST /v1/posts with:
{
  "media_items": [{"type": "video", "url": "https://external-cdn.com/video.mp4"}]
}
```

### 📋 Questions for Zernio Support

1. **Direct-to-storage upload API**: Do you have a large file upload API that returns non-zernio.com signed URLs (S3/R2/GCS)?

2. **External URL support**: Can `media_items.url` accept external CDN URLs? Which platforms support this?

3. **Ingest limits**: What's the max file size for external media URLs? Any platform-specific limits?

4. **URL requirements**: Any specific requirements for external URLs (public access, Content-Type, CORS, etc.)?

### 🔧 Technical Details

**413 Response Headers:**
```
Status: 413
Server: Vercel
X-Vercel-Error: FUNCTION_PAYLOAD_TOO_LARGE
X-Vercel-Id: iad1::ljtzf-1775044742350-fc734f591dd1
```

**Test Results:**
- ✅ <4MB: Regular upload works
- ❌ 8.4MB: 413 FUNCTION_PAYLOAD_TOO_LARGE  
- ❌ 23.6MB: 413 FUNCTION_PAYLOAD_TOO_LARGE

**Target Platforms:** TikTok, Instagram Reels, YouTube Shorts

### 🚨 Business Impact
Cannot publish video shorts (20-50MB) which are the primary content type. Current workflow requires manual workarounds.

### 📞 Contact Information
- API Key: sk_b72389ef5c8adebb1b2f6e43496ef424d170c3fa797ae3154452eb0cd53ac213
- Account: Accelerate plan via team owner
- Use case: Automated video short publishing

---

## 📋 COPY-PASTE READY VERSION

Subject: Large File Upload Issue - 413 FUNCTION_PAYLOAD_TOO_LARGE at 8MB

Body:
Hi Zernio Support,

I'm experiencing a 413 Payload Too Large error when trying to upload video files (20-50MB). The error shows "X-Vercel-Error: FUNCTION_PAYLOAD_TOO_LARGE" which indicates the upload endpoint is hitting Vercel's function body limit.

Current upload flow:
POST /v1/media/upload-token ✅ 
PUT https://zernio.com/upload/{token} ❌ (413 at 8.4MB)
POST /v1/media/upload/{token}/check ✅

413 Response Headers:
Server: Vercel
X-Vercel-Error: FUNCTION_PAYLOAD_TOO_LARGE

Questions:
1. Do you have a direct-to-storage upload API for large files that returns S3/R2/GCS signed URLs?
2. Can media_items.url accept external CDN URLs for TikTok/IG/YT Shorts?
3. What's the max file size for external media URLs?
4. Any specific requirements for external URLs?

I need to publish 20-50MB video shorts. Can you provide a large file upload solution?

Thanks!
