# Step 10, Voice

Turns the final script into speech, one clip per sentence. It runs on this PC and costs nothing.

## What it does

1. Takes the sentences of the final script from step 9, in speaking order.
2. Writes figures and symbols the way they are said: "$300 million" becomes "300 million dollars", "82%" becomes "82 percent", "501B" becomes "501 billion".
3. Speaks each sentence with Chatterbox Turbo, in the voice of the reference recording.
4. Checks each clip and speaks a bad one once more.
5. Records each clip's length and the pause that follows it.
6. Writes a report to `runs/<date>/10_voice/report.md`, listing every sentence it prepared for speaking.

Step 11 then joins the clips into `out/<date>/episode.mp3`.

## Rules

- **One consistent voice:** the recording named under `[voice]` in `settings.toml`, by default `voice/reference.wav`.
- **Use only a voice you have the right to use.** The model copies whatever recording it is given.
- **Nothing is sent to a paid voice service.** The model runs on this PC's graphics card.
- **Preparation changes how text is spoken, never what it says.** The script is not altered.
- **Names the voice gets wrong are said from a list you add to:** `[voice.say]` in `settings.toml`.
- **A failed clip is tried once more.** If it fails again the run stops, so a broken episode is never produced. The good clips are kept, and a rerun speaks only what is missing.
- **A clip of an unbelievable length for its words counts as failed.**
- **A held episode is not voiced** until you have looked at it.
- **Pauses are set by what comes next:** between sentences, between parts of a story, between headlines, and before a new story. The lengths are under `[voice.pauses]`.

## It never

- Changes the words of the script.
- Skips a sentence silently.
- Adds music, effects or a second voice.

## Run it

`.\.venv\Scripts\python.exe -m steps 10`

To voice a script that is already written, without fetching, rating or writing again: `.\.venv\Scripts\python.exe -m steps --again 10`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step10_voice` (they use a stand-in voice)

## How it is set up

- **A separate Python.** The voice model needs Python 3.11 and its own libraries, so it lives in `.venv-voice`, apart from the pipeline's `.venv`. Step 10 starts `worker.py` there and reads back what it made.
- **Installed once.** `chatterbox-tts` version 0.1.7, with PyTorch for an NVIDIA graphics card. The model's files (3.8 GB) are in `data/models/huggingface`. Nothing is downloaded again.
- **To install on another PC:** see `voice/README.md`.

## What it stores

- Table `clips`: for each spoken sentence, its file, its length in seconds and the pause after it.
- The clip files themselves, in `out/<date>/clips/`, until step 11 has joined them.

## Good to know

- **Measured on 7 October 2026:** 125 sentences, 16.1 minutes of audio, made in 11.8 minutes on an RTX 4060 laptop card.
- **The voice speaks a little slower than the cap assumes.** A 2,213-word script came to 16.1 minutes, about 137 words a minute with pauses, against the 150 used to set the cap. Since then `words_per_minute` under `[episode]` has been set to 130, the voice's measured pace.
- **Every file carries an inaudible watermark** marking it as AI-generated. The model adds it and offers no way to turn it off.
- **The model has no dial for tone, pitch or pace.** It takes its delivery from the reference recording, so a livelier recording gives a livelier read.
- **Takes vary.** It does not say a sentence the same way twice, and nobody has listened to a clip before it is joined.
