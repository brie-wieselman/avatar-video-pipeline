# Detailed runbook — Avatar Video Pipeline

This is the long-form companion to `SKILL.md`. Follow it when you need concrete
tool-call shapes, batch behavior, or title/overlay recipes.

## 0. Setup

1. Confirm HeyGen MCP tools are available (suffixes: `create_video_from_avatar`,
   `list_avatar_looks`, `list_avatar_groups`, `list_voices`, `create_asset_upload`,
   `complete_asset_upload`, `get_asset`, `get_video`). If a client namespaces
   tools with a server prefix, match by suffix.
2. Confirm `ELEVENLABS_API_KEY` is set: `printenv ELEVENLABS_API_KEY | head -c 4`.
3. Copy `references/config.example.json` to a working `config.json` and fill in
   `elevenlabs.voice_id`. Everything else has sane defaults.

## 1. Script

- Given script → use as-is. Topic only → draft, then confirm before rendering.
- Strip anything not meant to be spoken. Save to `voiceover_script.txt`.
- Pacing: ~150 wpm. A 60s vertical clip ≈ 140–160 words.
- SSML/pauses: ElevenLabs honors `<break time="0.5s"/>` inside the text for
  breathing room; use sparingly.

## 2. Voiceover (ElevenLabs)

```bash
python3 scripts/elevenlabs_tts.py \
  --text-file voiceover_script.txt \
  --config config.json \
  --output voiceover.mp3
```

- Flags override config: `--voice-id`, `--model`, `--stability`,
  `--similarity-boost`, `--style`, `--output-format`.
- Output is `voiceover.mp3`; the script prints `{output, bytes, voice_id, ...}`.
- Mispronunciation fix loop: edit the script (phonetic spelling / break tags) →
  re-run → re-listen. Only proceed once the take is clean.

Voice-settings cheat sheet:
- `stability` low (0.2–0.4) = more expressive/variable; high (0.6–0.8) = steadier.
- `similarity_boost` high = closer to the reference voice.
- `style` > 0 = more stylized delivery (costs a bit of stability).

## 3. Randomize the avatar

Dynamic discovery (no configured pool):
1. `list_avatar_groups` (optional) → pick/confirm a group id.
2. `list_avatar_looks` (optionally scoped to that group) → save JSON to
   `avatars.json`.
3. `python3 scripts/pick_avatar.py --config config.json < avatars.json`
   → `{"avatar_id": "...", "source": "dynamic", "candidates": N}`.

Configured pool: set `heygen.avatar_pool` in `config.json` and the same command
picks from it (`source: "pool"`), ignoring stdin.

- `--seed N` makes the pick reproducible (useful for tests / redoing a batch).
- If the user pinned an avatar, skip this and use theirs.
- **Log the chosen id** in your reply so the user knows who appeared.

## 4. Render (marry audio → avatar)

The marriage happens by feeding the ElevenLabs audio into the avatar render as
the voice input, so HeyGen lip-syncs the avatar to the real track.

### 4a. Get the audio to HeyGen

Preferred — upload as an asset:
1. `create_asset_upload` → returns an upload URL / asset id.
2. PUT the bytes of `voiceover.mp3` to that URL (respect the content-type it
   asks for, typically `audio/mpeg`).
3. `complete_asset_upload` → finalize; `get_asset` → the asset id/url to use.

Alternative — if `voiceover.mp3` is already hosted at a public URL and
`create_video_from_avatar` accepts an `audio_url`, pass the URL directly and
skip the upload.

### 4b. Create the video

Call `create_video_from_avatar` with:
- `avatar_id` = the randomized pick (Step 3)
- voice input = **audio** (the uploaded asset), NOT `input_text`
- `dimension` = `config.heygen.dimension`
- `background` = `config.heygen.background`
- `avatar_style` = `config.heygen.avatar_style`

Check the tool's live schema (via ToolSearch) for the exact field names for the
audio voice input — HeyGen expects a `voice` object of type `audio` referencing
the asset, not a text script.

### 4c. Wait for completion

Poll `get_video` on the returned `video_id` until `status == "completed"`;
capture `video_url`. Handle `failed` by surfacing the error to the user.

Because the avatar was rendered on the ElevenLabs track, the finished MP4
already carries the married voiceover. **No separate mux step is needed.** If a
particular path ever yields silent video + separate audio:

```bash
ffmpeg -i video.mp4 -i voiceover.mp3 -c:v copy -c:a aac -shortest final.mp4
```

## 5. Titles & HyperFrames (optional)

Trigger when `titles.enabled` is true or the user explicitly asks for titles /
lower-thirds / captions / an intro-outro card.

### HyperFrames (programmable HTML video)
- Hosted chat client: HyperFrames MCP — `compose` a project (title card,
  lower-third, animated caption) then `render_video`; composite over/around the
  avatar clip.
- Local machine: use the `heygen-com/hyperframes` skills
  (`npx skills add heygen-com/hyperframes`) → `/hyperframes`, `/hyperframes-cli`.

Common shapes:
- **Intro title card**: full-frame animated title, 1.5–2.5s, cut to the avatar.
- **Lower-third**: name/role strip anchored bottom-left, fades in ~1s after the
  avatar starts, out before the end.
- **Kinetic captions**: burned-in word-by-word captions timed to the voiceover
  (transcribe `voiceover.mp3` for timings).

### Without HyperFrames (ffmpeg fallback)
- Prepend a title card:
  ```bash
  ffmpeg -loop 1 -t 2 -i title.png -i avatar.mp4 \
    -filter_complex "[0:v]scale=1080:1920,setsar=1[t];[t][1:v]concat=n=2:v=1:a=0[v]" \
    -map "[v]" -map 1:a title_then_avatar.mp4
  ```
- Burn a lower-third:
  ```bash
  ffmpeg -i avatar.mp4 -vf "drawtext=text='Your Name':x=60:y=h-160:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=16" out.mp4
  ```

## 6. Deliver

Report: HeyGen `video_url`, chosen `avatar_id`, ElevenLabs `voice_id`, asset
ids, and (if titles) the HyperFrames project id / final file. For a batch, list
each item with its randomized avatar so the run is reproducible.

## Batch pattern

For N videos from N scripts: run Steps 2–4 per script, re-randomizing the avatar
each time (don't reuse `--seed` across items unless you want the same avatar).
Confirm the first take end-to-end before spending credits on the rest.
