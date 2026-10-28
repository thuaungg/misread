#!/usr/bin/env python3
"""Misread 48-hour test.

Question: if you only see a letter the way a busy person does, do you
miss -- or get WRONG -- what you have to do?

For each letter in letters/ we build "views" (what a skimmer actually
sees), ask a Nemotron reader what it must do, then grade its answers
against the must-know facts in facts/. The summary ends with a
GO / NO-GO verdict.

Usage:
  python run_test.py --dry-run   # only build the views; no API calls
  python run_test.py --mock      # fake model; checks the pipeline works
  python run_test.py             # real run on Nebius Token Factory
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import os
import pathlib
import random
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent
API_URL = "https://api.tokenfactory.nebius.com/v1/chat/completions"
READER_MODEL = "nvidia/Nemotron-3_5-Lightning"
GRADER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
SLOTS = ["action", "deadline", "consequence", "contact"]
CONDITIONS = ["full", "skim", "glance20", "phone"]
CONDITION_INFO = {
    "full": "careful full read (baseline)",
    "skim": "headings, bold text and the first sentence of each paragraph",
    "glance20": "about 20% of the words, read top-down in an F-pattern",
    "phone": "first screen on a phone (~110 words), no scrolling",
    "preview": "notification / email preview (first ~180 characters)",
}

# ---------------------------------------------------------------- views
#
# Grounding: Nielsen Norman Group eye-tracking found people read at most
# 28% of the words on a page (20% is more likely) and 79% scan rather
# than read; scanning follows F-shaped and "layer-cake" (headings only)
# patterns. These functions approximate those patterns from text.

SKIP = "…"


def blocks(doc):
    return [b.strip("\n").split("\n") for b in re.split(r"\n\s*\n", doc.strip()) if b.strip()]


def is_heading(line):
    return line.startswith("## ")


# Words, for the busy readers' views. Some scripts don't put spaces between words, so a word is
# measured instead: Chinese, Japanese and Korean, two characters; Thai, Lao and Khmer, six letters;
# Burmese (which spaces only between phrases), two or three syllables. Each is about one English word
# (measured on translations of the same letter). A piece that carries on its neighbour's word starts
# with GLUE, and join_words puts the text back together without adding spaces.
CJK_RUN = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]+")
DENSE_RUN = re.compile(r"(?P<cjk>[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]+)"
                       r"|(?P<thai>[\u0e00-\u0eff\u1780-\u17ff]+)|(?P<my>[\u1000-\u109f]+)")
# a Burmese syllable starts at a consonant or independent vowel that isn't killed (asat) or stacked
MY_SYLLABLE = re.compile(r"[\u1000-\u1021\u1023-\u102a\u103f\u104c-\u104f\u1040-\u1049](?![\u103a\u1039])")
GLUE = "\x00"


def _dense_pieces(m):
    run = m.group()
    if m.group("cjk"):
        return [run[i:i + 2] for i in range(0, len(run), 2)]
    if m.group("thai"):
        return [run[i:i + 6] for i in range(0, len(run), 6)]
    starts = [s.start() for s in MY_SYLLABLE.finditer(run)]
    if not starts or starts[0] != 0:
        starts = [0] + starts
    cuts, k, size = [0], 0, 2
    while k + size < len(starts):  # 2, 3, 2, 3 ... syllables: 2.5 a word on average
        k += size
        cuts.append(starts[k])
        size = 5 - size
    return [run[a:b] for a, b in zip(cuts, cuts[1:] + [len(run)])]


def words(text):
    out = []
    for chunk in text.split():
        pieces, at = [], 0
        for m in DENSE_RUN.finditer(chunk):
            if m.start() > at:
                pieces.append(chunk[at:m.start()])
            pieces += _dense_pieces(m)
            at = m.end()
        if at < len(chunk):
            pieces.append(chunk[at:])
        out += [pieces[0]] + [GLUE + p for p in pieces[1:]]
    return out


def join_words(ws):
    return "".join(w[1:] if w.startswith(GLUE) else (" " + w if i else w) for i, w in enumerate(ws))


def first_sentence(text, max_words=15):
    m = re.search(r"^(.+?(?:[.!?:](?=\s|$)|[。！？：]))", text)
    s = m.group(1) if m else text
    w = words(s)
    cut = len(w) > max_words or len(s) < len(text)
    return join_words(w[:max_words]) + (" " + SKIP if cut else "")


def view_full(doc):
    return doc.strip()


def view_skim(doc):
    out = []
    for b in blocks(doc):
        kept, para = [], []
        for line in b:
            if is_heading(line):
                if para:
                    kept.append(_skim_para(" ".join(para)))
                    para = []
                kept.append(line)
            else:
                para.append(line)
        if para:
            kept.append(_skim_para(" ".join(para)))
        out.append("\n".join(k for k in kept if k))
    return "\n\n".join(o for o in out if o)


def balance(s):
    """Close a bold marker left open when a fragment is cut mid-run."""
    return s + "**" if s.count("**") % 2 else s


def _skim_para(text):
    # A skimmer reads bold text in full but only the opening of plain paragraphs.
    text = re.sub(r"\*\*\s+\*\*", " ", text)  # join bold runs split across lines
    plain = text.replace("**", "")
    bold = [b.strip() for b in re.findall(r"\*\*(.+?)\*\*", text) if b.strip()]
    head = "" if text.startswith("**") else first_sentence(plain)
    head_core = head.replace(SKIP, "").strip()
    pieces = ([head] if head else []) + [f"**{b}**" for b in bold if b not in head_core]
    shown = " ".join(pieces)
    if len(words(shown.replace("**", "").replace(SKIP, ""))) < len(words(plain)) and not shown.endswith(SKIP):
        shown += " " + SKIP
    return shown.strip()


def view_glance(doc, share=0.20, top_share=0.08, scan_words=7):
    total = len(words(doc))
    budget, top_budget, used = int(total * share), int(total * top_share), 0
    out = []
    for b in blocks(doc):
        if used >= budget:
            out.append(SKIP)
            break
        text_words = words(" ".join(b))
        if used < top_budget:  # top bars of the F: read fully
            take = text_words[: max(0, top_budget - used + 15)]
            out.append(balance(join_words(take)) + (" " + SKIP if len(take) < len(text_words) else ""))
            used += len(take)
        else:  # stem of the F: headings, or the left edge of each paragraph
            heads = [line for line in b if is_heading(line)]
            if heads:
                out.append("\n".join(heads))
                used += sum(len(words(h)) for h in heads)
            else:
                take = text_words[:scan_words]
                out.append(balance(join_words(take)) + (" " + SKIP if len(take) < len(text_words) else ""))
                used += len(take)
    return "\n\n".join(out)


def view_phone(doc, n=110):
    w = words(doc)
    return balance(join_words(w[:n])) + (f"\n\n{SKIP} (you didn't scroll further)" if len(w) > n else "")


def view_preview(doc, chars=180):
    flat = re.sub(r"\s+", " ", doc).strip()
    return flat[:chars] + (SKIP if len(flat) > chars else "")


VIEWS = {"full": view_full, "skim": view_skim, "glance20": view_glance, "phone": view_phone, "preview": view_preview}

# --------------------------------------------------------------- prompts

READER_SYSTEM = """You are an ordinary adult who has just received this letter. You did not read all of it: you only noticed the parts shown to you. "…" marks text you skipped or didn't notice.

Answer from what you noticed, the way you honestly understand it. Do not use outside knowledge about how these kinds of letters or programs usually work, and do not assume anything the text you saw doesn't say. If what you saw doesn't tell you something, use null.

Even if you decide you don't need to do anything, still say what you noticed the letter asking for, any date it gives, what it warns about, and who it says to contact.

Write your answers in the same language as the letter, but keep "need_to_act" as "yes", "no" or "not sure" in English.

Reply with JSON only, no other text:
{"need_to_act": "yes" or "no" or "not sure",
 "action": "what you think you need to do" or null,
 "deadline": "by when" or null,
 "consequence": "what happens if you don't, or the main warning the letter gives" or null,
 "contact": "who to contact and how" or null}"""

GRADER_SYSTEM = """You check whether a reader understood a letter. You get the TRUE must-know facts (from a careful person who read the whole letter) and the READER's answers (from someone who may have only skimmed it).

For each of action, deadline, consequence, contact, label the reader's answer:
- "found": it conveys the essential point of the true fact. Wording can differ and minor details can be missing.
- "missing": the reader gave nothing, said they don't know or that the letter doesn't say, was too vague to act on, or talked about a different point that the true fact neither confirms nor contradicts.
- "wrong": the reader is confidently mistaken in a way that conflicts with the true fact: a different date or amount, the opposite or a harmful action, saying nothing bad happens when something does, or sending them to a different organisation than the one in the true fact.

"Wrong" is a serious charge, so use it only for a real conflict. For "contact", naming a different person, office, phone line or website of the same organisation is not wrong.

Judge dates only against the true facts. These are sample letters, so dates in the past are expected: never mark a date wrong just because its year has passed.

If a true fact says there is nothing (no action needed right now, no deadline), then an answer that says so, or null, counts as "found".

If a true fact lists several items, an answer that correctly gives one of them (especially the first) counts as "found".

Reply with JSON only, no other text:
{"action": "...", "deadline": "...", "consequence": "...", "contact": "...", "note": "one short sentence on the most important problem, or empty"}

Label only the facts you were given."""

# ------------------------------------------------------------------ api


class Api:
    def __init__(self, key, mock):
        self.key, self.mock = key, mock
        self.use_json_mode, self.use_think_kw = True, True
        self.lock = threading.Lock()
        self.tokens = {"in": 0, "out": 0}
        self.calls = 0

    def chat(self, model, system, user, temperature, max_tokens=700, think=False):
        if self.mock:
            return mock_reply(system, user)
        for attempt in range(7):
            body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if self.use_json_mode:
                body["response_format"] = {"type": "json_object"}
            if self.use_think_kw:
                body["chat_template_kwargs"] = {"enable_thinking": bool(think)}
            req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    d = json.load(r)
                with self.lock:
                    self.calls += 1
                    u = d.get("usage") or {}
                    self.tokens["in"] += u.get("prompt_tokens", 0)
                    self.tokens["out"] += u.get("completion_tokens", 0)
                return d["choices"][0]["message"].get("content") or ""
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:400]
                if e.code == 401:
                    sys.exit("API key was rejected (401). Check NEBIUS_API_KEY in your .env file.")
                if e.code == 404 and "model" in msg.lower():
                    sys.exit(f"Model not found: {model}. Pass --reader-model / --grader-model. Server said: {msg}")
                if e.code in (400, 422):
                    low = msg.lower()
                    if self.use_think_kw and ("chat_template" in low or "enable_thinking" in low or "extra" in low):
                        self.use_think_kw = False
                        continue
                    if self.use_json_mode and ("response_format" in low or "json" in low):
                        self.use_json_mode = False
                        continue
                    raise RuntimeError(f"HTTP {e.code}: {msg}")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(min(60, 2 ** attempt + random.random()))
                    continue
                raise RuntimeError(f"HTTP {e.code}: {msg}")
            except (urllib.error.URLError, TimeoutError):
                time.sleep(min(60, 2 ** attempt + random.random()))
        raise RuntimeError("gave up after repeated network errors")


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    # A reply cut off by the token limit: close it at the last safe point and keep what arrived.
    start = text.find("{")
    if start >= 0:
        body = text[start:]
        for end in range(len(body), 0, -1):
            if body[end - 1] in ',"':
                for tail in ("}", "\"}", "null}"):
                    try:
                        out = json.loads(body[:end].rstrip(",") + tail)
                        if isinstance(out, dict):
                            return out
                    except ValueError:
                        continue
    raise ValueError(f"no JSON in reply: {text[:200]!r}")


# ----------------------------------------------------------------- mock
# A crude keyword "model" so the whole pipeline can be checked without a key.

MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def mock_reply(system, user):
    if system is READER_SYSTEM:
        v = user
        date = re.search(MONTH + r" \d{1,2}(, \d{4})?", v)
        phone = re.search(r"\(?\d{3}\)?[ -]?\d{3}-\d{4}|1-800-[\dx-]+", v)
        act = re.search(r"[^.\n]*\b(return|pay|respond|renew|take|provide|call)\b[^.\n]*", v, re.I)
        bad = re.search(r"[^.\n]*\b(lose|penalt|change|911)\b[^.\n]*", v, re.I)
        calm = re.search(r"has not changed|continued at the same level", v, re.I)
        need = "no" if calm and not date else ("yes" if act else "not sure")
        return json.dumps({"need_to_act": need, "action": act.group(0).strip() if act else None,
                           "deadline": date.group(0) if date else None,
                           "consequence": bad.group(0).strip() if bad else None,
                           "contact": phone.group(0) if phone else None})
    truth = json.loads(user.split("TRUE FACTS:\n", 1)[1].split("\n\nREADER")[0])
    reader = json.loads(user.split("READER'S ANSWERS:\n", 1)[1])
    out = {}
    for s in SLOTS:
        a, t = (reader.get(s) or "").lower(), truth[s].lower()
        if not a:
            out[s] = "missing"
        elif s == "deadline":
            out[s] = "found" if any(tok in t for tok in re.findall(r"[a-z]+ \d{1,2}", a)) else "wrong"
        else:
            shared = set(re.findall(r"[a-z0-9]{4,}", a)) & set(re.findall(r"[a-z0-9]{4,}", t))
            out[s] = "found" if len(shared) >= 2 else "missing"
    out["note"] = ""
    return json.dumps(out)


# ------------------------------------------------------------ the test

NOT_STATED = re.compile(r"^\W*(?:not stated|none\b|n/?a\b|nothing\b|there is no\b|no (?:specific |explicit )?(?:deadline|consequence|action|contact|date))", re.I)


INVENTED_TASK_SYSTEM = """A person read a letter that asks nothing of them, and described what they think they now have to do.

Answer "sender" if it means doing something with or for whoever sent the letter that a real person would act on: pay, reply, respond, submit or send something, sign, call or email them, apply, visit, or go to an appointment.
Answer "self" if it only means being aware, waiting, keeping the letter, preparing, telling their family, or reading more information.

Reply with JSON only: {"kind": "sender" or "self"}"""


def invented_task(api, args, action):
    """True if a reader of a no-action letter thinks they must do something for the sender."""
    if not action:
        return False
    out = parse_json(api.chat(args.grader_model, INVENTED_TASK_SYSTEM, f"What they think they have to do: {action}", 0.0, max_tokens=60))
    return str(out.get("kind", "")).lower().startswith("sender")


# The reader model sometimes copies the reply format back instead of answering ("by when").
FORM_HINTS = {"what you think you need to do", "by when", "who to contact and how",
              "what happens if you don't, or the main warning the letter gives", "..."}


SAYS_NOTHING = re.compile(r"\b(?:does not|doesn't|did not|didn't|do not|don't) (?:explicitly |clearly )?(?:say|state|specify|mention|provide|give|list|include)\b"
                          r"|\b(?:is|are|was|were|isn't|aren't)\s+not (?:stated|specified|mentioned|provided)\b"
                          r"|^\W*not (?:stated|specified|mentioned|provided)\b|^\W*(?:unknown|unclear|none|n/?a)\W*$"
                          r"|\bno (?:specific |explicit |clear )?(?:consequence|deadline|contact|date|penalty)s? (?:is |are |was )?"
                          r"(?:mentioned|given|stated|listed|specified|provided)\b"
                          r"|\bnot (?:specified|stated|given|shown|mentioned) (?:in|on)\b", re.I)


def echoes_form(value, slot=None):
    """True if the answer is no answer: the reply format copied back, or (for a date, warning
    or contact) "the letter doesn't say"."""
    if not isinstance(value, str):
        return False
    if value.strip().strip('."').lower() in FORM_HINTS:
        return True
    return slot in ("deadline", "consequence", "contact") and bool(SAYS_NOTHING.search(value))


def scored_slots(fact):
    """The questions this letter can be marked on. A fact the letter doesn't state can't be misread,
    and when nothing is required, "what to do" is covered by "need to act?"."""
    required = fact["action_required"]
    out = [] if required == "conditional" else ["need_to_act"]
    for s in SLOTS:
        if (s == "action" and required is False) or NOT_STATED.match(str(fact["facts"].get(s) or "")):
            continue
        out.append(s)
    return out


# ------------------------------------------------------------ the double-check
# The grader only sees the answer key, so it can't tell "a different answer the letter also
# gives" from a real misunderstanding. Every "wrong" is checked once against the letter itself.

VERIFY_SYSTEM = """You check one answer a busy reader gave about a letter they skimmed. You get the LETTER, the QUESTION, what a CAREFUL READER took from the letter (to show what the question is about; the letter is what counts), and the READER's ANSWER.

Decide which is true:
- "consistent": the answer agrees with the letter. It may be partial, less detailed, or name one of several valid options (another date, office, phone line or step the letter also gives).
- "conflicts": the answer is a real misunderstanding that the letter contradicts, and acting on it would hurt the reader: a date or amount that is not the one the letter gives for this, a step the letter does not ask for, a different organisation to contact, or saying nothing bad happens when the letter warns of something.
For a contact, any person, office, phone number or website of the same organisation as the letter's contact is "consistent"; only a different organisation conflicts.
- "off_point": the answer doesn't really answer the question (a fragment, something unrelated, or a vague remark), without contradicting the letter.

Reply with JSON only: {"verdict": "consistent" or "conflicts" or "off_point", "why": "one short sentence"}"""

QUESTION = {"need_to_act": "Do you need to do anything because of this letter? If yes, what?",
            "action": "What do you need to do?", "deadline": "By when?",
            "consequence": "What happens if you don't do it?", "contact": "Who should you contact, and how?"}


def said_text(slot, reader):
    """A reader's answer as one sentence, the way the results screen shows it."""
    if slot == "need_to_act":
        if str(reader.get("need_to_act", "")).lower() == "no":
            return "No — I don't need to do anything."
        what = reader.get("action")
        return f"Yes — I have to {what[0].lower() + what[1:]}" if what else "Yes — I have to do something."
    return reader.get(slot) or "—"


def truth_text(slot, fact):
    if slot == "need_to_act":
        return "Yes — you have to act." if fact["action_required"] is True else "No — nothing is needed right now."
    return fact["facts"][slot]


def verify_answer(api, args, letter, slot, said, careful):
    user = (f"LETTER:\n<<<\n{letter}\n>>>\n\nQUESTION: {QUESTION[slot]}\nCAREFUL READER: {careful}\nREADER'S ANSWER: {said}\n\n"
            "TASK: judge the reader's answer against the letter. Reply with JSON only: "
            '{"verdict": "consistent" or "conflicts" or "off_point", "why": "one short sentence"}')
    for _ in range(2):
        out = parse_json(api.chat(args.grader_model, VERIFY_SYSTEM, user, 0.0, max_tokens=200))
        if out.get("verdict") in ("consistent", "conflicts", "off_point"):
            return out["verdict"]
    return "conflicts"  # no clear verdict: keep the grader's call


SAME_ORG_SYSTEM = """Two answers to "who should I contact about this letter?". Do they point to the same organisation? An answer that names only a role or a phone number belongs to the organisation that sent the letter, unless it says otherwise.
Different people, offices, phone numbers, emails or websites of one organisation count as the same organisation (a school's principal and its general office; Ford's customer service and a Ford dealer; two IRS phone numbers).
A different organisation means somebody else entirely (a nursing home instead of the Medicare appeals reviewer; Medicare's general helpline instead of the separate appeals organisation named in the letter).
Reply with JSON only: {"same_org": true or false}"""


def same_org(api, args, title, said, careful):
    """Contacts get a narrow question: the general check is too strict about which office or number."""
    out = parse_json(api.chat(args.grader_model, SAME_ORG_SYSTEM,
                              f"LETTER: {title}" + chr(10) + f"ANSWER A (reader): {said}" + chr(10) + f"ANSWER B (letter): {careful}",
                              0.0, max_tokens=40))
    return out.get("same_org") is True or str(out.get("same_org")).lower() == "true"


def double_check(api, args, letter, fact, results):
    """Re-label each "wrong" that the letter doesn't actually contradict. Changes results in place."""
    pairs = {}
    for r in results:
        for s, v in (r.get("labels") or {}).items():
            if v == "wrong":
                pairs.setdefault((s, said_text(s, r["reader"])), []).append(r)
    if not pairs:
        return
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        verdicts = dict(zip(pairs, ex.map(lambda k: _safe_verify(api, args, letter, k[0], k[1], truth_text(k[0], fact),
                                                                 fact.get("title", "")), pairs)))
    for (s, _), rs in pairs.items():
        new = {"consistent": "found", "off_point": "missing"}.get(verdicts[(s, _)])
        for r in rs:
            if new:
                r["labels"][s] = new
            r["score"] = 100 * sum(v == "found" for v in r["labels"].values()) / len(r["labels"])
            r["misread"] = any(v == "wrong" for v in r["labels"].values())


def _safe_verify(api, args, letter, slot, said, careful, title=""):
    try:
        if slot == "contact":
            return "consistent" if same_org(api, args, title, said, careful) else "conflicts"
        return verify_answer(api, args, letter, slot, said, careful)
    except Exception:  # a failed check keeps the grader's label
        return "conflicts"


def run_one(api, args, doc_id, fact, cond, view, run_idx):
    base = {"doc": doc_id, "cond": cond, "run": run_idx}
    language = fact.get("language") or "English"
    ask = "" if language.lower() in ("english", "en") else f"\n\nThe letter is in {language}. Write your answers in {language}."
    reader_raw = api.chat(args.reader_model, READER_SYSTEM,
                          f"What you noticed of the letter:\n\n<<<\n{view}\n>>>{ask}", args.temperature,
                          max_tokens=4000 if args.think else 700, think=args.think)
    try:
        reader = parse_json(reader_raw)
    except Exception as e:
        return {**base, "error": f"reader: {e}", "reader_raw": reader_raw}
    reader = {k: (None if echoes_form(v, k) else v) for k, v in reader.items()}
    slots = scored_slots(fact)
    asked = [k for k in SLOTS if k in slots]
    truth = {k: fact["facts"][k] for k in asked}
    answers = {k: reader.get(k) for k in asked}
    required = fact["action_required"]
    labels = {}
    if truth:
        grader_user = ("TRUE FACTS:\n" + json.dumps(truth, ensure_ascii=False) +
                       "\n\nREADER'S ANSWERS:\n" + json.dumps(answers, ensure_ascii=False))
        grader_raw = api.chat(args.grader_model, GRADER_SYSTEM, grader_user, 0.0, max_tokens=500)
        try:
            grade = parse_json(grader_raw)
        except Exception as e:
            return {**base, "error": f"grader: {e}", "reader": reader, "grader_raw": grader_raw}
    else:
        grade = {}
    need = str(reader.get("need_to_act", "")).strip().lower()
    if required is True:
        labels["need_to_act"] = "found" if need == "yes" else "wrong" if need == "no" else "missing"
    elif required is False:  # nothing to do: wrong only if they think they must do something for the sender
        try:
            invented = need == "yes" and invented_task(api, args, reader.get("action"))
        except Exception as e:
            return {**base, "error": f"task check: {e}", "reader": reader}
        labels["need_to_act"] = "wrong" if invented else "found"
    # "only if ..." letters have no single right yes/no, so need_to_act isn't scored for them
    labels.update({s: str(grade.get(s, "missing")).lower() for s in slots if s != "need_to_act"})
    labels = {k: (v if v in ("found", "missing", "wrong") else "missing") for k, v in labels.items()}
    score = 100 * sum(v == "found" for v in labels.values()) / len(labels) if labels else 100.0
    return {**base, "labels": labels, "score": score, "misread": any(v == "wrong" for v in labels.values()),
            "reader": reader, "note": grade.get("note", "")}


def load_env(path):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#") and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="only build and save the views")
    p.add_argument("--mock", action="store_true", help="use a fake model (no key needed)")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--conditions", default=",".join(CONDITIONS))
    p.add_argument("--docs", default="", help="comma-separated letter ids (default: all)")
    p.add_argument("--reader-model", default=READER_MODEL)
    p.add_argument("--grader-model", default=GRADER_MODEL)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--think", action="store_true", help="let the reader model reason before answering")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()

    load_env(ROOT / ".env")
    key = os.environ.get("NEBIUS_API_KEY", "")
    if not (args.dry_run or args.mock) and not key:
        sys.exit("No NEBIUS_API_KEY found. Copy .env.example to .env and paste your key in it.")

    conds = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for c in conds:
        if c not in VIEWS:
            sys.exit(f"unknown condition {c!r}; choose from {', '.join(VIEWS)}")
    doc_ids = [d.strip() for d in args.docs.split(",") if d.strip()] or \
        sorted(f.stem for f in (ROOT / "letters").glob("*.md"))
    docs = {d: (ROOT / "letters" / f"{d}.md").read_text(encoding="utf-8") for d in doc_ids}
    facts = {d: json.loads((ROOT / "facts" / f"{d}.json").read_text(encoding="utf-8")) for d in doc_ids}

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-mock" if args.mock else "-dry" if args.dry_run else "")
    out = ROOT / "results" / stamp
    (out / "views").mkdir(parents=True, exist_ok=True)
    views = {}
    for d in doc_ids:
        for c in conds:
            views[(d, c)] = VIEWS[c](docs[d])
            (out / "views" / f"{d}__{c}.txt").write_text(views[(d, c)], encoding="utf-8")
    print(f"Built {len(views)} views in {out.relative_to(ROOT) / 'views'}")
    for d in doc_ids:
        full = len(docs[d].split())
        shares = "  ".join(f"{c}={100 * len(views[(d, c)].split()) // full}%" for c in conds)
        print(f"  {d:16s} {shares}  (share of words visible)")
    if args.dry_run:
        print("\nDry run: open the views folder to see exactly what each 'reader' gets to see.")
        return

    api = Api(key, args.mock)
    jobs = [(d, c, r) for d in doc_ids for c in conds for r in range(args.runs)]
    print(f"\nRunning {len(jobs)} readings ({len(doc_ids)} letters x {len(conds)} views x {args.runs} runs)"
          f" with reader={args.reader_model}{' (mock)' if args.mock else ''} ...")
    results, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex, \
            open(out / "calls.jsonl", "w", encoding="utf-8") as log:
        futs = [ex.submit(run_one, api, args, d, facts[d], c, views[(d, c)], r) for d, c, r in jobs]
        for f in cf.as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                res = {"error": str(e)}
            results.append(res)
            log.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} done")
    summarize(out, results, doc_ids, conds, facts, args, api)


# -------------------------------------------------------------- summary

ICON = {"found": "✅", "missing": "⬜", "wrong": "🟥"}
ORDER = ["found", "missing", "wrong"]


def summarize(out, results, doc_ids, conds, facts, args, api):
    ok = [r for r in results if "score" in r]
    errors = [r for r in results if "error" in r]
    cell = {}
    for r in ok:
        cell.setdefault((r["doc"], r["cond"]), []).append(r)
    reduced = [c for c in conds if c != "full"]

    lines = [f"# Misread 48-hour test: results ({out.name})", "",
             f"Reader: `{args.reader_model}` (thinking {'on' if args.think else 'off'}, temperature {args.temperature})"
             f" · Grader: `{args.grader_model}` · Runs per view: {args.runs}" + (" · **MOCK MODEL**" if args.mock else ""), "",
             "Score = share of the must-knows the reader got right: need to act? what, by when, what if not, who to contact."
             " ('Only if' letters skip the need-to-act question, since there is no single right yes/no.)",
             "**Misread** = the reader gave a confident *wrong* answer, e.g. 'no, I don't need to do anything'.", "",
             "| View | What the reader sees |", "|---|---|"]
    lines += [f"| {c} | {CONDITION_INFO[c]} |" for c in conds] + [""]

    doc_stats = {}
    for d in doc_ids:
        f = facts[d]
        lines += [f"## {f['title']}", f"*Expected design: {f['design']}.* {f.get('trap', '')}", "",
                  "| View | Score | Misreads | Need to act? | Action | Deadline | Consequence | Contact |",
                  "|---|---|---|---|---|---|---|---|"]
        means, per_run = {}, {}
        for c in conds:
            rs = cell.get((d, c), [])
            if not rs:
                lines.append(f"| {c} | n/a | | | | | | |")
                continue
            means[c] = statistics.mean(r["score"] for r in rs)
            for r in rs:
                per_run.setdefault(r["run"], []).append(r["score"])
            tally = {k: " ".join(ICON[x] for x in sorted((r["labels"][k] for r in rs if k in r["labels"]), key=ORDER.index)) or "—"
                     for k in ["need_to_act"] + SLOTS}
            lines.append(f"| {c} | {means[c]:.0f} | {sum(r['misread'] for r in rs)}/{len(rs)} | {tally['need_to_act']} | "
                         f"{tally['action']} | {tally['deadline']} | {tally['consequence']} | {tally['contact']} |")
        run_means = [statistics.mean(v) for v in per_run.values() if len(v) == len(conds)]
        red = [means[c] for c in reduced if c in means]
        doc_stats[d] = {"means": means,
                        "range": (max(means.values()) - min(means.values())) if means else 0,
                        "spread": (max(run_means) - min(run_means)) if len(run_means) > 1 else 0.0,
                        "reduced_mean": statistics.mean(red) if red else None}
        examples = [r for c in reduced for r in cell.get((d, c), []) if r["misread"]]
        if examples:
            lines += ["", "**What skimming readers concluded (misreads):**", ""]
            seen = set()
            for r in examples:
                key = (r["cond"], str(r["reader"].get("need_to_act")), str(r["reader"].get("action")))
                if key in seen or len(seen) >= 4:
                    continue
                seen.add(key)
                wrong = [k for k, v in r["labels"].items() if v == "wrong"]
                note = f" — {r['note']}" if r.get("note") else ""
                lines.append(f"- *{r['cond']}*: need to act → **{r['reader'].get('need_to_act')}**; "
                             f"action → “{r['reader'].get('action') or '(nothing)'}”; deadline → “{r['reader'].get('deadline') or '(nothing)'}” "
                             f"(wrong: {', '.join(wrong)}){note}")
        lines += ["", f"Run-to-run spread: {doc_stats[d]['spread']:.0f} points", ""]

    full_scores = [s["means"]["full"] for s in doc_stats.values() if "full" in s["means"]]
    control = statistics.mean(full_scores) if full_scores else 0
    signal_docs = [d for d, s in doc_stats.items() if s["range"] >= 25]
    misread_cells = [(d, c) for d in doc_ids for c in reduced
                     if cell.get((d, c)) and sum(r["misread"] for r in cell[(d, c)]) * 2 > len(cell[(d, c)])]
    spreads = [s["spread"] for s in doc_stats.values()]
    noise = statistics.median(spreads) if spreads else 0
    checks = [
        ("Control: careful full reads mostly correct (avg >= 70)", control >= 70, f"avg {control:.0f}"),
        ("Signal: skimming changes the result (>= 2 letters with a >= 25-point gap between views)",
         len(signal_docs) >= 2, f"{len(signal_docs)} letters: {', '.join(signal_docs) or 'none'}"),
        ("Misreads are common: >= 3 letters where most runs of some view reach a confident WRONG answer",
         len({d for d, _ in misread_cells}) >= 3,
         f"{len({d for d, _ in misread_cells})} letters: " + (", ".join(f"{d}/{c}" for d, c in misread_cells) or "none")),
        ("Stable: run-to-run spread <= 10 points (median across letters)", noise <= 10, f"median {noise:.0f}"),
    ]
    go = all(c[1] for c in checks)
    lines += ["## Verdict", "", "| Check | Pass? | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {'✅' if ok_ else '❌'} | {det} |" for n, ok_, det in checks]
    oh = doc_stats.get("ohio_renewal", {}).get("reduced_mean")
    nc = doc_stats.get("nc_renewal", {}).get("reduced_mean")
    if oh is not None and nc is not None:
        lines.append(f"| Bonus: the clearer Ohio letter beats the North Carolina letter when skimmed | "
                     f"{'✅' if oh > nc else '❌'} | Ohio {oh:.0f} vs NC {nc:.0f} |")
    good = [s["reduced_mean"] for d, s in doc_stats.items() if facts[d]["design"] == "good" and s["reduced_mean"] is not None]
    risky = [s["reduced_mean"] for d, s in doc_stats.items() if facts[d]["design"] == "risky" and s["reduced_mean"] is not None]
    if good and risky:
        g, rk = statistics.mean(good), statistics.mean(risky)
        lines.append(f"| Bonus: well-designed letters beat risky ones when skimmed | {'✅' if g > rk else '❌'} | "
                     f"good {g:.0f} vs risky {rk:.0f} |")
    lines += ["", f"# {'🟢 GO — build Misread' if go else '🔴 NO-GO — see the failed checks above'}", ""]
    if args.mock:
        lines += ["> This was a **mock** run with a fake keyword model. It only proves the code works. "
                  "The verdict means nothing until you run it for real.", ""]
    if errors:
        lines += [f"⚠️ {len(errors)} readings failed and were left out. First error: `{errors[0].get('error')}`", ""]
    if not args.mock:
        lines += [f"API calls: {api.calls} · tokens in {api.tokens['in']:,} / out {api.tokens['out']:,}", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(
        {"checks": [{"check": n, "pass": ok_, "detail": det} for n, ok_, det in checks], "go": go, "docs": doc_stats},
        indent=2), encoding="utf-8")
    print("\n" + "\n".join(f"  {'PASS' if ok_ else 'FAIL'}  {n}  ({det})" for n, ok_, det in checks))
    print(f"\n  {'GO' if go else 'NO-GO'}{'  (mock run: means nothing yet)' if args.mock else ''}")
    if errors:
        print(f"  {len(errors)} readings failed; first error: {errors[0].get('error')}")
    print(f"\nFull results: {out / 'summary.md'}")


if __name__ == "__main__":
    main()
