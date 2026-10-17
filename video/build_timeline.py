"""Export one day's episode as a shot list for the video: every spoken sentence becomes one shot.

Timings come from the audio itself: align.py times every word with Whisper, and each shot starts when the
first word of its sentence is heard. (The clip lengths step 10 stores add up to a few seconds more than the
joined episode, so a timeline built from them drifts behind the voice.) The layout of each shot is chosen from
what the sentence says: a figure becomes a number callout, a list of names becomes a grid, a source's
view becomes a quote card, some plain sentences get a picture, and the rest becomes kinetic type.

    .venv\\Scripts\\python.exe video\\build_timeline.py 2026-10-16 [--images both|article|generated|none]
"""

import argparse
import difflib
import json
import re
import shutil
import sqlite3
from pathlib import Path

import numpy
import soundfile
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FPS = 30
TAIL = 4  # seconds the end card and the music stay after the last word

SEGMENT_NAMES = {"main": "Main story", "quick_hits": "Quick hit", "culture": "Lighter side", "watching": "Watching", "corrections": "Correction"}

# A figure worth showing big: money, percentages, multipliers, sizes, counts with a scale word.
FIGURE = re.compile(
    r"(?P<pre>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>%|x\b|×|GB\b|TB\b|B\b|M\b|K\b|-?billion|-?million|-?trillion|-?thousand|-?bit\b|\s?percent)?",
    re.IGNORECASE,
)
SCALE_WORDS = ("billion", "million", "trillion", "thousand", "percent", "%", "x", "×", "gb", "tb", "b", "m", "k", "bit")
SOURCE_VIEW = re.compile(
    r"^(?P<source>The [A-Z][\w']*(?: [A-Z][\w']*)?|[A-Z][\w]+(?: [A-Z][\w]+){0,2}) (?P<verb>says|reports|notes|writes|adds|argues|describes|calls|presents|focuses|cites|claims|warns|points out)\b"
)


def figures(text: str) -> list[dict]:
    """The figures in a sentence that are worth a callout, with the words around them as a label."""
    found = []
    for m in FIGURE.finditer(text):
        num, unit, pre = m.group("num"), (m.group("unit") or "").strip(), m.group("pre") or ""
        start = m.start()
        end = m.end("unit") if m.group("unit") else m.end("num")
        # Skip years, dates, version numbers and model names: "Nemotron 3.5", "RTX 4070", "74B-A9B", "1024 × 1024".
        before = text[max(0, start - 1) : start]
        if before and (before.isalpha() or before in ".-#"):
            continue
        previous_word = text[:start].split()[-1:] or [""]
        if previous_word[0].isupper() and len(previous_word[0]) > 1 and not pre:
            continue
        # "Flash 1017", "Omni 600M", "d1 3B": a number after a capitalised word inside the sentence, or after a word
        # with a digit in it, is part of a name, unless it is money, a share or a multiple.
        inside = text[:start].strip() != previous_word[0]
        if (previous_word[0][:1].isupper() and inside or re.search(r"\d", previous_word[0])) and not pre and unit.lower() not in ("%", "percent", "x"):
            continue
        # 10^26, firmware 13.60, port 8081: a power, a bare decimal and a four-figure code are not amounts.
        if not unit and not pre and (text[m.end("num") : m.end("num") + 1] == "^" or "." in num or re.fullmatch(r"\d{4}", num)):
            continue
        after = text[end : end + 2]
        spelled_scale = unit.lower().lstrip("-").startswith(("billion", "million", "trillion", "thousand", "bit"))
        next_word = text[end:].split()[:1] or [""]
        if not unit and not pre and next_word[0][:1].isupper():
            continue  # a name such as "404 Media"
        if unit == "×" or (after[:1] == "-" and after[1:2].isalpha() and not spelled_scale) or (after[:1].isalpha() and not unit):
            continue
        value = float(num.replace(",", ""))
        if not unit and not pre:
            if 1900 <= value <= 2100 or value < 2:
                continue
        if unit.lower().lstrip("-") not in SCALE_WORDS and not pre and value < 10:
            continue
        found.append({"prefix": pre, "value": value, "text": num, "unit": unit.lstrip("-"), "at": start})
    return found


def names(text: str) -> list[str]:
    """A list of three or more names: 'Atlassian, CrowdStrike, Perplexity and Salesforce'."""
    m = re.search(r"((?:[A-Z][\w.&'-]*(?: [A-Z][\w.&'-]*)*, ){2,}(?:[A-Z][\w.&'-]*(?: [A-Z][\w.&'-]*)*,? )?and (?:as )?[A-Z][\w.&'-]*(?: [A-Z][\w.&'-]*)*)", text)
    if not m:
        return []
    parts = re.split(r",\s*|\s+and\s+(?:as\s+)?", m.group(1))
    return [p.strip().rstrip(".") for p in parts if p.strip()]


COMMON_STARTS = {"The", "A", "An", "It", "Its", "This", "That", "With", "In", "On", "At", "For", "Two", "One", "Items", "Coverage"}


def key_phrase(text: str) -> str | None:
    """The product or company the sentence is about: the longest run of capitalised words."""
    best = None
    for m in re.finditer(r"(?:[A-Z][\w.'+/-]*|\d[\w.]*)(?: (?:[A-Z][\w.'+/-]*|\d[\w.]*))*", text):
        phrase = m.group(0).rstrip(".'").removesuffix("'s").removesuffix("’s")
        if m.start() == 0 and " " not in phrase and phrase[1:].islower():
            continue  # an ordinary word that starts the sentence: "Users", "Both"
        words = phrase.split()
        if words and words[0] in COMMON_STARTS:
            words = words[1:]
        phrase = " ".join(words)
        if not phrase or phrase.isdigit() or len(phrase) < 3:
            continue
        if best is None or len(phrase.split()) > len(best.split()) or (len(phrase.split()) == len(best.split()) and len(phrase) > len(best)):
            best = phrase
    return best


def layout_for(part: str, text: str, index_in_story: int, last_source: str | None) -> dict:
    if part == "how" or part == "what":
        view = SOURCE_VIEW.match(text)
        source = None
        if view:
            source = view.group("source") if view.group("source") not in ("It", "They", "He", "She") else last_source
        if source and part == "how":
            return {"kind": "quote", "source": source}
        found_names = names(text)
        if len(found_names) >= 3:
            return {"kind": "names", "names": found_names[:8]}
        found = figures(text)
        if found:
            return {"kind": "stat", "figures": found[:3]}
        if source:
            return {"kind": "quote", "source": source}
        return {"kind": "kinetic", "variant": index_in_story % 3, "key": key_phrase(text)}
    return {"kind": part}


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def speech_frames(mp3: Path) -> tuple[numpy.ndarray, float]:
    """Whether each 10 ms of the episode has voice in it, and the episode's length in seconds."""
    audio, rate = soundfile.read(mp3, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    hop = rate // 100
    n = len(audio) // hop
    peak = numpy.abs(audio[: n * hop]).reshape(n, hop).max(axis=1)
    return peak > 0.02, len(audio) / rate


def align(shots: list[dict], words: list[dict], loud: numpy.ndarray, duration: float) -> int:
    """Set each shot's start, end and word times from Whisper's words. Returns how many script words matched.

    The script's words and Whisper's are matched in order; a word Whisper heard differently ("15 million dollars"
    for "$15M") takes its time from the matched words around it. Whisper starts a sentence's first word early,
    stretched over the pause before it, so each start is moved on to where the voice is actually heard."""
    script = [w for s in shots for w in s["text"].split()]
    times: list[tuple[float, float] | None] = [None] * len(script)
    matcher = difflib.SequenceMatcher(None, [norm(w) for w in script], [norm(w["w"]) for w in words], autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            times[block.a + k] = (words[block.b + k]["start"], words[block.b + k]["end"])
    known = [t is not None for t in times]
    matched = sum(known)
    # Share out the time between the matched words on either side of a gap.
    k = 0
    while k < len(times):
        if times[k] is not None:
            k += 1
            continue
        j = k
        while j < len(times) and times[j] is None:
            j += 1
        left = times[k - 1][1] if k > 0 else 0.0
        right = times[j][0] if j < len(times) else duration
        step = (right - left) / (j - k + 1)
        for m in range(k, j):
            times[m] = (left + step * (m - k + 0.5), left + step * (m - k + 1))
        k = j

    def heard_from(t: float, until: float) -> float:
        frame, stop = int(t * 100), min(len(loud), int(until * 100) + 1)
        while frame < stop and not loud[frame]:
            frame += 1
        return frame / 100 if frame < stop else t

    def heard_until(t: float, since: float) -> float:
        frame, stop = min(len(loud) - 1, int(t * 100)), int(since * 100)
        while frame > stop and not loud[frame]:
            frame -= 1
        return (frame + 1) / 100

    at = 0
    for i, shot in enumerate(shots):
        mine = times[at : at + len(shot["text"].split())]
        # A first word Whisper heard differently ("Cloud" for "Claude") has a guessed time in the pause before the
        # sentence, so the voice is looked for up to the end of the shot's first word Whisper did hear.
        first = next((k for k in range(len(mine)) if known[at + k]), 0)
        at += len(mine)
        start = 0.0 if i == 0 else heard_from(mine[0][0], mine[first][1])
        shot["start"] = round(start, 3)
        shot["end"] = round(max(start + 0.3, heard_until(mine[-1][1], mine[-1][0])), 3)
        shot["words"] = [0.0] + [round(max(0.0, w[0] - start), 3) for w in mine[1:]]  # when each word is said
    for i, shot in enumerate(shots):
        shot["next"] = shots[i + 1]["start"] if i + 1 < len(shots) else round(duration, 3)
        shot["end"] = min(shot["end"], shot["next"])
    return matched


def pictures(day: str, story_ids: list[int], which: str, public: Path) -> dict[int, list[dict]]:
    """The pictures for each story, the article's own first, copied into public/images for the video."""
    cache = Path(__file__).parent / "cache" / day
    lists = {"article": cache / "article-images.json", "generated": cache / "generated-images.json"}
    article = json.loads(lists["article"].read_text()) if which in ("both", "article") and lists["article"].exists() else {}
    generated = json.loads(lists["generated"].read_text()) if which in ("both", "generated") and lists["generated"].exists() else {}
    folder = public / "images"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    out = {}
    for story_id in story_ids:
        chosen = [{"file": article[str(story_id)]["file"], "credit": article[str(story_id)]["credit"]}] if str(story_id) in article else []
        chosen += [{"file": name, "credit": "AI-generated"} for name in generated.get(str(story_id), [])]
        for picture in chosen:
            shutil.copyfile(cache / "images" / picture["file"], folder / picture["file"])
            picture["file"] = f"images/{picture['file']}"
        if chosen:
            out[story_id] = chosen
    return out


def transparent(source: Path, target: Path) -> None:
    """The logos are drawn on near-black; make that black see-through so they sit on any background."""
    rgb = numpy.asarray(Image.open(source).convert("RGB"), dtype="float32")
    background = rgb[5, 5]
    distance = numpy.abs(rgb - background).max(axis=2)
    alpha = numpy.clip(distance / 90, 0, 1)
    out = numpy.dstack([rgb, alpha * 255]).astype("uint8")
    Image.fromarray(out, "RGBA").resize((1500, 1500), Image.LANCZOS).save(target)


def envelope(mp3: Path, frames: int) -> list[float]:
    """Loudness of the voice for each video frame, 0 to 1, for the graphics that move with the voice."""
    audio, rate = soundfile.read(mp3, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    per = rate / FPS
    out = []
    for f in range(frames):
        chunk = audio[int(f * per) : int((f + 1) * per)]
        out.append(float(numpy.sqrt(numpy.mean(chunk**2))) if len(chunk) else 0.0)
    top = numpy.percentile(out, 98) or 1.0
    return [round(min(1.0, v / top), 3) for v in out]


def main(day: str, which: str) -> None:
    conn = sqlite3.connect(ROOT / "data" / "local.db")
    run_id = conn.execute("select id from runs where run_date=? order by id desc limit 1", (day,)).fetchone()[0]

    stories = {}
    rows = conn.execute(
        """select es.story_id, es.position, es.segment, s.label, s.item_ids
           from episode_stories es join episodes e on e.id = es.episode_id
           join selections s on s.story_id = es.story_id and s.run_id = e.run_id
           where e.run_id = ? and es.form != 'dropped' order by es.position""",
        (run_id,),
    ).fetchall()
    for story_id, position, segment, label, item_ids in rows:
        sources = []
        for item_id in json.loads(item_ids):
            row = conn.execute("select source from items where id=?", (item_id,)).fetchone()
            if row and row[0] not in sources:
                sources.append(row[0])
        stories[story_id] = {"segment": SEGMENT_NAMES.get(segment, segment), "label": label, "sources": sources[:4]}

    clips = conn.execute(
        """select l.part, l.story_id, l.text, k.seconds, k.pause_after
           from clips k join script_lines l on l.id = k.line_id where k.run_id = ? order by k.position""",
        (run_id,),
    ).fetchall()

    shots, at, order, index_in_story, current, last_source = [], 0.0, [], 0, None, None
    for part, story_id, text, seconds, pause in clips:
        # The sentence splitter breaks "Oct. 23." in two; show such a stub as part of the shot before it.
        if shots and len(text) < 6 and part in ("what", "how"):
            shots[-1]["text"] += " " + text
            shots[-1]["end"] = round(at + seconds, 3)
            shots[-1]["next"] = round(at + seconds + pause, 3)
            at += seconds + pause
            continue
        if story_id and story_id != current and part in ("cue", "title"):
            current, index_in_story, last_source = story_id, 0, None
            order.append(story_id)
        layout = layout_for(part, text, index_in_story, last_source)
        last_source = layout.get("source", last_source)
        shot = {
            "part": part,
            "story": story_id,
            "text": text,
            "start": round(at, 3),
            "end": round(at + seconds, 3),  # the voice stops here
            "next": round(at + seconds + pause, 3),  # the next shot starts here
            "layout": layout,
            "index": index_in_story,
        }
        if part in ("what", "how", "brief"):
            index_in_story += 1
        shots.append(shot)
        at += seconds + pause

    mp3 = ROOT / "out" / day / "episode.mp3"
    words_file = Path(__file__).parent / "cache" / day / "words.json"
    if not words_file.exists():
        raise SystemExit(f"No word timings for {day}. Run first: .venv-voice\\Scripts\\python.exe video\\align.py {day}")
    loud, total = speech_frames(mp3)
    matched = align(shots, json.loads(words_file.read_text(encoding="utf-8"))["words"], loud, total)
    shots[-1]["next"] = round(total + TAIL, 3)  # the end card holds while the music fades

    public = Path(__file__).parent / "public"
    public.mkdir(exist_ok=True)
    story_pictures = pictures(day, order, which, public) if which != "none" else {}
    # A story's lead picture sits behind its title and its headline; every third plain sentence gets one of the rest.
    used: dict[int, int] = {}
    for shot in shots:
        mine = story_pictures.get(shot["story"])
        index = shot.pop("index")
        if not mine:
            continue
        kind = shot["layout"]["kind"]
        if kind in ("title", "headline"):
            shot["layout"]["image"] = mine[0]
        elif kind in ("kinetic", "brief") and index % 3 == 1:
            n = used.get(shot["story"], 0)
            shot["layout"] = {"kind": "photo", "image": mine[(1 + n) % len(mine)], "key": shot["layout"].get("key")}
            used[shot["story"]] = n + 1

    titles = {s["story"]: s["text"] for s in shots if s["part"] == "title"}
    chapters = []
    for n, story_id in enumerate(order, 1):
        first = next(s for s in shots if s["story"] == story_id and s["part"] in ("cue", "title"))
        chapters.append({"story": story_id, "number": n, "title": titles.get(story_id, ""), "start": first["start"], **stories.get(story_id, {})})

    shutil.copyfile(mp3, public / "episode.mp3")
    for logo in ("aidea-logo-3000.png", "aidea-daily-logo-3000.png"):
        transparent(ROOT / "branding" / logo, public / logo)

    frames = int(round(total * FPS)) + FPS
    timeline = {
        "date": day,
        "fps": FPS,
        "duration": round(total + TAIL, 3),
        "shots": shots,
        "chapters": chapters,
        "level": envelope(mp3, frames),
    }
    (Path(__file__).parent / "src" / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")

    kinds = {}
    for s in shots:
        kinds[s["layout"]["kind"]] = kinds.get(s["layout"]["kind"], 0) + 1
    words = sum(len(s["text"].split()) for s in shots)
    print(f"{len(shots)} shots, {len(chapters)} stories, {total / 60:.2f} minutes; {matched} of {words} words matched to the audio; "
          f"pictures for {len(story_pictures)} stories. Layouts: {kinds}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("day", nargs="?", default="2026-10-16")
    parser.add_argument("--images", choices=("both", "article", "generated", "none"), default="both",
                        help="article: each story's own lead image (the publishers' rights); generated: make_images.py's pictures")
    args = parser.parse_args()
    main(args.day, args.images)
