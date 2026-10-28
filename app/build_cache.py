#!/usr/bin/env python3
"""Turn results you already ran into saved results the web app opens instantly.

  python app/build_cache.py

Test results come from the newest results/<run>/calls.jsonl that covers each
letter; fix results from the newest results/fix-*/<letter>/ folder. No API calls.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import core  # noqa: E402
import fixer  # noqa: E402
import run_test as rt  # noqa: E402

RESULTS = rt.ROOT / "results"


def run_time(name):
    """'20261018-001747' or 'fix-20261018-003806' -> '2026-10-18T00:17:47'."""
    m = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", name)
    return f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}" if m else None


def newest_test_rows():
    """For each letter, the readings from the newest real test run that includes it."""
    rows = {}
    for run in sorted(RESULTS.iterdir(), reverse=True):
        log = run / "calls.jsonl"
        if run.name.startswith("fix-") or run.name.endswith(("-mock", "-dry")) or not log.exists():
            continue
        by_doc = {}
        for line in log.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "doc" in r:
                by_doc.setdefault(r["doc"], []).append(r)
        for doc, rs in by_doc.items():
            rows.setdefault(doc, (run.name, rs))
    return rows


def newest_fix_dirs():
    found = {}
    for run in sorted(RESULTS.glob("fix-*"), reverse=True):
        if run.name.endswith("-mock"):
            continue
        for d in run.iterdir():
            if (d / "candidates.json").exists() and (d / "fixed_letter.md").exists():
                found.setdefault(d.name, d)
    return found


def main():
    ids = core.sample_ids()
    fixes = newest_fix_dirs()
    for doc, d in fixes.items():
        if doc not in ids:
            continue
        c = json.loads((d / "candidates.json").read_text(encoding="utf-8"))
        pick = next(x for x in c["candidates"] if x["desc"] == c["pick"])
        pick["text"] = (d / "fixed_letter.md").read_text(encoding="utf-8")
        letter = (d / "original_reflowed.md").read_text(encoding="utf-8")
        r = {"letter": letter, "located": c["located"], "base": c["original"], "ranked": c["candidates"],
             "pick": pick, "refs": fixer.relative_refs(pick, c["located"])}
        fix = core.summarize_fix(r)
        fix["ran_at"], fix["live"] = run_time(d.parent.name), False
        core.save_cache(doc, "fix", fix)
        print(f"fix   {doc:16s} from {d.parent.name}: {r['base']['score']:.0f} → {pick['confirm']['score']:.0f}")
    for doc, (run, rs) in newest_test_rows().items():
        if doc not in ids:
            continue
        s = core.load_sample(doc)
        located =core.load_cache(doc, "fix")["located"] if (core.CACHE / f"{doc}.fix.json").exists() else None
        test = core.summarize_test(s["text"], s["fact"], rs, located)
        old = core.load_cache(doc, "test")
        if not located and old and old.get("located"):
            test["located"] = old["located"]  # keep highlights found earlier
        test["ran_at"], test["live"] = run_time(run), False
        core.save_cache(doc, "test", test)
        print(f"test  {doc:16s} from {run}: busy {test['overall']['busy']:.0f}, careful {test['overall']['careful']:.0f}"
              f"{'' if located else '  (no highlights yet)'}")


if __name__ == "__main__":
    main()
