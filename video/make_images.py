"""Draw the b-roll pictures from image_prompts.py's prompts with SDXL-Turbo, on the laptop's GPU.

The pictures are made here, so they are free to publish. Run it with the voice environment, which has torch for
the GPU. Its own diffusers is too old for its transformers, and the voice step needs both left as they are, so a
newer diffusers sits in video\\.image-deps and is loaded first. Install it once:

    .venv\\Scripts\\python.exe -m pip install --no-deps --only-binary=:all: --python-version 3.11 --target video\\.image-deps "diffusers>=0.36"
    .venv-voice\\Scripts\\python.exe video\\make_images.py 2026-10-16
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".image-deps"))

import torch  # noqa: E402
from diffusers import AutoPipelineForText2Image  # noqa: E402

WIDTH, HEIGHT = 1024, 576  # 16:9; the video scales them up under a slow push-in
NEGATIVE = "text, letters, words, watermark, logo, signature, caption, blurry, deformed hands, low quality"


def main(day: str) -> None:
    cache = Path(__file__).parent / "cache" / day
    prompts = json.loads((cache / "image-prompts.json").read_text(encoding="utf-8"))
    folder = cache / "images"
    folder.mkdir(parents=True, exist_ok=True)
    pipe = AutoPipelineForText2Image.from_pretrained("stabilityai/sdxl-turbo", torch_dtype=torch.float16, variant="fp16").to("cuda")
    pipe.set_progress_bar_config(disable=True)
    made = {}
    for story, story_prompts in prompts.items():
        for n, prompt in enumerate(story_prompts):
            file = folder / f"generated-{story}-{n}.jpg"
            if not file.exists():  # a picture already drawn is kept, so a second run only fills gaps
                generator = torch.Generator("cuda").manual_seed(int(story) * 10 + n)
                image = pipe(prompt=prompt, negative_prompt=NEGATIVE, num_inference_steps=2, guidance_scale=0.0, width=WIDTH, height=HEIGHT, generator=generator).images[0]
                image.save(file, quality=92)
            made.setdefault(story, []).append(file.name)
    (cache / "generated-images.json").write_text(json.dumps(made, indent=1), encoding="utf-8")
    print(f"{sum(len(v) for v in made.values())} pictures -> {folder}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-16")
