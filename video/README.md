# Video (prototype)

Turns a day's `episode.mp3` into an edited 1080p video with motion graphics, pictures and a music bed. Every spoken sentence is its own shot, and each shot starts when its first word is heard: the word timings come from the audio itself, through the local Whisper model.

## Make one

```
.venv\Scripts\python.exe video\make_sfx.py                          # once: the sound kit for the cuts
.venv\Scripts\python.exe video\make_music.py                        # once: the music bed
.venv\Scripts\python.exe -m pip install --no-deps --only-binary=:all: --python-version 3.11 --target video\.image-deps "diffusers>=0.36"   # once

.venv-voice\Scripts\python.exe video\align.py 2026-10-16            # every word's time, from the audio (about 2 minutes)
.venv\Scripts\python.exe video\fetch_images.py 2026-10-16           # each story's lead image from its source pages
.venv\Scripts\python.exe video\image_prompts.py 2026-10-16          # two picture prompts per story (one model request, a few cents)
.venv-voice\Scripts\python.exe video\make_images.py 2026-10-16      # draw them with SDXL-Turbo (about 45 minutes for 46 on the laptop GPU)
.venv\Scripts\python.exe video\build_timeline.py 2026-10-16         # the shot list; add --images article, generated or none
cd video
npm install                                                          # once
npx remotion studio src/index.ts                                     # look through it in the browser
npx remotion render src/index.ts Episode ..\out\2026-10-16\episode-video.mp4 --concurrency=50%
```

The full render of a 22-minute episode takes about 30 minutes on this laptop. Rendering a range first is quicker: add `--frames=0-2699` for the first 90 seconds.

## Timing

`align.py` transcribes the episode with Whisper (`medium.en`) and `build_timeline.py` matches its words to the script's in order. About 9 in 10 words match; the others ("15 million dollars" for "$15M") get their time from the words on either side. Whisper starts a sentence early, over the pause before it, so each cut is moved to where the voice is actually heard.

The clip lengths that step 10 stores are not used for timing. On 2026-10-16 they added up to 2.96 seconds more than the joined episode, so a video timed from them fell further behind the voice with every story.

## Pictures

| Source | Made by | Shown as | Credit on screen |
| --- | --- | --- | --- |
| The story's own lead image (`og:image`) | `fetch_images.py` | behind the title card and the headline, and the first picture shot | `IMAGE · <source>` |
| Two scenes per story drawn locally by SDXL-Turbo | `image_prompts.py`, `make_images.py` | picture shots | `AI-GENERATED ILLUSTRATION` |

Every third plain sentence of a story becomes a picture shot: the picture full screen with the words on its dark side, or in a tilted frame beside them. Each picture moves slowly (Ken Burns).

The lead images belong to their publishers. They are fine for watching privately; before publishing, use `--images generated` or check the rights.

## How shots are chosen

`build_timeline.py` reads each sentence and picks a layout:

| Layout | When | What it shows |
| --- | --- | --- |
| `stat` | the sentence has a figure (money, %, ×, GB, billion) | the number counting up, with a gauge for percentages, bars for multipliers and cards for further figures |
| `names` | a list of three or more names | a grid of name cards popping in as each is said |
| `quote` | a source's view ("The Decoder says…") | the source's badge and the sentence lighting up word by word |
| `photo` | every third plain sentence of a story with pictures | a picture with the sentence lighting up beside it |
| `kinetic` | anything else | type that slams in word by word, a product name filling in, or a red marker sweeping over it |
| `cue`, `title` | the start of each story | a red "Next up" stinger, then a chapter card over the story's picture, with the segment, confirmed or reported, and sources |
| `intro`, `watch`, `opening`, `closing`, `credits` | their parts of the script | a stamp, a calendar tile, the logo open, the source roll and end card |

Around the shots: the heartbeat line from the logo runs along the bottom and beats harder when the voice is louder, a chapter bar shows the 23 stories, and captions run on the number and name shots.

## Sound

- **Voice:** `episode.mp3`, unchanged.
- **Music:** `make_music.py` synthesises a 77-second loop (A minor, 100 BPM: pad, sub bass, plucked arpeggio, soft kick and hats from bar 9). It plays about 20 dB under the voice, comes up on the "Next up" stingers, and rises over the end card before fading out.
- **Effects:** whooshes on cuts, a low hit on chapter cards and a tick on numbers, all from `make_sfx.py`.

Nothing needs a licence except the article lead images.

## Known limits

- The voice itself is quiet (about -27 dB RMS); the video does not raise it.
- SDXL-Turbo draws at 1024×576, so the pictures are a little soft at 1080p. The dark grading and slow movement hide most of it.
