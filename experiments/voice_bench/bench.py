"""Voice test bench: speak each case several times, hear every take with Whisper, and count the clean ones.

Run with the pipeline's Python from the project folder (the worktree), pointing at the live folder for the
environments, the models and the reference voice:

    $env:PYTHONPATH = "<worktree>"
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/bench.py experiments/voice_bench/cases.json [--n 5]
        [--text-only] [--group A,B] [--ids A01,C03] [--live "<live folder>"] [--force]
    "<live>\\.venv\\Scripts\\python.exe" experiments/voice_bench/bench.py --rejudge experiments/voice_bench/results/<run>.json
        (judges the stored Whisper text of an earlier run again with the current check.py: no voice, no GPU)

It does what step 10 does, with the real code: `step10_voice.step.spoken` (with `[voice.say]` from settings.toml),
`phrases`, the real worker (one job for every case x take, so the model loads once; its own retakes are switched off
with retakes = 0, so every take is an independent raw take), the real listener, and `check.fault` against the
sentence as written and as spoken (a take is fine if it says either). A case may also have "expect" (words that must be heard), "forbid" (words that must not be
heard) and "forbid_raw" (regular expressions that must not match what Whisper wrote, punctuation included).
A take passes when fault() finds nothing and every expect/forbid holds. A case passes with 4 of 5 takes.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # the worktree
sys.path.insert(0, str(ROOT))

from steps.step10_voice.check import fault, run_listener, words  # noqa: E402
from steps.step10_voice.step import phrases, spoken  # noqa: E402

DEFAULT_LIVE = Path(r"C:\Users\hanee\Downloads\AI news podcast")
PASS_RATIO = 0.8  # 4 of 5
NO_GPU_FROM, NO_GPU_UNTIL = (3, 30), (5, 30)  # local time: the scheduled run starts at 04:00


def guard(force: bool) -> None:
    """Refuse to start a GPU job while the daily run may be using the card."""
    now = datetime.now()
    if not force and NO_GPU_FROM <= (now.hour, now.minute) < NO_GPU_UNTIL:
        sys.exit(f"It is {now:%H:%M}: no GPU job between 03:30 and 05:30, the scheduled run needs the card.")
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match ' -m steps' } | "
         "Select-Object -ExpandProperty CommandLine"],
        capture_output=True, text=True).stdout.strip()
    if out and not force:
        sys.exit(f"A pipeline run is going (python -m steps); not starting a GPU job:\n{out}")


def mentions(heard: list[str], wanted: list[str]) -> list[bool]:
    """For each wanted string, whether it is in what was heard (same normalisation as check.py)."""
    spaced, joined = " " + " ".join(heard) + " ", "".join(heard)
    result = []
    for text in wanted:
        parts = words(text)
        result.append(bool(parts) and (f" {' '.join(parts)} " in spaced or "".join(parts) in joined))
    return result


def forbidden(heard: list[str], banned: list[str]) -> list[bool]:
    spaced = " " + " ".join(heard) + " "
    return [bool(words(text)) and f" {' '.join(words(text))} " in spaced for text in banned]


def judge(case: dict, heard_text: str) -> dict:
    heard = words(heard_text)
    problems = []
    found = fault(case["text"], heard_text, case.get("spoken"))
    if found:
        problems.append(found)
    for text, ok in zip(case.get("expect", []), mentions(heard, case.get("expect", []))):
        if not ok:
            problems.append(f"expected \"{text}\" not heard")
    for text, bad in zip(case.get("forbid", []), forbidden(heard, case.get("forbid", []))):
        if bad:
            problems.append(f"forbidden \"{text}\" heard")
    for pattern in case.get("forbid_raw", []):
        if re.search(pattern, heard_text, re.I):
            problems.append(f"forbidden pattern /{pattern}/ matched")
    return {"pass": not problems, "problems": problems, "fault": found}


def speak(items: list[dict], voice: dict, live: Path, folder: Path) -> dict:
    """One worker job for every take. Retakes are off. Returns {item id: clip}."""
    python, reference = live / voice["python"], live / voice["reference"]
    folder.mkdir(parents=True, exist_ok=True)
    job = folder / "job.json"
    job.write_text(json.dumps({
        "sentences": items, "reference": str(reference), "folder": str(folder), "phrase_pause": voice["pauses"]["phrase"],
        **{key: voice[key] for key in ("engine", "temperature", "exaggeration", "cfg_weight", "speed")},
        "clean": voice.get("clean", False), "retakes": 0, "longest_pause": voice.get("longest_pause", 2.0),
    }), encoding="utf-8")
    result = job.with_name("result.json")
    result.unlink(missing_ok=True)
    env = dict(os.environ, HF_HOME=str(live / "data" / "models" / "huggingface"))
    worker = ROOT / "steps" / "step10_voice" / "worker.py"
    done = subprocess.run([str(python), str(worker), str(job)], env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=4 * 3600)
    if not result.exists():
        sys.exit(f"The voice model made nothing: {(done.stderr or done.stdout)[-800:]}")
    if done.returncode != 0:
        print(f"worker stopped early ({done.returncode}); using what it made", file=sys.stderr)
    answer = json.loads(result.read_text(encoding="utf-8"))["clips"]
    return {int(key): clip for key, clip in answer.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cases", nargs="?")
    ap.add_argument("--rejudge", metavar="RESULTS", help="judge the stored takes of this results .json again; no voice, no GPU")
    ap.add_argument("--n", type=int, default=5, help="takes per case")
    ap.add_argument("--text-only", action="store_true", help="only print text -> spoken form; no voice, no GPU")
    ap.add_argument("--group", help="only these groups, e.g. A,B")
    ap.add_argument("--ids", help="only these case ids, e.g. A01,C03")
    ap.add_argument("--live", default=str(DEFAULT_LIVE), help="the live folder: environments, models, reference voice")
    ap.add_argument("--force", action="store_true", help="skip the GPU guard")
    args = ap.parse_args()
    if args.rejudge:
        return rejudge(Path(args.rejudge))
    if not args.cases:
        ap.error("cases file needed unless --rejudge is given")

    live = Path(args.live)
    settings = tomllib.loads((ROOT / "settings.toml").read_text(encoding="utf-8"))["voice"]
    say, longest = settings.get("say", {}), settings["pauses"]["longest_phrase"]
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.group:
        cases = [c for c in cases if c["group"] in args.group.split(",")]
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids.split(",")]
    for case in cases:
        case["spoken"] = spoken(case["text"], say)

    if args.text_only:
        for case in cases:
            print(f"[{case['id']}] {case['text']}\n     -> {case['spoken']}")
        return 0

    guard(args.force)
    name, stamp = Path(args.cases).stem, datetime.now().strftime("%Y%m%d-%H%M%S")
    clips = HERE / "clips"
    clips.mkdir(exist_ok=True)
    for old in clips.glob("*"):
        if old.is_file():
            old.unlink()

    items, index = [], {}
    for case in cases:
        for take in range(args.n):
            number = len(items) + 1
            index[number] = (case, take)
            items.append({"id": number, "position": number, "text": case["spoken"],
                          "phrases": phrases(case["spoken"], longest), "plain": case["text"]})
    began = time.monotonic()
    print(f"{len(cases)} cases x {args.n} takes = {len(items)} takes, started {datetime.now():%H:%M}", flush=True)
    made = speak(items, settings, live, clips)
    voiced = time.monotonic() - began

    files = {}
    for number, clip in made.items():
        if "file" in clip:
            case, take = index[number]
            target = clips / f"{case['id']}-t{take + 1}.wav"
            os.replace(clip["file"], target)
            files[number] = target
    listen = run_listener(live, settings, clips)
    heard = listen([{"id": number, "file": str(path)} for number, path in files.items()])
    took = time.monotonic() - began
    for leftover in (clips / "job.json", clips / "result.json"):
        leftover.unlink(missing_ok=True)

    results = []
    for case in cases:
        takes = []
        for take in range(args.n):
            number = next(n for n, (c, t) in index.items() if c is case and t == take)
            clip, said = made.get(number, {}), heard.get(number, {})
            if "text" in said:
                verdict = judge(case, said["text"])
            else:
                verdict = {"pass": False, "problems": [clip.get("error") or said.get("error") or "no clip or no transcript"], "fault": None}
            takes.append({"take": take + 1, "heard": said.get("text"), "seconds": clip.get("seconds"),
                          "file": str(files[number].relative_to(ROOT)) if number in files else None, **verdict})
        passes = sum(t["pass"] for t in takes)
        results.append({**{k: v for k, v in case.items()}, "passes": passes, "n": args.n,
                        "result": "PASS" if passes >= PASS_RATIO * args.n - 1e-9 else "FAIL", "takes": takes})

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    summary = {"cases_file": args.cases, "n": args.n, "started": stamp, "voice_seconds": round(voiced), "total_seconds": round(took),
               "settings": {k: settings[k] for k in ("engine", "temperature", "clean", "speed")}, "retakes": 0, "results": results}
    (out / f"{name}-{stamp}.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / f"{name}-{stamp}.md").write_text(markdown(summary), encoding="utf-8")
    print(markdown(summary, brief=True))
    print(f"wrote {out / f'{name}-{stamp}.md'}")
    return 0


def rejudge(path: Path) -> int:
    """Judge the stored Whisper text of an earlier run again with the current judge. Writes <run>-rejudged.json/.md and
    prints each case's old and new passes."""
    summary = json.loads(path.read_text(encoding="utf-8"))
    n = summary["n"]
    lines = ["| Case | Group | Old | New | Result |", "| --- | --- | --- | --- | --- |"]
    for case in summary["results"]:
        old = case["passes"]
        for take in case["takes"]:
            if take.get("heard") is not None:
                take.update(judge(case, take["heard"]))
        case["passes"] = sum(t["pass"] for t in case["takes"])
        case["result"] = "PASS" if case["passes"] >= PASS_RATIO * n - 1e-9 else "FAIL"
        lines.append(f"| {case['id']} | {case['group']} | {old}/{n} | {case['passes']}/{n} | {case['result']} |")
    out = path.with_name(path.stem + "-rejudged")
    out.with_suffix(".json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(summary), encoding="utf-8")
    print(markdown(summary, brief=True))
    print("\n".join(lines))
    print(f"wrote {out.with_suffix('.md')}")
    return 0


def markdown(summary: dict, brief: bool = False) -> str:
    results, n = summary["results"], summary["n"]
    lines = [f"# Voice bench: {Path(summary['cases_file']).stem}, {summary['started']}", "",
             f"{len(results)} cases x {n} takes, worker retakes off, voice {summary['voice_seconds'] / 60:.1f} min, "
             f"with Whisper {summary['total_seconds'] / 60:.1f} min. A case passes with at least {-(-PASS_RATIO * n // 1):.0f} of {n}.", "",
             "| Group | Cases passing | Takes passing |", "| --- | --- | --- |"]
    for group in sorted({r["group"] for r in results}):
        rows = [r for r in results if r["group"] == group]
        lines.append(f"| {group} | {sum(r['result'] == 'PASS' for r in rows)} / {len(rows)} | {sum(r['passes'] for r in rows)} / {len(rows) * n} |")
    lines += ["", "| Case | Kind | Passes | Result |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['id']} | {r['kind']} | {r['passes']}/{n} | {r['result']} |" for r in results]
    if not brief:
        lines += ["", "## Failing takes", ""]
        for r in results:
            bad = [t for t in r["takes"] if not t["pass"]]
            if not bad:
                continue
            lines += [f"### {r['id']} ({r['group']}, {r['kind']}): {r['passes']}/{n} {r['result']}", "", f"Text: {r['text']}", f"Spoken: {r['spoken']}", ""]
            lines += [f"- take {t['take']}: heard \"{t['heard']}\" -- {'; '.join(t['problems'])}" for t in bad]
            lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
