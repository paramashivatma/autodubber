from .utils import log

MIN_THOUGHT_DURATION = 2.2
MAX_THOUGHT_DURATION = 12.0
SOFT_GAP = 0.55
HARD_GAP = 1.1

INCOMPLETE_ENDINGS = (
    ",",
    ":",
    ";",
    "-",
    " and",
    " or",
    " but",
    " so",
    " because",
    " that",
    " which",
    " who",
    " where",
    " when",
    " while",
    " if",
    " then",
    " than",
    " the",
    " a",
    " an",
    " to",
    " of",
    " in",
    " on",
    " for",
    " with",
    " from",
    " by",
    " is",
    " are",
    " was",
    " were",
    " be",
    " it",
    " there",
    " this",
)

CONTINUATION_STARTS = {
    "and",
    "or",
    "but",
    "so",
    "because",
    "that",
    "which",
    "who",
    "where",
    "when",
    "while",
    "then",
    "than",
    "if",
    "to",
    "of",
    "for",
    "with",
    "in",
    "on",
    "by",
    "it",
    "there",
    "this",
    "these",
    "those",
    "he",
    "she",
    "they",
    "you",
    "we",
}


def _first_word(text):
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return ""
    return cleaned.split()[0].strip("\"'([{")


def _is_complete_thought(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    lower = cleaned.lower().rstrip()
    if lower.endswith(("...", ",")):
        return False
    if cleaned.endswith((".", "!", "?")):
        return True
    return not any(lower.endswith(token) for token in INCOMPLETE_ENDINGS)


def _should_merge(current, nxt):
    cur_dur = current["end"] - current["start"]
    nxt_dur = nxt["end"] - nxt["start"]
    combined_dur = nxt["end"] - current["start"]
    gap = nxt["start"] - current["end"]
    protected = current.get("is_gap_probe") or nxt.get("is_gap_probe")

    if combined_dur > MAX_THOUGHT_DURATION:
        return False
    if gap >= HARD_GAP:
        return False
    if protected and gap > 0.18:
        return False

    current_complete = current.get("is_complete_thought", _is_complete_thought(current.get("text")))
    next_starts_like_continuation = _first_word(nxt.get("text")) in CONTINUATION_STARTS
    short_group = cur_dur < MIN_THOUGHT_DURATION or nxt_dur < MIN_THOUGHT_DURATION

    if gap <= 0.12:
        return True
    if (not current_complete or next_starts_like_continuation) and gap <= SOFT_GAP:
        return True
    if short_group and gap <= 0.22:
        return True
    return False


def _build_group(segs):
    start = segs[0]["start"]
    end = segs[-1]["end"]
    text = " ".join((seg.get("text") or "").strip() for seg in segs if (seg.get("text") or "").strip())
    pauses = []
    prev_end = start
    for seg in segs:
        pauses.append(round(max(seg["start"] - prev_end, 0.0), 3))
        prev_end = seg["end"]
    source_segments = [
        {
            "id": seg.get("id"),
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg.get("text", ""),
            "is_gap_probe": bool(seg.get("is_gap_probe")),
        }
        for seg in segs
    ]
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "group_start": round(start, 3),
        "group_end": round(end, 3),
        "text": text,
        "source_segments": source_segments,
        "pause_before": round(segs[0].get("pause_before", 0.0), 3),
        "source_pauses": pauses,
        "is_gap_probe": any(seg.get("is_gap_probe") for seg in segs),
        "is_complete_thought": _is_complete_thought(text),
    }


def merge_short_segments(segments):
    if not segments:
        return segments

    segs = []
    prev_end = 0.0
    for seg in sorted(segments, key=lambda s: s["start"]):
        enriched = dict(seg)
        enriched["pause_before"] = round(max(enriched["start"] - prev_end, 0.0), 3)
        enriched["is_complete_thought"] = _is_complete_thought(enriched.get("text", ""))
        segs.append(enriched)
        prev_end = enriched["end"]

    groups = []
    current_group = [segs[0]]
    for nxt in segs[1:]:
        current = _build_group(current_group)
        if _should_merge(current, nxt):
            current_group.append(nxt)
        else:
            groups.append(_build_group(current_group))
            current_group = [nxt]
    groups.append(_build_group(current_group))

    for i, seg in enumerate(groups):
        seg["id"] = i

    log("SEG_MERGE", f"{len(segs)} -> {len(groups)} thought groups")
    return groups
