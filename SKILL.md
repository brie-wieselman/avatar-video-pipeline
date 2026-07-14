---
name: avatar-video-pipeline
description: >-
  End-to-end pipeline for producing talking-avatar videos: write/refine a
  script, generate a voiceover with ElevenLabs, render a HeyGen avatar
  (with the avatar ID randomized from a pool), marry the ElevenLabs
  voiceover to the avatar render so lips sync to the real audio, and
  optionally add title cards and HyperFrames overlays. Use whenever the
  user wants to make a spokesperson / talking-head / avatar video, an
  ElevenLabs + HeyGen video, a narrated avatar clip, or asks to "make a
  video" from a script or topic in this style.
---

# Avatar Video Pipeline (ElevenLabs voiceover → HeyGen avatar → titles/HyperFrames)

This skill packages a repeatable production sequence for talking-avatar
videos. It is intentionally **account-agnostic**: nothing is hardcoded to a
single voice or avatar, so it can be shared publicly and run against anyone's
HeyGen + ElevenLabs accounts.

## The pipeline at a glance

```
1. SCRIPT      → write or refine the narration script
2. VOICEOVER   → ElevenLabs text-to-speech  → voiceover.mp3
3. AVATAR PICK → randomize an avatar_id from a pool (dynamic or configured)
4. RENDER      → HeyGen avatar video driven by the ElevenLabs audio (lip-sync)
5. MARRY       → the render already IS the marriage (audio input == final voice)
6. TITLES/HF   → (optional) HyperFrames title cards / lower-thirds / overlays
7. DELIVER     → surface links + save asset ids
```

Run the steps in order. Each step has a "how" section below. Do not skip the
config-loading step — it controls voice, avatar pool, and dimensions.

## Prerequisites (check once, up front)

- **HeyGen** access via the HeyGen MCP server (tools named `create_video_from_avatar`,
  `list_avatar_looks`, `list_avatar_groups`, `create_asset_upload`,
  `complete_asset_upload`, `get_asset`, `get_video`, `list_voices`, etc.).
  If those tools aren't available, tell the user to connect the HeyGen MCP
  server and stop.
- **ElevenLabs** access via an `ELEVENLABS_API_KEY` environment variable. The
  voiceover step calls the ElevenLabs REST API directly through
  `scripts/elevenlabs_tts.py` (Python stdlib only — no pip install). If the key
  is missing, either ask the user to set it, or fall back to HeyGen's built-in
  `create_speech` voice (note the fallback to the user — it changes the voice).
- **(Optional) HyperFrames** for titles/overlays, via the HyperFrames MCP or the
  local `heygen-com/hyperframes` skills. Only needed if titles are requested.

Load `references/config.example.json` and let the user point at their own
`config.json` (or accept overrides in the request). Config keys:

```jsonc
{
  "elevenlabs": {
    "voice_id": "REQUIRED — an ElevenLabs voice id",
    "model_id": "eleven_multilingual_v2",
    "output_format": "mp3_44100_128",
    "voice_settings": { "stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": true }
  },
  "heygen": {
    "avatar_pool": [],            // optional: explicit avatar_id list to randomize from. Empty = discover at runtime.
    "avatar_group_id": null,      // optional: restrict discovery to one avatar group
    "dimension": { "width": 1080, "height": 1920 },  // 1080x1920 vertical / 1920x1080 landscape
    "background": { "type": "color", "value": "#ffffff" },
    "avatar_style": "normal"
  },
  "titles": { "enabled": false, "template": "lower-third" }
}
```

---

## Step 1 — Script

If the user gave a finished script, use it verbatim. Otherwise draft one from
their topic and confirm before spending render credits. Keep the spoken text
clean (no stage directions, no markdown) — it goes straight to TTS. Save the
final text to `voiceover_script.txt` in the working directory.

Rules of thumb: ~150 words per spoken minute; write for the ear (short
sentences, contractions); front-load the hook in the first 3 seconds.

## Step 2 — Voiceover (ElevenLabs)

Generate the audio with the bundled script. It reads the API key from
`ELEVENLABS_API_KEY` and voice settings from the config (or flags):

```bash
python3 scripts/elevenlabs_tts.py \
  --text-file voiceover_script.txt \
  --voice-id "<voice_id>" \
  --model eleven_multilingual_v2 \
  --output voiceover.mp3 \
  --config config.json          # optional; flags override config values
```

The script writes `voiceover.mp3` and prints its duration + path as JSON.
Listen for issues (mispronunciations → fix with phonetic spelling or SSML
breaks in the script, then re-run). Confirm the take before rendering.

**No ElevenLabs key?** Fall back to HeyGen `create_speech` (pick a voice via
`list_voices`) and skip to Step 4 using the returned `audio` asset — but tell
the user you switched voices.

## Step 3 — Randomize the avatar

Pick one avatar id per render so a batch of videos varies:

- **Configured pool** (`heygen.avatar_pool` non-empty): choose uniformly at
  random from that list.
- **Dynamic discovery** (pool empty): call `list_avatar_looks` (optionally
  scoped by `heygen.avatar_group_id` via `list_avatar_groups`), collect the
  usable `avatar_id`/look ids, and choose one at random.

Helper for deterministic, reproducible selection and logging:

```bash
# Pipe HeyGen's avatar list (JSON) in, or pass --pool with a config file.
python3 scripts/pick_avatar.py --config config.json < avatars.json
# → {"avatar_id": "...", "source": "pool|dynamic", "candidates": N}
```

Record the chosen `avatar_id` so the render is reproducible and the user knows
which avatar appeared. If the user pinned a specific avatar in the request,
honor it and skip randomization.

## Step 4 — Render the avatar video (this is the "marrying")

Drive the HeyGen avatar with the **ElevenLabs audio**, not a text script — that
is what marries the voiceover to the video, and it makes the lips sync to the
real audio.

1. **Make the audio reachable by HeyGen.** Upload `voiceover.mp3` as a HeyGen
   asset: `create_asset_upload` → PUT the bytes → `complete_asset_upload`, then
   `get_asset` to get the audio asset id/url. (If HeyGen accepts a public
   `audio_url` directly and the mp3 is already hosted, you may pass the URL
   instead of uploading.)
2. **Call `create_video_from_avatar`** with the audio input (not `input_text`):
   - `avatar_id`: the randomized pick from Step 3
   - voice/audio: the uploaded audio asset (audio-type voice input)
   - `dimension`, `background`, `avatar_style`: from config
3. **Poll `get_video`** until `status == "completed"`; capture the `video_url`.

Because the avatar was rendered *on top of the ElevenLabs track*, the finished
MP4 already contains the married voiceover — no separate mux step is needed.
(If a request ever produces silent video + separate audio, mux with
`ffmpeg -i video.mp4 -i voiceover.mp3 -c:v copy -c:a aac -shortest out.mp4`.)

## Step 5 — Titles & HyperFrames (optional)

Only if the user wants titles/lower-thirds/overlays (`titles.enabled` or an
explicit ask):

- **HyperFrames** (programmable HTML video): compose a title card / lower-third
  / captioned overlay and composite it with the avatar render. In a hosted chat
  client use the HyperFrames MCP (`compose`, `render_video`); on a local machine
  use the `heygen-com/hyperframes` skills (`/hyperframes`, `/hyperframes-cli`).
- **Simple title cards** without HyperFrames: prepend/append a rendered title
  frame, or burn a lower-third with ffmpeg `drawtext`.

See `references/pipeline.md` for concrete title/overlay recipes.

## Step 6 — Deliver

Report back with: the HeyGen video URL, the chosen `avatar_id`, the ElevenLabs
`voice_id`, and any asset ids — so the run is reproducible. If part of a batch,
list each video with its randomized avatar.

---

## Notes & guardrails

- **Cost:** each render spends HeyGen credits and ElevenLabs characters.
  Confirm the script (Step 1) and the voiceover take (Step 2) before rendering.
- **Consent:** only use avatars/voices the user is licensed to use. For custom
  clones, HeyGen requires recorded consent.
- **Secrets:** never hardcode `ELEVENLABS_API_KEY` or HeyGen keys into the
  repo, config, or commits. The key is read from the environment at runtime.
- **Tool names** above are the canonical HeyGen MCP tool names; a given client
  may namespace them (e.g. a server prefix). Match by suffix if needed.
- See `references/pipeline.md` for the detailed runbook and
  `references/config.example.json` for a ready-to-copy config.
