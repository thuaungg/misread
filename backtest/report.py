"""Turn backtest/results/*.json into backtest/summary.md.

    python backtest/report.py
"""
import collections
import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
SLOT = {"need_to_act": "Need to act?", "action": "What to do", "deadline": "Deadline",
        "consequence": "If they don't", "contact": "Who to contact"}


def load_all():
    rows = []
    for m in MANIFEST:
        p = HERE / "results" / f"{m['id']}.json"
        rows.append(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {**m, "outcome": "not run"})
    return rows


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def short(s, n=90):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def metrics(rows):
    ok = [r for r in rows if r.get("test")]
    cards = [c for r in ok for c in r["test"]["cards"]]
    v = collections.Counter(c.get("audit", {}).get("verdict") for c in cards)
    judged = v["reader_wrong"] + v["reader_ok"] + v["key_wrong"]
    full = [r["test"]["overall"]["careful"] for r in ok]
    return {
        "Letters tested": f"{len(ok)}",
        "Crashed": f"{sum(r['outcome'].startswith('error') for r in rows)}",
        "Median full-read score": f"{med(full):.0f}",
        "Full read under 70 (answer key or text problem)": f"{sum(f < 70 for f in full)}",
        "Median busy-reader score": f"{med([r['test']['overall']['busy'] for r in ok]):.0f}",
        "Letters with a wrong answer": f"{sum(bool(r['test']['cards']) for r in ok)}",
        "Wrong-answer cards": f"{len(cards)}",
        "Cards confirmed by the re-check": (f"{v['reader_wrong']}/{judged} ({100 * v['reader_wrong'] / judged:.0f}%)"
                                            if judged else "not checked"),
    }


def load_dir(d):
    out = []
    for m in MANIFEST:
        p = HERE / d / f"{m['id']}.json"
        out.append(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {**m, "outcome": "not run"})
    return out


def main():
    rows = load_all()
    ok = [r for r in rows if r.get("test")]
    by_outcome = collections.Counter(r["outcome"].split(":")[0] for r in rows)
    L = ["# Misread backtest: 100 letters", ""]
    if (HERE / "results_v1").exists():
        kinds = {r["id"]: r.get("kind") for r in rows}
        v1 = load_dir("results_v1")
        before, after = metrics(v1), metrics(rows)
        L += ["## Before and after the fixes", "",
              "Hand review of 30 random flags (genuine / debatable / unfair): run 2: 7 / 7 / 16, run 5: 8 / 17 / 5.", "",
              "### All 100 documents", "", "| | Before | After |", "|---|---|---|"]
        L += [f"| {k} | {before[k]} | {after[k]} |" for k in before]
        if any(kinds.values()):
            lb = metrics([r for r in v1 if kinds.get(r["id"]) == "letter"])
            la = metrics([r for r in rows if r.get("kind") == "letter"])
            L += ["", "### Real letters only (what Misread is for)", "", "| | Before | After |", "|---|---|---|"]
            L += [f"| {k} | {lb[k]} | {la[k]} |" for k in lb]
        L += [""]

    # ---------------------------------------------------------------- headline numbers
    def group_line(name, rs):
        if not rs:
            return f"| {name} | 0 | | | | |"
        busy = [r["test"]["overall"]["busy"] for r in rs]
        full = [r["test"]["overall"]["careful"] for r in rs]
        mis = sum(bool(r["test"]["cards"]) for r in rs)
        return (f"| {name} | {len(rs)} | {med(busy):.0f} | {med(full):.0f} | {mis} ({100 * mis / len(rs):.0f}%) | "
                f"{sum(f < 70 for f in full)} |")

    L += ["## What happened to each letter", ""]
    L += [f"- **{k}**: {v}" for k, v in by_outcome.most_common()]
    rejected = [r for r in rows if r["outcome"].startswith("rejected")]
    errors = [r for r in rows if r["outcome"].startswith("error")]
    L += [""]
    L += ["## Scores", "",
          "| Group | Tested | Median busy score | Median full-read score | Letters with a wrong answer | Full read under 70 |",
          "|---|---|---|---|---|---|"]
    for name, rs in [("Singapore", [r for r in ok if r["group"] == "sg"]),
                     ("US and other", [r for r in ok if r["group"] == "intl"]),
                     ("Normal letters", [r for r in ok if not r["hard"]]),
                     ("Hard cases", [r for r in ok if r["hard"]]),
                     ("Kind: letter", [r for r in ok if r.get("kind") == "letter"]),
                     ("Kind: newsletter", [r for r in ok if r.get("kind") == "newsletter"]),
                     ("Kind: template", [r for r in ok if r.get("kind") == "template"]),
                     ("Kind: not a letter", [r for r in ok if r.get("kind") == "not_a_letter"]),
                     ("All", ok)]:
        L.append(group_line(name, rs))
    L += ["", "A careful full read should score high. Under 70 means the answer key or the extracted text is the likely problem, not the letter.", ""]

    # ---------------------------------------------------------------- audit of wrong-answer cards
    cards = [(r, c) for r in ok for c in r["test"]["cards"]]
    audited = [(r, c) for r, c in cards if c.get("audit")]
    verdicts = collections.Counter(c["audit"].get("verdict") for _, c in audited)
    L += ["## Are the \"wrong answers\" really wrong?", "",
          f"{len(cards)} wrong-answer cards across {sum(bool(r['test']['cards']) for r in ok)} letters. "
          f"Each was re-checked by Nemotron 3 Ultra reading the whole letter. That re-check is generous: "
          f"judged by hand, far fewer are clear-cut. See [hand_review.md](hand_review.md) for 30 random flags per run.", ""]
    if audited:
        n = len(audited)
        for v, label in [("reader_wrong", "Really wrong (the card is right)"), ("reader_ok", "Reader was fine (unfair card)"),
                         ("key_wrong", "Answer key was wrong"), ("error", "Check failed")]:
            if verdicts.get(v):
                L.append(f"- **{label}**: {verdicts[v]} ({100 * verdicts[v] / n:.0f}%)")
        by_slot = collections.defaultdict(collections.Counter)
        for _, c in audited:
            by_slot[c["slot"]][c["audit"].get("verdict")] += 1
        L += ["", "| Question | Cards | Really wrong | Unfair | Key wrong |", "|---|---|---|---|---|"]
        for s, cnt in sorted(by_slot.items(), key=lambda kv: -sum(kv[1].values())):
            L.append(f"| {SLOT[s]} | {sum(cnt.values())} | {cnt['reader_wrong']} | {cnt['reader_ok']} | {cnt['key_wrong']} |")
    L += [""]

    # ---------------------------------------------------------------- fixes
    fixed = [r for r in ok if r.get("fix")]
    if fixed:
        good = [r for r in fixed if "error" not in r["fix"]]
        L += ["## The fixer", "",
              f"Ran on {len(fixed)} letters with the lowest busy scores (confirmed misreads first). "
              f"{len(fixed) - len(good)} stopped with a message instead of a fix.", "",
              "| Letter | Before | After | Misreads before → after | Change | Same words |", "|---|---|---|---|---|---|"]
        def no_better(f):  # the fixer now refuses these: "none of the changes did better"
            b, a = f["before"], f["after"]
            return a["misread_rate"] > b["misread_rate"] + 1e-9 or (a["misread_rate"] >= b["misread_rate"] - 1e-9 and a["score"] <= b["score"])

        for r in fixed:
            f = r["fix"]
            if "error" in f:
                L.append(f"| {r['id']} | | | | {short(f['error'], 80)} | |")
                continue
            if no_better(f):
                L.append(f"| {r['id']} | {f['before']['score']:.0f} | | | no change beat the original: the site now says so | |")
                continue
            L.append(f"| {r['id']} | {f['before']['score']:.0f} | {f['after']['score']:.0f} | "
                     f"{f['before']['misread_rate']:.0%} → {f['after']['misread_rate']:.0%} | {short(f['change']['desc'], 70)} | "
                     f"{'yes' if f['change']['keeps_wording'] else 'no'} |")
        good = [r for r in good if not no_better(r["fix"])]
        L += ["", f"{len(good)} of {len(fixed)} letters got a change that beat the original on the same re-check."]
        if good:
            gain = [r["fix"]["after"]["score"] - r["fix"]["before"]["score"] for r in good]
            L += ["", f"Median gain {med(gain):+.0f} points; {sum(g > 0 for g in gain)}/{len(good)} improved; "
                      f"{sum(r['fix']['after']['misread_rate'] < r['fix']['before']['misread_rate'] for r in good)}/{len(good)} cut misreads."]
        L += [""]

    # ---------------------------------------------------------------- hard cases
    L += ["## Hard cases", "", "| Letter | Why it's hard | What the system did |", "|---|---|---|"]
    for r in rows:
        if not r["hard"]:
            continue
        if r.get("test"):
            t = r["test"]
            did = f"busy {t['overall']['busy']:.0f}, full {t['overall']['careful']:.0f}, {len(t['cards'])} wrong-answer card(s)"
        else:
            did = r["outcome"]
        if r.get("notes"):
            did += "; warning shown: " + ", ".join(r["notes"])
        if r.get("kind") and r["kind"] != "letter":
            did += f"; classified as {r['kind'].replace('_', ' ')} (the site warns)"
        L.append(f"| {r['id']} | {r['hard']} | {did} |")
    L += [""]

    # ---------------------------------------------------------------- speed and keys
    ks = [r["key_seconds"] for r in ok if "key_seconds" in r]
    ts = [r["test_seconds"] for r in ok if "test_seconds" in r]
    if ks:
        L += ["## Speed", "", f"- Answer key: median {med(ks):.0f}s, slowest {max(ks):.0f}s",
              f"- Test (12 readings): median {med(ts):.0f}s, slowest {max(ts):.0f}s", ""]
    req = collections.Counter(str(r["fact"]["action_required"]) for r in ok)
    unstated = collections.Counter(s for r in ok for s, v in r["fact"]["facts"].items() if str(v).lower().startswith("not stated"))
    L += ["## Answer keys", "", f"- Need to act: {dict(req)}",
          f"- Questions the key said the letter doesn't answer: {dict(unstated)}", ""]

    # ---------------------------------------------------------------- every letter
    L += ["## Every letter", "", "| Letter | Words | Busy | Full | Worst wrong answer (they said → actually) | Check |", "|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("test"):
            L.append(f"| {r['id']} | {r.get('words', '')} | | | {r['outcome']} | |")
            continue
        t = r["test"]
        c = t["cards"][0] if t["cards"] else None
        worst = f"{SLOT[c['slot']]}: “{short(c['said'], 70)}” → {short(c['truth'], 60)}" if c else ""
        chk = c.get("audit", {}).get("verdict", "") if c else ""
        L.append(f"| {r['id']} | {r['words']} | {t['overall']['busy']:.0f} | {t['overall']['careful']:.0f} | {worst} | {chk} |")

    (HERE / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
