#!/usr/bin/env python3
"""Generate a voiceover MP3 from text using the ElevenLabs REST API.

Stdlib only (urllib) so it runs anywhere with no `pip install`. Reads the API
key from the ELEVENLABS_API_KEY environment variable. Voice settings come from
--config (a JSON file) and/or explicit flags; flags win over config.

Usage:
    python3 elevenlabs_tts.py --text-file script.txt --voice-id VID --output voiceover.mp3
    python3 elevenlabs_tts.py --text "Hello world" --config config.json

On success prints a JSON line: {"output": "...", "bytes": N, "voice_id": "..."}
Exit code is non-zero on any failure.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.elevenlabs.io/v1/text-to-speech"


def load_config(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh).get("elevenlabs", {})


def main():
    ap = argparse.ArgumentParser(description="ElevenLabs text-to-speech → MP3")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Inline text to speak")
    src.add_argument("--text-file", help="Path to a UTF-8 text file to speak")
    ap.add_argument("--voice-id", help="ElevenLabs voice id (or set in config)")
    ap.add_argument("--model", help="Model id, e.g. eleven_multilingual_v2")
    ap.add_argument("--output", default="voiceover.mp3", help="Output MP3 path")
    ap.add_argument("--output-format", help="e.g. mp3_44100_128")
    ap.add_argument("--config", help="JSON config file (elevenlabs.* keys)")
    ap.add_argument("--stability", type=float)
    ap.add_argument("--similarity-boost", type=float)
    ap.add_argument("--style", type=float)
    args = ap.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ERROR: ELEVENLABS_API_KEY is not set in the environment.")

    cfg = load_config(args.config)
    cfg_settings = cfg.get("voice_settings", {}) or {}

    voice_id = args.voice_id or cfg.get("voice_id")
    if not voice_id:
        sys.exit("ERROR: no voice id (pass --voice-id or set elevenlabs.voice_id in config).")

    model_id = args.model or cfg.get("model_id", "eleven_multilingual_v2")
    output_format = args.output_format or cfg.get("output_format", "mp3_44100_128")

    if args.text is not None:
        text = args.text
    else:
        with open(args.text_file, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    if not text:
        sys.exit("ERROR: the text to speak is empty.")

    def pick(flag, key, default):
        return flag if flag is not None else cfg_settings.get(key, default)

    voice_settings = {
        "stability": pick(args.stability, "stability", 0.5),
        "similarity_boost": pick(args.similarity_boost, "similarity_boost", 0.75),
        "style": pick(args.style, "style", 0.0),
        "use_speaker_boost": cfg_settings.get("use_speaker_boost", True),
    }

    body = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings,
    }).encode("utf-8")

    url = f"{API_ROOT}/{voice_id}?output_format={output_format}"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"ERROR: ElevenLabs API {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: could not reach ElevenLabs: {exc.reason}")

    if not audio:
        sys.exit("ERROR: ElevenLabs returned an empty audio body.")

    with open(args.output, "wb") as fh:
        fh.write(audio)

    print(json.dumps({
        "output": args.output,
        "bytes": len(audio),
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": output_format,
    }))


if __name__ == "__main__":
    main()
