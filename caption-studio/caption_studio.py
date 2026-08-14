#!/usr/bin/env python3
"""
Caption Studio — CapCut-style auto-captions with word-accurate timing.

What CapCut does under the hood: it sends audio to a dedicated speech-
recognition (ASR) model that MEASURES each word's position in the waveform.
This tool does the same thing locally using faster-whisper (OpenAI's Whisper
model on the CTranslate2 runtime) with word-level timestamps and Silero
voice-activity detection — free, offline, no API key, no quota.

Pipeline:  video → extract audio (ffmpeg) → transcribe with word timestamps
           → group words into CapCut-style caption phrases → render styled
           .ass subtitles (+ .srt) → burn into the video with ffmpeg.

Usage:
    python3 caption_studio.py video.mp4
    python3 caption_studio.py video.mp4 --style karaoke --words 4
    python3 caption_studio.py video.mp4 --srt-only          # just make files
    python3 caption_studio.py video.mp4 --engine gemini     # API fallback

Requires: ffmpeg on PATH, `pip install faster-whisper`.
Gemini fallback requires GEMINI_API_KEY env var or --gemini-key.
"""

import argparse
import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

# ────────────────────────────────────────────────────────────────────────────
# Audio extraction
# ────────────────────────────────────────────────────────────────────────────

def extract_audio(video_path: str, out_wav: str) -> float:
    """Extract 16 kHz mono WAV (what Whisper expects). Returns duration (s)."""
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_wav])
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", out_wav],
        capture_output=True, text=True, check=True)
    return float(probe.stdout.strip())


def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {res.stderr.strip()[:400]}")
    return res


# ────────────────────────────────────────────────────────────────────────────
# Engine 1 (primary): faster-whisper — measured word-level timestamps
# ────────────────────────────────────────────────────────────────────────────

def transcribe_whisper(wav_path: str, model_size: str, language: str):
    """Returns list of {word, start, end}. This is the CapCut-class engine:
    a real ASR model measuring timing from the waveform, with Silero VAD
    trimming silences so timestamps stay anchored to actual speech."""
    from faster_whisper import WhisperModel
    print(f"[whisper] loading model '{model_size}' (first run downloads it, then cached)…")
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    print("[whisper] transcribing — word timestamps + VAD on…")
    segments, info = model.transcribe(
        wav_path,
        language=language or None,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        beam_size=5,
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"word": text, "start": float(w.start), "end": float(w.end)})
    print(f"[whisper] {len(words)} words, detected language: {info.language} "
          f"(p={info.language_probability:.2f})")
    return words


# ────────────────────────────────────────────────────────────────────────────
# Engine 2 (fallback): Gemini API — estimated phrase timestamps
# ────────────────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent?key={key}")


def transcribe_gemini(wav_path: str, api_key: str, duration: float):
    """Fallback when whisper can't run. Gemini ESTIMATES timing (an LLM can't
    measure audio), so accuracy is lower — chunks are kept short (20 s) to
    bound drift. Returns word list with timing interpolated inside phrases."""
    words = []
    chunk = 20.0
    n = max(1, math.ceil(duration / chunk))
    for i in range(n):
        start = i * chunk
        end = min((i + 1) * chunk, duration)
        print(f"[gemini] chunk {i + 1}/{n} ({start:.0f}s → {end:.0f}s)…")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            piece = tf.name
        try:
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                 "-ss", str(start), "-to", str(end), "-c:a", "pcm_s16le", piece])
            segs = _gemini_chunk(piece, api_key, end - start)
            for s in segs:
                seg_words = s["text"].split()
                if not seg_words:
                    continue
                dur = max(0.2, s["end"] - s["start"])
                per = dur / len(seg_words)
                for j, w in enumerate(seg_words):
                    words.append({
                        "word": w,
                        "start": start + s["start"] + j * per,
                        "end": start + s["start"] + (j + 1) * per,
                    })
        finally:
            os.unlink(piece)
    print(f"[gemini] {len(words)} words (estimated timing — prefer whisper engine)")
    return words


def _gemini_chunk(piece_path: str, api_key: str, dur: float):
    with open(piece_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "audio/wav", "data": b64}},
            {"text": (
                f"Listen to this {dur:.1f}-second clip and transcribe it with "
                "timestamps. Split speech into phrases of 3-8 words. For each "
                "phrase give start and end in seconds from the start of THIS "
                "clip, reflecting when words are ACTUALLY spoken (mind the "
                "pauses). Times increase monotonically, max "
                f"{dur:.1f}. Empty array if no speech.")},
        ]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "NUMBER"},
                        "end": {"type": "NUMBER"},
                        "text": {"type": "STRING"},
                    },
                    "required": ["start", "end", "text"],
                    "propertyOrdering": ["start", "end", "text"],
                },
            },
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    req = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_MODEL, key=api_key),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.load(res)
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    items = json.loads(raw)
    out, last_end = [], 0.0
    for it in items:
        try:
            s, e, t = float(it["start"]), float(it["end"]), str(it["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not t or s > dur + 1:
            continue
        s = max(last_end, max(0.0, min(s, dur)))
        e = max(s + 0.3, min(e, dur + 0.5))
        out.append({"start": s, "end": e, "text": t})
        last_end = e
    return out


# ────────────────────────────────────────────────────────────────────────────
# Caption grouping — CapCut-style short phrases
# ────────────────────────────────────────────────────────────────────────────

def group_captions(words, max_words=4, max_dur=3.0, gap_split=0.6):
    """Group the word stream into caption phrases the way CapCut does:
    short (default 4 words), never longer than max_dur seconds, and always
    starting a new caption after a speech pause (> gap_split seconds)."""
    captions = []
    buf = []
    for w in words:
        if buf:
            gap = w["start"] - buf[-1]["end"]
            dur = w["end"] - buf[0]["start"]
            ends_clause = bool(re.search(r"[.!?,;:]$", buf[-1]["word"]))
            if (len(buf) >= max_words or dur > max_dur or gap > gap_split
                    or (ends_clause and len(buf) >= 2)):
                captions.append(buf)
                buf = []
        buf.append(w)
    if buf:
        captions.append(buf)
    out = []
    for group in captions:
        out.append({
            "start": group[0]["start"],
            "end": group[-1]["end"],
            "words": group,
            "text": " ".join(w["word"] for w in group),
        })
    # Hold each caption on screen through short gaps (CapCut does the same) —
    # capped so a long silence doesn't pin stale text.
    for i in range(len(out) - 1):
        gap = out[i + 1]["start"] - out[i]["end"]
        if gap > 0.05:
            out[i]["end"] = min(out[i]["end"] + 1.0, out[i + 1]["start"] - 0.02)
    return out


# ────────────────────────────────────────────────────────────────────────────
# Renderers — SRT + styled ASS (CapCut-inspired presets)
# ────────────────────────────────────────────────────────────────────────────

def ts_srt(t):
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def ts_ass(t):
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_srt(captions, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(captions, 1):
            f.write(f"{i}\n{ts_srt(c['start'])} --> {ts_srt(c['end'])}\n{c['text']}\n\n")


# Colours are ASS &HAABBGGRR (blue-green-red). Orange #F28C28 → &H00288CF2.
STYLES = {
    # White bold text on an orange box — the classic CapCut look from
    # Kevin's videos ("vlog is part of a fundraiser").
    "orange-pill": {
        "primary": "&H00FFFFFF", "back": "&H00288CF2",
        "outline_colour": "&H00288CF2", "border_style": 4,
        "outline": 6, "shadow": 0, "highlight": None,
    },
    "dark-pill": {
        "primary": "&H00FFFFFF", "back": "&HB4000000",
        "outline_colour": "&HB4000000", "border_style": 4,
        "outline": 6, "shadow": 0, "highlight": None,
    },
    # White text, black outline, the CURRENT word turns orange as it is
    # spoken — CapCut's word-highlight / karaoke caption.
    "karaoke": {
        "primary": "&H00FFFFFF", "back": "&H00000000",
        "outline_colour": "&H00000000", "border_style": 1,
        "outline": 3, "shadow": 1, "highlight": "&H00288CF2",
    },
    # Plain white with black outline (no box).
    "outline": {
        "primary": "&H00FFFFFF", "back": "&H00000000",
        "outline_colour": "&H00000000", "border_style": 1,
        "outline": 3, "shadow": 1, "highlight": None,
    },
}


def write_ass(captions, path, style_name, video_w, video_h, font_scale=1.0):
    st = STYLES[style_name]
    font_size = int(video_h * 0.055 * font_scale)
    margin_v = int(video_h * 0.12)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial,{font_size},{st['primary']},&H00FFFFFF,{st['outline_colour']},{st['back']},-1,0,0,0,100,100,0,0,{st['border_style']},{st['outline']},{st['shadow']},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if st["highlight"]:
        # Word-highlight mode: one Dialogue event per word, whole phrase
        # visible, active word recoloured. Timing comes straight from the
        # measured word timestamps.
        hi = st["highlight"]
        for c in captions:
            words = c["words"]
            for i, w in enumerate(words):
                start = w["start"] if i > 0 else c["start"]
                end = words[i + 1]["start"] if i + 1 < len(words) else c["end"]
                if end <= start:
                    continue
                parts = []
                for j, other in enumerate(words):
                    token = other["word"].replace("{", "").replace("}", "")
                    if j == i:
                        parts.append(f"{{\\c{hi}}}{token}{{\\c{st['primary']}}}")
                    else:
                        parts.append(token)
                text = " ".join(parts)
                lines.append(f"Dialogue: 0,{ts_ass(start)},{ts_ass(end)},Cap,,0,0,0,,{text}")
    else:
        for c in captions:
            text = c["text"].replace("{", "").replace("}", "")
            lines.append(f"Dialogue: 0,{ts_ass(c['start'])},{ts_ass(c['end'])},Cap,,0,0,0,,{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")


def video_dimensions(video_path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, check=True)
    w, h = probe.stdout.strip().split("\n")[0].split(",")[:2]
    return int(w), int(h)


def burn_in_dir(video_path, ass_path, out_path):
    # The ass filter argument needs escaping for quotes/colons in paths —
    # sidestep that entirely by running ffmpeg from the .ass file's directory.
    ass_dir = os.path.dirname(os.path.abspath(ass_path)) or "."
    res = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.abspath(video_path),
         "-vf", f"ass={os.path.basename(ass_path)}",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-c:a", "copy", os.path.abspath(out_path)],
        cwd=ass_dir, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("ffmpeg burn failed: " + res.stderr.strip()[:400])


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="CapCut-style word-accurate captions")
    p.add_argument("video", help="input video file")
    p.add_argument("--style", choices=list(STYLES), default="orange-pill",
                   help="caption style preset (default: orange-pill)")
    p.add_argument("--words", type=int, default=4,
                   help="max words per caption (default 4, like CapCut)")
    p.add_argument("--model", default="small.en",
                   help="whisper model: tiny.en/base.en/small.en/medium.en/"
                        "large-v3 (default small.en)")
    p.add_argument("--language", default="en", help="spoken language (default en)")
    p.add_argument("--engine", choices=["whisper", "gemini"], default="whisper",
                   help="whisper = local, free, word-accurate (default); "
                        "gemini = API fallback with estimated timing")
    p.add_argument("--gemini-key", default=os.environ.get("GEMINI_API_KEY", ""),
                   help="Gemini API key (or set GEMINI_API_KEY)")
    p.add_argument("--font-scale", type=float, default=1.0,
                   help="caption size multiplier (default 1.0)")
    p.add_argument("--srt-only", action="store_true",
                   help="write .srt/.ass only, skip burning the video")
    p.add_argument("--out", default="", help="output video path")
    args = p.parse_args()

    base = os.path.splitext(args.video)[0]
    out_video = args.out or f"{base}_captioned.mp4"
    srt_path, ass_path = f"{base}.srt", f"{base}.ass"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = tf.name
    try:
        print("[audio] extracting…")
        duration = extract_audio(args.video, wav)
        print(f"[audio] {duration:.1f}s")

        if args.engine == "whisper":
            try:
                words = transcribe_whisper(wav, args.model, args.language)
            except Exception as e:
                if not args.gemini_key:
                    raise SystemExit(
                        f"whisper engine failed ({e}) and no Gemini key set. "
                        "Install with: pip install faster-whisper — or pass "
                        "--engine gemini --gemini-key AIza…")
                print(f"[whisper] failed ({e}) — falling back to Gemini")
                words = transcribe_gemini(wav, args.gemini_key, duration)
        else:
            if not args.gemini_key:
                raise SystemExit("--engine gemini needs --gemini-key or GEMINI_API_KEY")
            words = transcribe_gemini(wav, args.gemini_key, duration)

        if not words:
            raise SystemExit("No speech found in the video.")

        captions = group_captions(words, max_words=args.words)
        print(f"[captions] {len(captions)} caption phrases")

        write_srt(captions, srt_path)
        w, h = video_dimensions(args.video)
        write_ass(captions, ass_path, args.style, w, h, args.font_scale)
        print(f"[files] {srt_path}  {ass_path}")

        if not args.srt_only:
            print(f"[burn] rendering {out_video} …")
            burn_in_dir(args.video, ass_path, out_video)
            print(f"[done] {out_video}")
        else:
            print("[done] caption files written (no burn requested)")
    finally:
        os.unlink(wav)


if __name__ == "__main__":
    main()
