#!/usr/bin/env python3
"""Misread fixer: find the smallest change that stops skimmers misreading a letter.

1. Locate: Nemotron points to the exact sentence in the letter behind each
   must-know fact (action, deadline, consequence, contact). Code checks the
   sentence really is in the letter.
2. Propose: safe edits that keep every original word -- bold a sentence, turn
   it into a heading, move it to the top, or add a "What you need to do" box
   made only of the letter's own sentences. Plus one wording change from
   Nemotron Ultra, flagged as needing review.
3. Screen every edit with the same busy readers as run_test.py, then confirm
   the best few with more runs, so luck doesn't pick the winner.
4. Recommend the cheapest edit that does (nearly) as well as the best one.

Usage:
  python fixer.py --doc cms_nomnc
  python fixer.py --doc cms_nomnc --doc nc_renewal
  python fixer.py --doc nc_renewal --mock      # fake model, checks the code
"""
import argparse
import collections
import concurrent.futures as cf
import datetime
import difflib
import json
import os
import re
import statistics
import sys
import types

import run_test as rt

LOCATOR_MODEL = rt.GRADER_MODEL
REWORD_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"
REDUCED = ["skim", "glance20", "phone"]
COST = {"bold": 1, "heading": 1, "move_to_top": 2, "summary_box": 3, "summary_box_below_date": 3, "reword": 5}
SLOT_NAME = {"action": "what to do", "deadline": "deadline", "consequence": "what happens if not", "contact": "who to contact"}

LOCATOR_SYSTEM = """You find where a letter states each must-know fact.

You get a LETTER and the must-know FACTS. For each fact, copy the ONE sentence from the letter that most directly states it, exactly as written in the letter, character for character. Copy only from the letter; never write your own words. If the letter doesn't state that fact, use null.

Reply with JSON only:
{"action": "...", "deadline": "...", "consequence": "...", "contact": "..."}"""

REWORD_SYSTEM = """You make the smallest possible wording change to one sentence of an official letter, so that a busy reader who sees only this sentence understands the fact correctly.

Keep the meaning and the legal content. Keep it to one sentence. Spell out anything the reader would otherwise have to work out from elsewhere in the letter (for example, replace "the above date" with the actual date). Don't add new requirements.

Reply with JSON only: {"sentence": "the rewritten sentence"}"""

# ----------------------------------------------------------- text helpers


def plain(s):
    return re.sub(r"\s+", " ", s.replace("**", "").replace("## ", "")).strip()


BULLET = re.compile(r"^\s*(?:[•●▪◦\-–]|\d{1,2}[.)])\s+")


def core(s):
    """A sentence's plain words without any leading bullet or list number."""
    return BULLET.sub("", plain(s))


def bullet_of(s):
    m = BULLET.match(plain(s))
    return m.group(0) if m else ""


def words(s):
    return collections.Counter(re.findall(r"[\w$.,%'’-]+", plain(s).lower()))


LIST_ITEM = re.compile(r"^\s*(?:[•●▪◦\-–]|\d{1,2}[.)]|[a-z][.)])\s")


def reflow(doc):
    """Join PDF line-wraps into whole paragraphs. Keeps headings, list items and
    paragraph breaks, and never changes a word, so edits can work on sentences."""
    out = []
    for block in re.split(r"\n\s*\n", doc.strip()):
        lines = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if rt.is_heading(line) or LIST_ITEM.match(line) or not lines or rt.is_heading(lines[-1]):
                lines.append(line)
            else:
                lines[-1] += " " + line
        out.append("\n".join(lines))
    return re.sub(r"\*\*\s+\*\*", " ", "\n\n".join(out)) + "\n"


# A new sentence starts after . ! ? or : and a space, before a capital in any script (Latin with
# accents, Greek, Cyrillic), a letter of a script without capitals (Tamil, Hindi and the other Indian
# scripts, Arabic, Hebrew, Myanmar, Korean) or a digit; after a bold run; before a bullet; after a
# Hindi, Arabic, Urdu or Myanmar full stop and a space; or right after a CJK full stop. A number's
# full stop is no break when another number follows (Korean dates: "2025. 12. 3.") or when it numbers
# a list item at the start of a line ("1. 기간").
CAPS = "A-ZÀ-ÞΑ-ΩЀ-Я"
UNCASED = "֐-ۿऀ-෿က-႟가-힯"
SENTENCE_BREAK = re.compile(rf"(?<=[.!?:])(?<!^\d\.)(?<!^\d\d\.)(?<!\d\.(?=\s+\d))\s+(?=[\"“«(*•0-9{CAPS}{UNCASED}])"
                            rf"|(?<=\*\*)\s+(?=[{CAPS}{UNCASED}])|\s+(?=•)"
                            rf"|(?<=[।॥؟۔။])\s+|(?<=[。！？])\s*")


CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def word_count(s):
    """Words in a sentence, counted like the busy readers' views (run_test.words): scripts without
    spaces between words (Chinese, Thai, Burmese...) are measured in English-word-sized pieces."""
    return len(rt.words(plain(s)))


def sentences(doc):
    found = []
    for line in doc.split("\n"):
        if not line.strip():
            continue
        if rt.is_heading(line):
            found.append(line)
            continue
        for part in SENTENCE_BREAK.split(line):
            if word_count(part) >= 3:
                found.append(part.strip())
    return found


def match_sentence(doc, guess):
    """Map the model's quote onto a real sentence of the letter (or None)."""
    if not guess:
        return None
    best, best_r = None, 0.0
    # spaces are ignored: PDF tables scatter them (in Chinese they even fall inside words)
    g = re.sub(r"\s+", "", plain(guess).lower())
    for s in sentences(doc):
        p = re.sub(r"\s+", "", plain(s).lower())
        if not p:
            continue
        if p == g:
            return s
        if g and (g in p or p in g) and len(p) >= 0.6 * len(g):
            r = 0.99
        else:
            m = difflib.SequenceMatcher(None, g, p, autojunk=False)
            r = m.ratio()
            # The model tidies a sentence that a table broke up; most of the real sentence is still in its quote.
            if len(p) >= 12 and len(p) >= 0.4 * len(g):
                r = max(r, sum(b.size for b in m.get_matching_blocks()) / len(p))
        if r > best_r:
            best, best_r = s, r
    if best_r >= 0.85:
        return best
    # The model sometimes copies several sentences joined together: use the first one that matches.
    pieces = [p for p in re.split(r";\s+|(?<=[.!?])\s+|(?<=[。！？])", guess.strip()) if word_count(p) >= 3]
    if len(pieces) > 1:
        return next((m for m in (match_sentence(doc, p) for p in pieces) if m), None)
    return None


# ------------------------------------------------------------------ edits


def _leftover(line, s):
    """What's left of a line once the sentence is taken out ('' if only a bullet remains)."""
    rest = re.sub(r"\s{2,}", " ", line.replace(s, "", 1)).strip()
    return rest if re.sub(r"[•●▪◦\-–\s]", "", plain(rest)) else ""


def _remove(doc, s):
    lines = doc.split("\n")
    for i, line in enumerate(lines):
        if s in line:
            lines[i] = _leftover(line, s)
            return "\n".join(lines)
    raise ValueError("sentence not found")


def edit_bold(doc, s):
    return doc.replace(s, f"{bullet_of(s)}**{core(s)}**", 1)


def edit_heading(doc, s):
    lines = doc.split("\n")
    for i, line in enumerate(lines):
        if s in line:
            rest = _leftover(line, s)
            lines[i] = f"## {core(s)}" + (f"\n{rest}" if rest else "")
            return "\n".join(lines)
    raise ValueError("sentence not found")


def edit_move_to_top(doc, s):
    return f"**{core(s)}**\n\n" + _remove(doc, s)


BOX_HEADING = "What you need to do"


def summary_box(sents, heading=BOX_HEADING):
    return f"## {heading}\n" + "\n".join(f"• **{core(s)}**" for s in sents)


def edit_summary_box(doc, sents, heading=BOX_HEADING):
    return summary_box(sents, heading) + "\n\n" + doc


def first_date_block(doc):
    """Index of the first block in the top half of the letter that states a date in
    words ("March 14, 2026"). Numeric dates are skipped: near the top they are usually
    form numbers or expiry dates, not the date the letter is about."""
    blocks = re.split(r"\n\s*\n", doc.strip())
    for i, b in enumerate(blocks[: max(1, len(blocks) // 2)]):
        if re.search(rt.MONTH + r"\s+\d{1,2}", plain(b)):
            return i
    return None


def edit_summary_box_below_date(doc, sents, idx, heading=BOX_HEADING):
    blocks = re.split(r"\n\s*\n", doc.strip())
    return "\n\n".join(blocks[: idx + 1] + [summary_box(sents, heading)] + blocks[idx + 1:]) + "\n"


# Text moved to the top can no longer point upward, and can only point at a
# deadline or date if one travels with it.
POINTS_UP = re.compile(r"\b(?:the above(?: \w+)?|above date|previous(?:ly)?|earlier in this)\b", re.I)
POINTS_AT_DATE = re.compile(r"\b(?:this deadline|that deadline|this date|that date|the date on)\b", re.I)
HAS_DATE = re.compile(rt.MONTH + r"\s+\d{1,2}|\b\d{1,2}/\d{1,2}/\d{2,4}\b")


def relative_refs(pick, located):
    """Sentences a move or box takes away from what they point at ('the above date')."""
    if pick["kind"] == "summary_box_below_date":
        return []  # the box sits under the date, so "the above date" still points the right way
    if pick["kind"] == "summary_box":
        moved = [s for s in dict.fromkeys(located.values()) if s]
    elif pick["kind"] == "move_to_top":
        moved = [located[pick["slot"]]]
    else:
        return []
    date_travels = any(HAS_DATE.search(core(s)) for s in moved)
    found = []
    for s in moved:
        m = POINTS_UP.search(core(s)) or (None if date_travels else POINTS_AT_DATE.search(core(s)))
        if m:
            found.append((core(s), m.group(0)))
    return found


def keeps_wording(original, edited, added=()):
    extra = collections.Counter()
    for a in added:
        extra += words(a)
    return words(edited) == words(original) + extra


# ----------------------------------------------------------------- search


class Progress:
    """Counts readings so a caller (the web app) can show a progress bar. Does nothing by default."""

    def stage(self, label, readings):
        pass

    def tick(self):
        pass


def read_all(api, args, doc_id, fact, letter, runs, label, progress=None):
    progress = progress or Progress()
    views = {c: rt.VIEWS[c](letter) for c in REDUCED}
    jobs = [(c, r) for c in REDUCED for r in range(runs)]
    res = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for f in cf.as_completed([ex.submit(rt.run_one, api, args, doc_id, fact, c, views[c], r) for c, r in jobs]):
            try:
                res.append(f.result())
            except Exception as e:  # one failed reading shouldn't sink the whole edit
                res.append({"error": str(e)})
            progress.tick()
    ok = [r for r in res if "score" in r]
    if not ok:
        return {"label": label, "score": 0.0, "misread_rate": 1.0, "by_view": {}, "n": 0,
                "errors": [r.get("error") for r in res][:1], "slot_fail": {}}
    by_view = {c: statistics.mean(r["score"] for r in ok if r["cond"] == c) for c in REDUCED if any(r["cond"] == c for r in ok)}
    slot_fail = {s: sum(r["labels"].get(s, "found") != "found" for r in ok) / len(ok) for s in rt.SLOTS}
    mis_by_view = {c: sum(r["misread"] for r in ok if r["cond"] == c) for c in REDUCED}
    return {"label": label, "score": statistics.mean(r["score"] for r in ok), "by_view": by_view,
            "misread_rate": sum(r["misread"] for r in ok) / len(ok), "mis_by_view": mis_by_view,
            "n": len(ok), "slot_fail": slot_fail,
            "examples": [r["reader"] for r in ok if r["misread"]][:2]}


def locate(api, args, letter, fact):
    if args.mock:
        sents = sentences(letter)
        guess = {}
        for slot in rt.SLOTS:
            t = words(fact["facts"][slot])
            guess[slot] = max(sents, key=lambda s: sum((words(s) & t).values()), default=None)
    else:
        user = "LETTER:\n<<<\n" + letter + "\n>>>\n\nFACTS:\n" + json.dumps(fact["facts"], ensure_ascii=False)
        guess = rt.parse_json(api.chat(LOCATOR_MODEL, LOCATOR_SYSTEM, user, 0.0, max_tokens=1600))
    return {slot: match_sentence(letter, guess.get(slot)) for slot in rt.SLOTS}


def reword(api, args, sentence, fact_text):
    if args.mock:
        return plain(sentence) + " (mock rewrite)"
    user = f"SENTENCE:\n{plain(sentence)}\n\nTHE FACT A READER MUST GET FROM IT:\n{fact_text}"
    out = rt.parse_json(api.chat(REWORD_MODEL, REWORD_SYSTEM, user, 0.2, max_tokens=400))
    return plain(out.get("sentence", "")) or None


def build_candidates(letter, located, extra_reword=None, heading=BOX_HEADING):
    cands, seen = [], set()
    for slot, s in located.items():
        if not s or s in seen:
            continue
        seen.add(s)
        short = core(s)[:70] + ("…" if len(core(s)) > 70 else "")
        is_bold = s.startswith("**") and s.rstrip(" .").endswith("**") and s.count("**") == 2
        if not is_bold and not rt.is_heading(s):
            cands.append(("bold", slot, s, edit_bold(letter, s), f"Make the {SLOT_NAME[slot]} sentence bold: “{short}”"))
        if not rt.is_heading(s):
            cands.append(("heading", slot, s, edit_heading(letter, s), f"Turn the {SLOT_NAME[slot]} sentence into a heading: “{short}”"))
        cands.append(("move_to_top", slot, s, edit_move_to_top(letter, s), f"Move the {SLOT_NAME[slot]} sentence to the top: “{short}”"))
    uniq = list(dict.fromkeys(s for s in located.values() if s))
    if uniq:
        cands.append(("summary_box", "all", None, edit_summary_box(letter, uniq, heading),
                      f"Add a “What you need to do” box at the top, made of the letter's own {len(uniq)} key sentence(s)"))
        idx = first_date_block(letter)
        if idx is not None and any(POINTS_UP.search(core(s)) for s in uniq):
            cands.append(("summary_box_below_date", "all", None, edit_summary_box_below_date(letter, uniq, idx, heading),
                          f"Add a “What you need to do” box just below the date line, made of the letter's own {len(uniq)} key sentence(s)"))
    if extra_reword:
        slot, s, new = extra_reword
        styled = f"## {new}" if rt.is_heading(s) else f"**{new}**" if s.startswith("**") else new
        cands.append(("reword", slot, s, letter.replace(s, styled, 1),
                      f"REWORD the {SLOT_NAME[slot]} sentence (changes wording, needs review): “{new}”"))
    return cands


# ----------------------------------------------------------------- report


def fmt_view(r):
    return " · ".join(f"{c} {r['by_view'].get(c, 0):.0f}" for c in REDUCED)


class NoFix(Exception):
    """The fixer found nothing it could try; the message is meant for the person, as is."""


def compute_fix(api, args, doc_id, original, fact, log=print, progress=None):
    """Run the whole search and return everything the report (or the web app) needs."""
    progress = progress or Progress()
    letter = reflow(original)
    assert keeps_wording(original, letter), "reflow changed words"
    log(f"\n=== {fact['title']}")

    log("  1/4 locating the must-know sentences ...")
    progress.stage("Finding the sentences that matter", 0)
    located = locate(api, args, letter, fact)
    for slot, s in located.items():
        log(f"      {slot:11s} → {('“' + plain(s)[:90] + '”') if s else '(not found in the letter)'}")

    log(f"  2/4 measuring the original ({args.screen_runs} run(s) per view) ...")
    progress.stage("Reading the original like a busy person", args.screen_runs * len(REDUCED))
    base_screen = read_all(api, args, doc_id, fact, letter, args.screen_runs, "original", progress)
    log(f"      original: {base_screen['score']:.0f}  ({fmt_view(base_screen)}), misreads {base_screen['misread_rate']:.0%}")

    extra = None
    worst = max((s for s in rt.SLOTS if located.get(s)), key=lambda s: base_screen["slot_fail"].get(s, 0), default=None)
    if worst and base_screen["slot_fail"].get(worst, 0) > 0:
        progress.stage("Asking Nemotron Ultra for one careful rewrite", 0)
        new = reword(api, args, located[worst], fact["facts"][worst])
        if new and plain(new) != plain(located[worst]):
            extra = (worst, located[worst], new)

    heading = fact.get("box_heading") or BOX_HEADING
    cands = build_candidates(letter, located, extra, heading)
    checked = []
    for kind, slot, s, text, desc in cands:
        added = [plain(x) for x in dict.fromkeys(v for v in located.values() if v)] + [heading] \
            if kind.startswith("summary_box") else []
        safe = kind != "reword" and keeps_wording(letter, text, added)
        if kind != "reword" and not safe:
            log(f"      skipped (wording check failed): {desc}")
            continue
        checked.append({"kind": kind, "slot": slot, "desc": desc, "text": text, "cost": COST[kind], "keeps_wording": safe})
    if not checked:
        raise NoFix("Couldn't find the answer key's sentences in the letter, so there was nothing to move. "
                    "Check that the answer key matches this letter.")
    log(f"  3/4 screening {len(checked)} edits ({args.screen_runs} run(s) per view) ...")
    progress.stage(f"Trying {len(checked)} small changes", len(checked) * args.screen_runs * len(REDUCED))
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        screens = list(ex.map(lambda c: read_all(api, args, doc_id, fact, c["text"], args.screen_runs, c["desc"], progress), checked))
    for c, s in zip(checked, screens):
        c["screen"] = s
        log(f"      {s['score']:5.0f}  misreads {s['misread_rate']:4.0%}  {c['desc'][:95]}")

    ranked = sorted(checked, key=lambda c: (c["screen"]["misread_rate"], -c["screen"]["score"], c["cost"]))
    finalists = ranked[: args.top]
    safe_best = next((c for c in ranked if c["keeps_wording"]), None)
    if safe_best and safe_best not in finalists:
        finalists.append(safe_best)
    log(f"  4/4 confirming the top {len(finalists)} + the original ({args.confirm_runs} runs per view) ...")
    progress.stage("Re-checking the best changes", (len(finalists) + 1) * args.confirm_runs * len(REDUCED))
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        base_f = ex.submit(read_all, api, args, doc_id, fact, letter, args.confirm_runs, "original", progress)
        conf = list(ex.map(lambda c: read_all(api, args, doc_id, fact, c["text"], args.confirm_runs, c["desc"], progress), finalists))
        base = base_f.result()
    for c, s in zip(finalists, conf):
        c["confirm"] = s

    # Fewest misreads first; among those, anything within 5 points of their best score.
    best_mis = min(c["confirm"]["misread_rate"] for c in finalists)
    fewest = [c for c in finalists if c["confirm"]["misread_rate"] <= best_mis + 1e-9]
    best_score = max(c["confirm"]["score"] for c in fewest)
    good_enough = [c for c in fewest if c["confirm"]["score"] >= best_score - 5]
    # Prefer: keeps the wording, then no "points the wrong way" warning, then cheapest, then highest score.
    pick = min(good_enough, key=lambda c: (not c["keeps_wording"], bool(relative_refs(c, located)), c["cost"], -c["confirm"]["score"]))
    safe_final = [c for c in finalists if c["keeps_wording"]]
    best_safe = max(safe_final, key=lambda c: (-c["confirm"]["misread_rate"], c["confirm"]["score"])) if safe_final else None
    if not pick["keeps_wording"] and best_safe and best_safe["confirm"]["score"] >= pick["confirm"]["score"] - 10 \
            and best_safe["confirm"]["misread_rate"] <= pick["confirm"]["misread_rate"] + 1e-9:
        pick = best_safe
    # Never recommend a change that doesn't beat the original on the same re-check.
    if pick["confirm"]["misread_rate"] > base["misread_rate"] + 1e-9 or (
            pick["confirm"]["misread_rate"] >= base["misread_rate"] - 1e-9 and pick["confirm"]["score"] <= base["score"]):
        raise NoFix(f"None of the {len(checked)} changes tried did better than the original letter, so there's no fix to recommend.")
    return {"letter": letter, "located": located, "base": base, "ranked": ranked, "pick": pick, "box_heading": heading,
            "best_safe": best_safe, "refs": relative_refs(pick, located)}


def fix_one(api, args, doc_id, out_root):
    original = (rt.ROOT / "letters" / f"{doc_id}.md").read_text(encoding="utf-8")
    fact = json.loads((rt.ROOT / "facts" / f"{doc_id}.json").read_text(encoding="utf-8"))
    r = compute_fix(api, args, doc_id, original, fact)
    letter, located, base, ranked, pick, best_safe, refs = (r[k] for k in
                                                           ("letter", "located", "base", "ranked", "pick", "best_safe", "refs"))
    out = out_root / doc_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixed_letter.md").write_text(pick["text"], encoding="utf-8")
    (out / "original_reflowed.md").write_text(letter, encoding="utf-8")
    gain = pick["confirm"]["score"] - base["score"]
    L = [f"# Fixer: {fact['title']}", "",
         f"Readers: `{args.reader_model}` · Grader: `{args.grader_model}` · Locator: `{LOCATOR_MODEL}` · Rewrite: `{REWORD_MODEL}`"
         + (" · **MOCK MODEL**" if args.mock else ""),
         f"Confirmed with {args.confirm_runs} runs per busy view ({', '.join(REDUCED)}).", "",
         "## Recommended change", "",
         f"**{pick['desc']}**", "",
         "| | Busy-reader score | Misreads | By view |", "|---|---|---|---|",
         f"| Before | {base['score']:.0f} | {base['misread_rate']:.0%} | {fmt_view(base)} |",
         f"| After | **{pick['confirm']['score']:.0f}** | **{pick['confirm']['misread_rate']:.0%}** | {fmt_view(pick['confirm'])} |", "",
         f"Change in score: **{gain:+.0f} points**. "
         + ("Keeps every original word (checked by code)." if pick["keeps_wording"] else
            "⚠️ This changes the letter's wording, so it needs legal review before use."), ""]
    if not pick["keeps_wording"] and best_safe:
        L += [f"Best change that keeps the wording: {best_safe['desc']} → {best_safe['confirm']['score']:.0f}, "
              f"misreads {best_safe['confirm']['misread_rate']:.0%}.", ""]
    if refs:
        L += ["⚠️ **Check before using:** these sentences now sit away from what they point to, "
              "so a person reading them first may be confused:", ""]
        L += [f"- “{s}” — says *{w}*" for s, w in refs]
        L += ["", "Fix it by placing the box just below the thing they refer to, or by spelling it out "
              "(for example, the actual date) — a wording change that needs review.", ""]
    L += ["## The must-know sentences the fixer found", "", "| Must-know | Sentence in the letter |", "|---|---|"]
    L += [f"| {SLOT_NAME[s]} | {('“' + plain(v) + '”') if v else '*not found*'} |" for s, v in located.items()]
    L += ["", "## Every edit tried", "", "| Edit | Cost | Keeps wording | Screen score | Screen misreads | Confirmed score | Confirmed misreads |",
          "|---|---|---|---|---|---|---|"]
    for c in ranked:
        conf = c.get("confirm")
        L.append(f"| {c['desc']} | {c['cost']} | {'yes' if c['keeps_wording'] else '**no**'} | {c['screen']['score']:.0f} | "
                 f"{c['screen']['misread_rate']:.0%} | {conf['score']:.0f} | {conf['misread_rate']:.0%} |" if conf else
                 f"| {c['desc']} | {c['cost']} | {'yes' if c['keeps_wording'] else '**no**'} | {c['screen']['score']:.0f} | "
                 f"{c['screen']['misread_rate']:.0%} | | |")
    if base.get("examples"):
        L += ["", "## What busy readers concluded before the fix", ""]
        L += [f"- action → “{e.get('action')}”; deadline → “{e.get('deadline')}”; consequence → “{e.get('consequence')}”"
              for e in base["examples"]]
    if pick["confirm"].get("examples"):
        L += ["", "## Misreads that remain after the fix", ""]
        L += [f"- action → “{e.get('action')}”; deadline → “{e.get('deadline')}”; consequence → “{e.get('consequence')}”"
              for e in pick["confirm"]["examples"]]
    L += ["", "The fixed letter is saved as `fixed_letter.md` next to this report."]
    if args.mock:
        L += ["", "> **Mock run**: fake keyword model. This only proves the code works."]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps(
        {"located": located, "original": base, "candidates": [{k: v for k, v in c.items() if k != "text"} for c in ranked],
         "pick": pick["desc"]}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {pick['desc']}")
    print(f"    busy-reader score {base['score']:.0f} → {pick['confirm']['score']:.0f}, "
          f"misreads {base['misread_rate']:.0%} → {pick['confirm']['misread_rate']:.0%}"
          + ("" if pick["keeps_wording"] else "  (changes wording: needs review)"))
    for s, w in refs:
        print(f"    ⚠ check: “{s[:70]}…” says “{w}”, which now points the wrong way")
    return out / "report.md"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--doc", action="append", required=True, help="letter id from letters/ (repeatable)")
    p.add_argument("--mock", action="store_true", help="fake model, no key needed")
    p.add_argument("--screen-runs", type=int, default=1)
    p.add_argument("--confirm-runs", type=int, default=3)
    p.add_argument("--top", type=int, default=3, help="how many screened edits to confirm")
    p.add_argument("--reader-model", default=rt.READER_MODEL)
    p.add_argument("--grader-model", default=rt.GRADER_MODEL)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    args.think = False

    rt.load_env(rt.ROOT / ".env")
    key = os.environ.get("NEBIUS_API_KEY", "")
    if not args.mock and not key:
        sys.exit("No NEBIUS_API_KEY found. Copy .env.example to .env and paste your key in it.")
    for d in args.doc:
        if not (rt.ROOT / "letters" / f"{d}.md").exists():
            sys.exit(f"No letter called {d!r} in letters/.")
    api = rt.Api(key, args.mock)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-mock" if args.mock else "")
    out_root = rt.ROOT / "results" / f"fix-{stamp}"
    reports = [fix_one(api, args, d, out_root) for d in args.doc]
    if not args.mock:
        print(f"\nAPI calls: {api.calls} · tokens in {api.tokens['in']:,} / out {api.tokens['out']:,}")
    print("\nReports:")
    for r in reports:
        print(f"  {r}")


if __name__ == "__main__":
    main()
