"""Check the three cases from user testing, end to end with the live models: the Medicare letter
in Russian, a watch advert pasted three times, and the English Medicare letter.

    python backtest/lang_check.py
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
import core  # noqa: E402

CASES = [("Russian Medicare letter", HERE / "lang" / "cms_nomnc_ru.txt"),
         ("Watch advert x3", HERE / "lang" / "watch_ad_x3.txt"),
         ("English Medicare letter", HERE.parent / "letters" / "cms_nomnc.md")]


def show(name, path):
    text = path.read_text(encoding="utf-8")
    t0 = time.time()
    fact = core.extract_facts(text)
    res = core.run_test_job(core.Job("test"), text, fact)
    located = res.get("located") or {}
    print(f"\n=== {name}  ({round(time.time() - t0)}s)")
    print(f"  language {fact['language']} · kind {fact['kind']} · need to act {fact['action_required']} · box heading “{fact['box_heading']}”")
    print(f"  summary: {fact['summary'][:120]}")
    for s, v in fact["facts"].items():
        print(f"  key {s:11}: {v[:110]}")
    print(f"  testable {res['testable']} · busy {res['overall']['busy']:.0f} · full {res['overall']['careful']:.0f}")
    print(f"  highlights found: {sum(bool(v) for v in located.values())} of 4  {[k for k, v in located.items() if v]}")
    for c in res["cards"]:
        print(f"  WRONG [{c['slot']}/{c['view']} {c['count']}/{c['of']}] said: {c['said'][:90]}")
        tip = c.get("coach") or {}
        print(f"      why: {tip.get('why', '-')[:140]}\n      fix: {tip.get('fix', '-')[:140]}")
        if tip.get("why_en"):
            print(f"      (en) {tip['why_en'][:120]} | {tip.get('fix_en', '')[:120]}")
    for i in res["checklist"]:
        print(f"  {'✓' if i['ok'] else '!'} {i['title']}")
    return fact, res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = {}
    for name, path in CASES:
        fact, res = show(name, path)
        out[name] = {"fact": fact, "test": {k: res[k] for k in ("cards", "checklist", "testable", "overall", "located", "language")}}
    (HERE / "lang" / "results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
