# Caption Studio — CapCut-style captions with word-accurate timing

A command-line app that puts captions on Kevin's videos with the same
accuracy as CapCut's auto-captions, for free, on your own machine.

## Why this is as accurate as CapCut

CapCut's auto-captions work by sending audio to ByteDance's dedicated
speech-recognition (ASR) models, which **measure** each word's position in
the audio waveform. They don't estimate — they align.

This tool does the same thing locally with **faster-whisper** (OpenAI's
Whisper speech model): word-level timestamps measured from the waveform,
plus Silero voice-activity detection so silences never throw the timing
off. This is a completely different class of accuracy from asking an LLM
(like Gemini) to guess timings — a language model can't measure audio,
an ASR model can.

| | CapCut | Caption Studio | Gemini-only |
|---|---|---|---|
| How timing is made | measured (cloud ASR) | measured (local ASR) | estimated (LLM) |
| Word-level accuracy | ✓ | ✓ | ✗ (drifts) |
| Cost | subscription for Pro styles | free | free tier |
| Runs offline | ✗ | ✓ (after model download) | ✗ |

## Setup (one time)

On the Mac:

```bash
brew install ffmpeg
pip3 install faster-whisper
```

## Use

```bash
python3 caption_studio.py "Episode_2036_Full_Episode.mp4"
```

That produces:

- `Episode_2036_Full_Episode_captioned.mp4` — captions burned in
- `Episode_2036_Full_Episode.srt` — standard subtitles (imports into
  CapCut, Premiere, YouTube, etc. if you want to style them there instead)
- `Episode_2036_Full_Episode.ass` — the styled captions used for burning

The first run downloads the speech model (~500 MB for the default
`small.en`), after that everything is offline and instant to start.

## Styles (CapCut-inspired presets)

```bash
--style orange-pill   # white bold text on orange box (default — Kevin's look)
--style karaoke       # white text, the word being spoken turns orange
--style dark-pill     # white text on translucent black box
--style outline       # plain white with black outline
```

## Options

```bash
--words 4            # max words per caption (CapCut uses short phrases)
--model small.en     # tiny.en (fastest) → large-v3 (most accurate)
--font-scale 1.2     # bigger captions
--srt-only           # just write .srt/.ass, don't render the video
--out result.mp4     # choose the output name
```

Model guide: `tiny.en` transcribes a 9-minute episode in well under a
minute on an M-series Mac but makes more word mistakes; `small.en`
(default) is the sweet spot; `medium.en` or `large-v3` for maximum
accuracy on tricky audio. **Timing accuracy is excellent on all of them**
— model size mainly affects word spelling, not timing.

## Gemini fallback

If faster-whisper can't be installed on a machine, the Gemini API key can
be used instead — but know that its timing is estimated, not measured:

```bash
python3 caption_studio.py video.mp4 --engine gemini --gemini-key "AIza…"
# or: export GEMINI_API_KEY="AIza…"
```

The tool also falls back to Gemini automatically if the whisper engine
fails and a key is available.

## How it fits the Content Machine

This replaces the transcription half of the web app's "Burn subtitles into
export" feature with studio-grade output. Typical flow: export the
combined video (intro + main) from the web app **without** subtitles, then
run Caption Studio on the result. Captions are timed against the actual
audio of the final video, so the intro insert can never knock them out of
sync.
