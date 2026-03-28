from .utils import log
MIN_DURATION=2.5; MAX_GAP=0.15; MAX_DURATION=12.0

def merge_short_segments(segments):
    if not segments: return segments
    segs=sorted(segments,key=lambda s:s["start"]); merged=[]; current=dict(segs[0])
    for nxt in segs[1:]:
        cur_dur=current["end"]-current["start"]; nxt_dur=nxt["end"]-nxt["start"]
        gap=nxt["start"]-current["end"]; combined=cur_dur+nxt_dur
        if gap<=MAX_GAP and combined<=MAX_DURATION and (cur_dur<MIN_DURATION or nxt_dur<MIN_DURATION):
            current["end"]=nxt["end"]; current["text"]=current["text"].rstrip()+" "+nxt["text"].lstrip()
        else:
            merged.append(current); current=dict(nxt)
    merged.append(current)
    for i,seg in enumerate(merged): seg["id"]=i
    log("SEG_MERGE",f"{len(segs)} -> {len(merged)} segments")
    return merged
