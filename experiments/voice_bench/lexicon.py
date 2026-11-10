"""Find a spelling the voice says right for a name, test it on the voice bench, and keep it in voice/lexicon.toml.

Run with the pipeline's Python from the worktree (it reads the live folder for the voice environment, the models,
the reference voice and the model key):

    $env:PYTHONPATH = "<worktree>"
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/lexicon.py find "Huang"
        (real sentences with the name, from the bench cases and the live folder's scripts; no GPU)
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/lexicon.py candidates "Huang" [--llm]
        (the spellings that would be tried; no GPU)
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/lexicon.py search terms.json [--chunk 6] [--rounds 2]
        (terms.json: [{"name": "Huang", "sentences": ["...", "..."]}, ...]; sentences are found for a name given
         without any. Voices every candidate 5 times in a real sentence, keeps the best if 4 of 5 are right)
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/lexicon.py new 2026-11-09
        (the names in that day's script that the lexicon has not tested; writes a terms.json beside it; no GPU)

How a name is searched. The candidates are (1) the name as written (also tells the lexicon it needs no entry),
(2) the entry [voice.say] or the lexicon already has, (3) the name split into syllables with hyphens, (4) a
phonetic respelling made from how espeak-ng says it, (5) five respellings from the pipeline's language model (it is
shown the sentences). Each candidate is spoken 5 times, each time in one of the real sentences, by the bench's worker
(retakes off), heard by Whisper and judged by check.fault() against the sentence with the name as written (a clip
may also say the sentence as spoken). A take is right when the judge finds nothing wrong with the name, whatever
else the sentence has; `clean` counts takes with nothing wrong anywhere. The best candidate with at least 4 right
takes is kept (ties go to the plainest). If none reaches 4, the first round's heard words are given to the model for 5
new respellings (the second attempt); if that fails too the name is recorded as "no reliable spelling" with its best
score and listed for escalation: it is not tried a third time.
"""

import argparse
import json
import os
import re
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # the worktree
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))  # for bench.py

import bench  # noqa: E402
from steps.step10_voice import lexicon as pronunciation  # noqa: E402
from steps.step10_voice.check import fault, words  # noqa: E402
from steps.step10_voice.step import phrases, spoken  # noqa: E402

TAKES = 5
NEEDED = pronunciation.MINIMUM
SENTENCE_WORDS = (6, 30)  # a real sentence long enough to be natural, short enough not to fail on something else
IPA = [  # espeak-ng's IPA, longest first, to plain English letters
    ("tʃ", "ch"), ("dʒ", "j"), ("aɪə", "eye-uh"), ("aɪ", "eye"), ("aʊ", "ow"), ("eɪ", "ay"), ("oʊ", "oh"), ("əʊ", "oh"), ("ɔɪ", "oy"),
    ("ɑːɹ", "ar"), ("ɔːɹ", "or"), ("ɪɹ", "eer"), ("ɛɹ", "air"), ("ʊɹ", "oor"), ("ɚ", "er"), ("ɜː", "er"),
    ("ɑː", "ah"), ("ɔː", "aw"), ("uː", "oo"), ("iː", "ee"), ("æ", "a"), ("ɛ", "eh"), ("ɪ", "ih"), ("ʌ", "uh"), ("ə", "uh"),
    ("ʊ", "uu"), ("ɑ", "ah"), ("ɔ", "aw"), ("i", "ee"), ("u", "oo"), ("ᵻ", "ih"), ("ɐ", "uh"), ("o", "oh"),
    ("θ", "th"), ("ð", "dh"), ("ʃ", "sh"), ("ʒ", "zh"), ("ŋ", "ng"), ("ɹ", "r"), ("j", "y"), ("ɡ", "g"), ("x", "k"),
    ("ˈ", ""), ("ˌ", ""), ("ː", ""), ("ʔ", ""), ("ɾ", "t"),
]
LIVE = bench.DEFAULT_LIVE


# --- Real sentences ---------------------------------------------------------------------------------------------------

def sentences_with(name: str, live: Path = LIVE, limit: int = 4) -> list[str]:
    """Real sentences that contain the name: the bench cases first, then the live folder's scripts, shortest natural ones first."""
    pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
    found: dict[str, None] = {}
    for case in json.loads((HERE / "cases.json").read_text(encoding="utf-8")):
        for sentence in re.split(r"(?<=[.!?])\s+", case["text"]):
            found[sentence] = None
    for folder in sorted((live / "out").glob("*"), reverse=True)[:20]:
        for file in ("podcast-script.md", "script.md"):
            try:
                text = (folder / file).read_text(encoding="utf-8")
            except OSError:
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
                found[sentence.strip(" #*>-")] = None
    if len([s for s in found if pattern.search(s)]) < limit:  # too few: the older reports of the live folder too
        for file in sorted((live / "runs").glob("*/*/*.md"), reverse=True):
            try:
                text = file.read_text(encoding="utf-8")
            except OSError:
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
                if pattern.search(sentence):
                    found[sentence.strip(" #*>-|")] = None
    good = [s for s in found if pattern.search(s) and SENTENCE_WORDS[0] <= len(s.split()) <= SENTENCE_WORDS[1]
            and not re.search(r"https?:|\[|\]|\||\*\*|was heard|not heard|\":", s)]
    good = [s.strip('"') for s in good]
    good.sort(key=lambda s: (bool(re.search(r"\d", s)), len(s.split())))  # no figures first, then short
    return good[:limit]


# --- Candidates -------------------------------------------------------------------------------------------------------

def syllables(word: str) -> list[str]:
    """A rough split into syllables at vowel groups: Federighi -> Fe-de-ri-ghi."""
    parts = re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy]+(?![aeiouy]))?|[^aeiouy]+$", word, flags=re.I)
    return parts if parts and "".join(parts) == word else [word]


def hyphenated(name: str) -> str:
    return " ".join("-".join(syllables(word)) for word in name.split())


def from_espeak(name: str) -> str | None:
    """A spelling of how espeak-ng says the name, in plain letters: Huang -> hwahng."""
    from steps.step10_voice.check import _sound
    out = []
    for word in name.split():
        sound = _sound(word)
        if not sound:
            return None
        table = dict(IPA)
        letters = re.sub("|".join(re.escape(ipa) for ipa, _ in IPA), lambda m: table[m.group()], sound)
        out.append(re.sub(r"[^a-z-]", "", letters).capitalize())
    return " ".join(out)


def settings_of(live: Path = LIVE) -> dict:
    return tomllib.loads((ROOT / "settings.toml").read_text(encoding="utf-8"))


def from_model(name: str, sentences: list[str], tried: dict[str, list[str]] | None = None, count: int = 5) -> tuple[list[str], float]:
    """Respellings from the pipeline's language model. `tried` maps a spelling already voiced to what Whisper heard.
    Returns the spellings and what the request cost in dollars."""
    from dotenv import load_dotenv
    from common import model
    load_dotenv(LIVE / ".env")
    system = (
        "You help a text-to-speech model (Chatterbox Turbo, English, a human-sounding voice) say a name right. The model "
        "reads spellings, so a respelling is plain letters that make it say the name the way people say it in English. "
        "Rules: respell only the name, nothing else; write plain English letters, no IPA and no accents; never write a "
        "whole syllable in capital letters (it would be spelt out letter by letter); hyphens may join syllables; keep "
        "each word of a multi-word name; give spellings that differ from each other in how they sound, not only in style. "
        "Every spelling is tested by having the voice say it in a real sentence and having Whisper write it down.")
    lines = [f"Name: {name}", "", "Real sentences it appears in:", *[f"- {s}" for s in sentences], ""]
    if tried:
        lines += ["Already tried, with what Whisper wrote when the voice said it (the name's place in the sentence):"]
        lines += [f"- \"{spelling}\": " + " | ".join(f"\"{h}\"" for h in heard[:3]) for spelling, heard in tried.items()]
        lines += ["", "Give spellings that sound different from all of these."]
    lines.append(f"Give {count} respellings of the name.")
    schema = {"type": "object", "properties": {"spellings": {"type": "array", "items": {"type": "string"}}},
              "required": ["spellings"], "additionalProperties": False}
    reply = model.ask(settings_of()["model"], system, "\n".join(lines), schema)
    return [s.strip() for s in reply.data.get("spellings", []) if s.strip()][:count], reply.cost


def candidates(name: str, current: str | None, sentences: list[str], llm: bool = True, tried=None) -> tuple[dict[str, str], float]:
    """{spelling: strategy}, plainest first, and the model cost."""
    found: dict[str, str] = {name: "as written"}
    if current and current != name:
        found.setdefault(current, "existing entry")
    for spelling, how in ((hyphenated(name), "syllables"), (from_espeak(name), "espeak")):
        if spelling and spelling.lower() != name.lower():
            found.setdefault(spelling, how)
    cost = 0.0
    if llm:
        spellings, cost = from_model(name, sentences, tried)
        for spelling in spellings:
            found.setdefault(spelling, "model")
    return {k: v for k, v in found.items() if k.strip()}, cost


# --- Judging ----------------------------------------------------------------------------------------------------------

def about(problems: str | None, name: str, spelling: str) -> bool:
    """Whether what the judge found wrong concerns the name (its words, or the words of the spelling it was given)."""
    if not problems:
        return False
    tokens = {t for t in words(name) + words(spelling) if len(t) > 1} | {t for part in re.split(r"[\s-]+", spelling) for t in words(part) if len(t) > 1}
    return any(token in problems.lower() for token in tokens)


def is_name(name: str) -> bool:
    """A real name: Title-case words of four letters or more (Huang, Pierre Stock, Claude Code, Ollama)."""
    return bool(re.fullmatch(r"[A-Z][a-z]{3,}(?: [A-Z][a-z]+)*", name))


def test_spellings(batch: list[dict], live: Path, voice: dict, tested: dict) -> None:
    """Voice every candidate of every term 5 times. Adds "takes" to each candidate in place."""
    items, index = [], {}
    for term in batch:
        for spelling in term["candidates"]:
            say = {k: v for k, v in tested.items() if k != term["name"]}
            say = {**say, term["name"]: {"say": spelling, "passes": 5}}
            for take in range(TAKES):
                sentence = term["sentences"][take % len(term["sentences"])]
                heard_as = spoken(sentence, {}, say)
                number = len(items) + 1
                index[number] = (term, spelling, sentence, heard_as)
                items.append({"id": number, "position": number, "text": heard_as, "phrases": phrases(heard_as, 1000), "plain": sentence})
    folder = HERE / "clips-lexicon"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*"):
        if old.is_file():
            old.unlink()
    made = bench.speak(items, voice, live, folder)
    files = {}
    for number, clip in made.items():
        if "file" in clip:
            target = folder / f"{number}.wav"
            os.replace(clip["file"], target)
            files[number] = target
    listen = bench.run_listener(live, voice, folder)
    heard = listen([{"id": n, "file": str(p)} for n, p in files.items()])
    for number, (term, spelling, sentence, heard_as) in index.items():
        said = heard.get(number, {}).get("text")
        # A real name is judged against its own spelling only: a respelling that makes the voice say another name
        # ("Wong" for Huang) must not pass because Whisper wrote what was said. Abbreviations, codes and the like
        # (AWS, tpu, 404 Media, Ep) are meant to be said differently, so the spoken form counts for them.
        found = fault(sentence, said, None if is_name(term["name"]) else heard_as) if said is not None else "no clip or no transcript"
        take = {"sentence": sentence, "heard": said, "spoken": heard_as, "problem": found, "right": not about(found, term["name"], spelling), "clean": not found}
        term["candidates"][spelling]["takes"].append(take)
    for leftover in (folder / "job.json", folder / "result.json"):
        leftover.unlink(missing_ok=True)


def score(info: dict) -> tuple[int, int]:
    return sum(t["right"] for t in info["takes"]), sum(t["clean"] for t in info["takes"])


ORDER = {"as written": 0, "existing entry": 1, "syllables": 2, "espeak": 3, "model": 4}


def best_of(term: dict) -> tuple[str, dict]:
    return max(term["candidates"].items(), key=lambda kv: (*score(kv[1]), -ORDER[kv[1]["how"]]))


def search(terms: list[dict], live: Path, rounds: int, chunk: int, llm: bool, log: Path) -> dict:
    voice = tomllib.loads((ROOT / "settings.toml").read_text(encoding="utf-8"))["voice"]
    existing = pronunciation.load(ROOT)
    say = voice.get("say", {})
    spent, summary = 0.0, {}
    for start in range(0, len(terms), chunk):
        batch = terms[start:start + chunk]
        for term in batch:
            term["sentences"] = term.get("sentences") or sentences_with(term["name"], live)
            if not term["sentences"]:
                sys.exit(f"{term['name']}: no real sentence found; give some in terms.json")
            if len(term["sentences"]) < 2:
                print(f"{term['name']}: only one real sentence found; all 5 takes use it", flush=True)
            term["attempts"] = []
            term["candidates"] = {}
            current = (existing.get(term["name"]) or {}).get("say") or say.get(term["name"])
            made, cost = candidates(term["name"], current, term["sentences"], llm)
            spent += cost
            term["candidates"] = {s: {"how": how, "takes": []} for s, how in made.items()}
        todo = batch
        for attempt in range(1, rounds + 1):
            bench.guard(False)
            print(f"attempt {attempt}: {len(todo)} names, {sum(len(t['candidates']) for t in todo)} spellings, {datetime.now():%H:%M}", flush=True)
            fresh = [dict(t, candidates={s: i for s, i in t["candidates"].items() if not i["takes"]}) for t in todo]
            test_spellings(fresh, live, voice, {w: e for w, e in existing.items() if e.get("say")})
            for term, one in zip(todo, fresh):
                term["candidates"].update(one["candidates"])
                top, info = best_of(term)
                term["attempts"].append({"attempt": attempt, "best": top, "right": score(info)[0]})
            todo = [t for t in todo if score(best_of(t)[1])[0] < NEEDED]
            if attempt < rounds and todo and llm:
                for term in todo:  # the second attempt: new spellings from what Whisper heard for the first
                    tried = {s: [t["heard"] or "" for t in i["takes"] if not t["right"]] for s, i in term["candidates"].items()}
                    more, cost = from_model(term["name"], term["sentences"], tried)
                    spent += cost
                    for s in more:
                        term["candidates"].setdefault(s, {"how": "model", "takes": []})
            elif not todo:
                break
        for term in batch:
            top, info = best_of(term)
            right, clean = score(info)
            entry = {"passes": right, "of": TAKES, "clean": clean, "tested": date.today().isoformat(), "sentence": info["takes"][0]["sentence"]}
            if right >= NEEDED:
                entry = {"say": top, **entry}
            else:
                entry = {"status": "none", "best": top, **entry}
            written = term["candidates"].get(term["name"])
            if written:
                entry["as_written"] = score(written)[0]
            existing[term["name"]] = entry
            summary[term["name"]] = {"entry": entry, "attempts": term["attempts"],
                                     "tried": {s: {"how": i["how"], "right": score(i)[0], "clean": score(i)[1],
                                                   "heard": [t["heard"] for t in i["takes"] if not t["right"]][:2], "takes": i["takes"]}
                                               for s, i in term["candidates"].items()}}
        pronunciation.save(ROOT, existing)
        log.write_text(json.dumps({"model_cost_usd": round(spent, 4), "terms": summary}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"chunk done; lexicon saved; model cost so far ${spent:.4f}", flush=True)
    return {"cost": spent, "terms": summary}


def untested_names(day: str, live: Path) -> list[dict]:
    texts = []
    for file in ("script.md", "podcast-script.md"):
        try:
            texts += (live / "out" / day / file).read_text(encoding="utf-8").split("\n")
        except OSError:
            pass
    tested = pronunciation.load(ROOT)
    say = tomllib.loads((ROOT / "settings.toml").read_text(encoding="utf-8"))["voice"].get("say", {})
    return [{"name": n, "count": c} for n, c in pronunciation.untested(texts, tested, say, ROOT)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["find", "candidates", "search", "new"])
    ap.add_argument("arg")
    ap.add_argument("--live", default=str(LIVE))
    ap.add_argument("--chunk", type=int, default=6, help="names voiced in one GPU job")
    ap.add_argument("--rounds", type=int, default=2, help="attempts per name (the owner's rule: two, then escalate)")
    ap.add_argument("--llm", action="store_true", help="candidates: include the model's")
    ap.add_argument("--no-llm", action="store_true", help="search: leave the model out")
    ap.add_argument("--log", default=str(HERE / "results" / "lexicon-search.json"))
    args = ap.parse_args()
    live = Path(args.live)
    if args.command == "find":
        print("\n".join(sentences_with(args.arg, live)))
    elif args.command == "candidates":
        found, cost = candidates(args.arg, None, sentences_with(args.arg, live), args.llm)
        print(json.dumps(found, indent=1, ensure_ascii=False), f"\nmodel cost ${cost:.4f}")
    elif args.command == "new":
        names = untested_names(args.arg, live)
        out = HERE / "results" / f"lexicon-new-{args.arg}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps([{"name": n["name"]} for n in names], indent=1), encoding="utf-8")
        print(", ".join(f"{n['name']} ({n['count']})" for n in names) or "none", f"\nwrote {out}")
    else:
        terms = json.loads(Path(args.arg).read_text(encoding="utf-8"))
        Path(args.log).parent.mkdir(exist_ok=True)
        done = search(terms, live, args.rounds, args.chunk, not args.no_llm, Path(args.log))
        for name, info in done["terms"].items():
            e = info["entry"]
            print(f"{name}: {'-> ' + e['say'] if 'say' in e else 'NO RELIABLE SPELLING (best ' + e['best'] + ')'} {e['passes']}/{e['of']} (as written {e.get('as_written', '-')})")
        print(f"model cost ${done['cost']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
