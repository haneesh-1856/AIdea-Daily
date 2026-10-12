# The show's voice

- `reference.wav`: the recording the voice model copies. It is 20 seconds of the owner's own voice (seconds 39 to 59 of the recording "my voice 2", made on 7 October 2026). To change the show's voice, replace this file with 15 to 20 seconds of clean speech from someone who has agreed to it.
- The other `reference-*.wav` files are earlier candidates and can be deleted.

## Installing the voice model on another PC

It needs an NVIDIA graphics card. From the project folder:

```
.\.venv\Scripts\python.exe -m pip install uv
.\.venv\Scripts\python.exe -m uv venv .venv-voice --python 3.11
.\.venv\Scripts\python.exe -m uv pip install --python .venv-voice\Scripts\python.exe -r voice\requirements.txt --torch-backend=cu124
```

The model's files download once, on first use, into `data/models/huggingface`.
