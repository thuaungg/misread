"""Backtest: put every letter in backtest/text through the same steps the web app runs.

    python backtest/run.py test     # word-limit check → answer key (Ultra) → 12 readings
    python backtest/run.py audit    # a second, careful check of every "wrong answer" card
    python backtest/run.py fix      # the fixer, on the letters that most need it
    python backtest/run.py regress  # the 13 example letters: do the known misreads still show?
    python backtest/run.py kind     # letter / newsletter / template / not a letter, with the app's rules
    python backtest/run.py refresh  # re-run the 13 examples and save them as the site's saved results
    python backtest/report.py       # summary.md from whatever has run

Results go to backtest/results/<id>.json; finished letters are skipped on a re-run.
Uses NEBIUS_API_KEY from misread-test/.env, like the app.
"""
import concurrent.futures as cf
import json
import pathlib
import re
import statistics
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
import core  # noqa: E402
import fixer  # noqa: E402
import run_test as rt  # noqa: E402

TEXT, RES = HERE / "text", HERE / "results"
MANIFEST = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
LETTERS_AT_ONCE = 3
FIX_LIMIT = 15


def template_notes(text):
    """Same checks as templateNotes() in app/static/app.js."""
    notes = []
    blanks = re.findall(r"\[[^\]\n]{2,40}\]|_{5,}", text)
    if len(blanks) >= 3:
        notes.append(f"template: {len(blanks)} blanks")
    letters = len({m.lower() for m in re.findall(r"\b(?:sample|template)\s+letter\s+[A-Z0-9]\b", text, re.I)})
    openings = len(re.findall(r"^\s*Dear\b", text, re.I | re.M))
    if max(letters, openings) >= 2:
        notes.append(f"{max(letters, openings)} letters in one file")
    return notes


def load(lid):
    p = RES / f"{lid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(lid, data):
    (RES / f"{lid}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ test

def test_one(m):
    lid = m["id"]
    text = (TEXT / f"{lid}.txt").read_text(encoding="utf-8")
    words = len(text.split())
    out = {"id": lid, "group": m["group"], "hard": m["hard"], "url": m["url"], "words": words,
           "pages": m.get("pages"), "notes": template_notes(text)}
    # The site's own gate (checkText in app.js)
    if words < 20:
        out["outcome"] = "rejected: too short (no readable text)"
        return out
    if words > core.MAX_WORDS:
        out["outcome"] = f"rejected: {words:,} words is over the {core.MAX_WORDS:,}-word limit"
        return out
    t0 = time.time()
    try:
        fact = core.extract_facts(text)
        out["fact"] = fact
        out["key_seconds"] = round(time.time() - t0, 1)
        job = core.Job("test")
        res = core.run_test_job(job, text, fact)
        out["test_seconds"] = round(time.time() - t0 - out["key_seconds"], 1)
        # keep what the report needs, not every view's text
        out["test"] = {k: res[k] for k in ("status", "cards", "grid", "overall", "conditional", "located")}
        out["test"]["views"] = {v: {k: d[k] for k in ("score", "n", "misreads", "share")} for v, d in res["views"].items()}
        out["outcome"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["outcome"] = f"error: {type(e).__name__}: {e}"
        out["trace"] = traceback.format_exc()[-1500:]
    return out


def cmd_test():
    RES.mkdir(exist_ok=True)
    todo = [m for m in MANIFEST if "error" not in m and not (load(m["id"]) or {}).get("outcome")]
    print(f"{len(todo)} letters to test", flush=True)
    with cf.ThreadPoolExecutor(max_workers=LETTERS_AT_ONCE) as ex:
        for out in ex.map(test_one, todo):
            save(out["id"], out)
            t = out.get("test")
            line = (f"busy {t['overall']['busy']:5.1f}  full {t['overall']['careful']:5.1f}  wrong cards {len(t['cards'])}"
                    if t else out["outcome"])
            print(f"{out['id']:32s} {line}", flush=True)
    print(f"API calls {core.API.calls}, tokens in {core.API.tokens['in']:,} out {core.API.tokens['out']:,}")


# ------------------------------------------------------------------ audit

AUDIT_SYSTEM = """You check another system's work. You get a LETTER, a QUESTION about it, the ANSWER KEY's answer, and a busy READER's answer, which the system marked as WRONG.

Read the whole letter carefully. Decide:
- "reader_wrong": the reader's answer really conflicts with the letter and would lead them to do the wrong thing.
- "reader_ok": the reader's answer is also correct or acceptable according to the letter (for example the letter gives more than one valid date, contact or action, or the reader's answer is just less detailed). The WRONG mark is unfair.
- "key_wrong": the answer key itself misstates the letter.

Do not answer the question yourself. Reply with JSON only, exactly these two keys: {"verdict": "reader_wrong" or "reader_ok" or "key_wrong", "why": "one short sentence"}"""

QUESTION = {"need_to_act": "Does the reader need to do anything?", "action": "What does the reader need to do?",
            "deadline": "By when?", "consequence": "What happens if they don't?", "contact": "Who should they contact?"}


def audit_card(letter, card):
    user = (f"LETTER:\n<<<\n{letter}\n>>>\n\nQUESTION: {QUESTION[card['slot']]}\n"
            f"ANSWER KEY: {card['truth']}\nREADER (marked WRONG): {card['said']}\n\n"
            # repeated after the letter: on long letters the model forgets the system prompt
            "TASK: do not answer the question. Judge whether the READER's answer is really wrong. "
            'Reply with JSON only: {"verdict": "reader_wrong" or "reader_ok" or "key_wrong", "why": "one short sentence"}')
    for _ in range(2):
        out = rt.parse_json(core.API.chat(fixer.REWORD_MODEL, AUDIT_SYSTEM, user, 0.0, max_tokens=300))
        if out.get("verdict") in ("reader_wrong", "reader_ok", "key_wrong"):
            return out
        user += "\n\nReply only with the JSON verdict object."
    return {"verdict": "error", "why": "no verdict given"}


def cmd_audit():
    rows = [r for r in (load(m["id"]) for m in MANIFEST) if r and r.get("test") and r["test"]["cards"]]
    jobs = []
    for r in rows:
        letter = fixer.reflow((TEXT / f"{r['id']}.txt").read_text(encoding="utf-8"))
        for i, c in enumerate(r["test"]["cards"]):
            if c.get("audit", {}).get("verdict") not in ("reader_wrong", "reader_ok", "key_wrong"):
                jobs.append((r, i, letter, c))
    print(f"{len(jobs)} wrong-answer cards to audit", flush=True)

    def go(j):
        r, i, letter, c = j
        try:
            return j, audit_card(letter, c)
        except Exception as e:  # noqa: BLE001
            return j, {"verdict": "error", "why": str(e)[:200]}

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for (r, i, _, c), a in ex.map(go, jobs):
            r["test"]["cards"][i]["audit"] = a
            save(r["id"], r)
            print(f"{r['id']:32s} {c['slot']:12s} {a.get('verdict')}", flush=True)
    print(f"API calls {core.API.calls}, tokens in {core.API.tokens['in']:,} out {core.API.tokens['out']:,}")


# ------------------------------------------------------------------ fix

def cmd_fix():
    rows = [r for r in (load(m["id"]) for m in MANIFEST) if r and r.get("test")]
    # the letters that most need a fix: confirmed wrong answers first, then the lowest busy scores
    def need(r):
        confirmed = sum(c.get("audit", {}).get("verdict") == "reader_wrong" for c in r["test"]["cards"])
        return (-confirmed, r["test"]["overall"]["busy"])
    picks = [r for r in sorted(rows, key=need)
             if r["test"]["overall"]["busy"] < 85 and r.get("kind", "letter") == "letter"][:FIX_LIMIT]
    todo = [r for r in picks if "fix" not in r]
    print(f"{len(todo)} letters to fix", flush=True)

    def go(r):
        text = (TEXT / f"{r['id']}.txt").read_text(encoding="utf-8")
        t0 = time.time()
        try:
            out = core.run_fix_job(core.Job("fix"), text, r["fact"])
            return r, {k: out[k] for k in ("before", "after", "change", "warnings")} | {
                "tried": len(out["tried"]), "seconds": round(time.time() - t0, 1)}
        except Exception as e:  # noqa: BLE001
            return r, {"error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - t0, 1)}

    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        for r, f in ex.map(go, todo):
            r["fix"] = f
            save(r["id"], r)
            line = f.get("error") or (f"{f['before']['score']:.0f} → {f['after']['score']:.0f}  "
                                      f"misreads {f['before']['misread_rate']:.0%} → {f['after']['misread_rate']:.0%}  {f['change']['desc'][:70]}")
            print(f"{r['id']:32s} {line}", flush=True)
    print(f"API calls {core.API.calls}, tokens in {core.API.tokens['in']:,} out {core.API.tokens['out']:,}")


# ------------------------------------------------------------------ kind

def cmd_kind():
    """Classify every document with the app's own rules (core.KIND_RULES), for the report."""
    rows = [r for r in (load(m["id"]) for m in MANIFEST) if r and "kind" not in r]
    for r in [r for r in rows if (r.get("fact") or {}).get("kind")]:  # the answer key already classified it
        r["kind"] = r["fact"]["kind"]
        save(r["id"], r)
    rows = [r for r in rows if "kind" not in r]

    def go(r):
        letter = fixer.reflow((TEXT / f"{r['id']}.txt").read_text(encoding="utf-8"))[:60000]
        user = (f"DOCUMENT:\n<<<\n{letter}\n>>>\n\n{core.KIND_RULES}\n\n"
                'Reply with JSON only: {"kind": "letter" or "newsletter" or "template" or "not_a_letter"}')
        try:
            k = str(rt.parse_json(core.API.chat(fixer.REWORD_MODEL, "You classify documents.", user, 0.0, max_tokens=60)).get("kind", ""))
        except Exception as e:  # noqa: BLE001
            k = f"error: {e}"
        return r, k

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r, k in ex.map(go, rows):
            r["kind"] = k
            save(r["id"], r)
            print(f"{r['id']:32s} {k}", flush=True)


# ------------------------------------------------------------------ regression

def cmd_regress():
    """The 13 example letters with their hand-checked answer keys: do the known misreads still show?"""
    out = {}

    def go(sid):
        s = core.load_sample(sid)
        res = core.run_test_job(core.Job("test"), s["text"], s["fact"])
        old = s["test"] or {}
        return sid, {"old_busy": round(old.get("overall", {}).get("busy", float("nan"))),
                     "old_wrong": sorted(k for k, v in old.get("status", {}).items() if v == "wrong"),
                     "new_busy": round(res["overall"]["busy"]), "new_full": round(res["overall"]["careful"]),
                     "new_wrong": sorted(k for k, v in res["status"].items() if v == "wrong"),
                     "cards": [(c["slot"], c["view"], c["said"][:100]) for c in res["cards"]]}

    with cf.ThreadPoolExecutor(max_workers=LETTERS_AT_ONCE) as ex:
        for sid, r in ex.map(go, core.sample_ids()):
            out[sid] = r
            print(f"{sid:16s} busy {r['old_busy']:>3} → {r['new_busy']:>3}  full {r['new_full']:>3}  "
                  f"wrong {r['old_wrong']} → {r['new_wrong']}", flush=True)
    (HERE / "regression.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"API calls {core.API.calls}, tokens in {core.API.tokens['in']:,} out {core.API.tokens['out']:,}")


def cmd_refresh():
    """Re-run the 13 example letters with the current system and save them as the site's saved results."""
    def go(sid):
        s = core.load_sample(sid)
        res = core.run_test_job(core.Job("test"), s["text"], s["fact"])
        core.save_cache(sid, "test", res)
        return sid, res

    with cf.ThreadPoolExecutor(max_workers=LETTERS_AT_ONCE) as ex:
        for sid, res in ex.map(go, core.sample_ids()):
            wrong = sorted(k for k, v in res["status"].items() if v == "wrong")
            print(f"{sid:16s} busy {res['overall']['busy']:5.1f}  full {res['overall']['careful']:5.1f}  wrong {wrong}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    {"test": cmd_test, "audit": cmd_audit, "fix": cmd_fix, "regress": cmd_regress, "kind": cmd_kind, "refresh": cmd_refresh}[sys.argv[1]]()
