"""The Misread engine behind the web app: test a letter, fix a letter, and shape
the results for the screen. Reuses run_test.py (busy readers + grader) and
fixer.py (edit search) from the folder above."""
import collections
import concurrent.futures as cf
import json
import os
import pathlib
import re
import statistics
import sys
import threading
import time
import types
import urllib.parse
import uuid

APP = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(APP.parent))
import run_test as rt  # noqa: E402
import fixer  # noqa: E402
import coach  # noqa: E402
import web_help  # noqa: E402

CACHE = APP / "cache"
VIEW_ORDER = ["full", "skim", "glance20", "phone"]
BUSY = ["skim", "glance20", "phone"]
TEST_RUNS = 3
MAX_WORDS = 10000

rt.load_env(rt.ROOT / ".env")
MOCK = os.environ.get("MISREAD_MOCK") == "1"
API = rt.Api(os.environ.get("NEBIUS_API_KEY", ""), MOCK)
LIVE = bool(os.environ.get("NEBIUS_API_KEY")) or MOCK
ARGS = types.SimpleNamespace(
    reader_model=rt.READER_MODEL, grader_model=rt.GRADER_MODEL, temperature=0.6, think=False,
    workers=6, mock=MOCK, screen_runs=1, confirm_runs=2, top=2)
MODELS = {"reader": rt.READER_MODEL, "grader": rt.GRADER_MODEL, "locator": fixer.LOCATOR_MODEL,
          "rewrite": fixer.REWORD_MODEL, "extract": fixer.REWORD_MODEL}

CATEGORY = [("irs_", "IRS"), ("cms_", "Medicare"), ("va_", "Medicaid"), ("nc_", "Medicaid"),
            ("ohio_", "Medicaid"), ("indiana_", "Medicaid"), ("sg_", "School"), ("us_fcps", "School"),
            ("us_edd", "Unemployment"), ("uk_nhs", "Health"), ("us_nysed", "School"),
            ("us_irs", "IRS"), ("ca_", "School"), ("kr_", "School"), ("jp_kyoto_aid", "City"), ("jp_", "School"),
            ("id_", "School"), ("pt_", "School")]
SOURCES_FILE = rt.ROOT / "sources.json"


def sources():
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8")) if SOURCES_FILE.exists() else {}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")
SLOT_LABEL = {"need_to_act": "Need to act?", "action": "What to do", "deadline": "Deadline",
              "consequence": "If you don't", "contact": "Who to contact"}
CARD_PRIORITY = ["need_to_act", "deadline", "consequence", "action", "contact"]


# ------------------------------------------------------------------- jobs

class Job(fixer.Progress):
    """A test or fix running in the background; the screen polls it for progress."""

    def __init__(self, kind):
        self.id, self.kind = uuid.uuid4().hex[:12], kind
        self.status, self.label, self.done, self.total = "running", "Starting", 0, 0
        self.result, self.error, self.started, self.finished = None, None, time.time(), None
        self._lock = threading.Lock()

    def stage(self, label, readings):
        with self._lock:
            self.label = label
            self.total += readings

    def tick(self):
        with self._lock:
            self.done += 1

    def view(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "label": self.label,
                "done": self.done, "total": max(self.total, self.done), "result": self.result,
                "error": self.error, "seconds": round(time.time() - self.started)}


JOBS = {}
KEEP_FINISHED = 15 * 60  # seconds: the page fetches a result within moments; then the letter is forgotten


def forget_old_jobs():
    """Drop finished runs (and the letters in them) after 15 minutes, and stuck ones after an hour."""
    now = time.time()
    for jid, j in list(JOBS.items()):
        if (j.finished and now - j.finished > KEEP_FINISHED) or now - j.started > 3600:
            JOBS.pop(jid, None)


def _sweep():  # also on quiet days, when no new run would trigger the clean-up
    while True:
        time.sleep(300)
        forget_old_jobs()


threading.Thread(target=_sweep, daemon=True).start()


def running_jobs():
    return sum(j.status == "running" for j in JOBS.values())


def start(kind, fn, *args, cache_as=None):
    if MOCK:
        cache_as = None  # fake-model results must never replace real saved ones
    forget_old_jobs()
    job = Job(kind)
    JOBS[job.id] = job

    def go():
        try:
            job.result = fn(job, *args)
            if cache_as:
                save_cache(cache_as, kind, job.result)
            job.status = "done"
        except fixer.NoFix as e:
            job.error, job.status = str(e), "error"
        except Exception as e:  # surface the reason on screen instead of hanging
            job.error, job.status = f"{type(e).__name__}: {e}", "error"
        finally:
            job.finished = time.time()

    threading.Thread(target=go, daemon=True).start()
    return job


# ------------------------------------------------------------------ cache

def save_cache(sample_id, kind, data):
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{sample_id}.{kind}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_cache(sample_id, kind):
    p = CACHE / f"{sample_id}.{kind}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- samples

def sample_ids():
    return sorted(f.stem for f in (rt.ROOT / "letters").glob("*.md") if (rt.ROOT / "facts" / f"{f.stem}.json").exists())


def category(sample_id):
    return next((c for p, c in CATEGORY if sample_id.startswith(p)), "Letter")


def load_sample(sample_id):
    if sample_id not in sample_ids():
        return None
    text = (rt.ROOT / "letters" / f"{sample_id}.md").read_text(encoding="utf-8")
    fact = json.loads((rt.ROOT / "facts" / f"{sample_id}.json").read_text(encoding="utf-8"))
    src = sources().get(sample_id, {})
    # a letter in another language opens with its page in that language, like a pasted one
    # (the page texts are translated once and kept, so this costs nothing after the first time)
    local = not coach.is_english(fact.get("language"))
    return {"id": sample_id, "title": fact["title"] if local else src.get("name") or fact["title"],
            "category": category(sample_id), "source": src or None, "text": fixer.reflow(text), "fact": fact,
            "test": load_cache(sample_id, "test"), "fix": load_cache(sample_id, "fix"),
            "ui": coach.ui_for(API, fact["language"]) if local and not MOCK else None}


def read_in_sample(sample_id, language):
    """An example letter's reader view in another language. Examples are public, so this one is
    saved and reused; a visitor's own letter never is."""
    path = CACHE / f"{sample_id}.read.{re.sub(r'[^a-z]+', '-', language.lower())}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    s = load_sample(sample_id)
    out = coach.read_in(API, s["fact"], (s["test"] or {}).get("cards", []), language)
    if out["complete"] and out["ui"] and not MOCK:
        save_cache(sample_id, "read." + re.sub(r"[^a-z]+", "-", language.lower()), out)
    return out


def help_sample(sample_id):
    """An example letter's official-help links (web_help). Examples are public, so the search is
    saved and reused; a visitor's own letter is searched only when they ask, and never saved."""
    saved = load_cache(sample_id, "help")
    if saved is not None:
        return saved
    s = load_sample(sample_id)
    src = s["source"] or {}
    sender = {"sender": src.get("publisher", ""), "published_at": urllib.parse.urlsplit(src.get("url", "")).hostname or ""}
    out = web_help.official_help(API, s["fact"], sender) if not MOCK else None
    if out:
        save_cache(sample_id, "help", out)
    return out


def list_samples():
    out, srcs = [], sources()
    for sid in sample_ids():
        fact = json.loads((rt.ROOT / "facts" / f"{sid}.json").read_text(encoding="utf-8"))
        test = load_cache(sid, "test")
        src = srcs.get(sid, {})
        out.append({"id": sid, "title": src.get("name") or fact["title"], "summary": src.get("summary", ""),
                    "publisher": src.get("publisher", ""), "url": src.get("url", ""), "category": category(sid),
                    "busy": round(test["overall"]["busy"]) if test else None,
                    "wrong": sum(v == "wrong" for v in test["status"].values()) if test else None,
                    "ran_at": test.get("ran_at") if test else None,
                    "teaser": ({k: test["cards"][0][k] for k in ("label", "said", "truth")} if test and test["cards"] else None),
                    "short": src.get("publisher_short", ""),
                    "has_fix": (CACHE / f"{sid}.fix.json").exists()})
    return out


# ------------------------------------------------------------- the test

def phone_display(letter, words=110):
    """The phone view with its line breaks kept, for showing (the reader gets the same words)."""
    count = 0
    for m in re.finditer(r"\S+", letter):
        pieces = rt.words(m.group())  # Chinese, Japanese and Korean: one word per two characters
        if count + len(pieces) >= words:
            end = m.start() + len(rt.join_words(pieces[: words - count]))
            return letter[:end].rstrip() + ("\n\n…" if letter[end:].strip() else "")
        count += len(pieces)
    return letter


def display_views(letter):
    return {"full": letter, "skim": rt.view_skim(letter), "glance20": rt.view_glance(letter),
            "phone": phone_display(letter)}


def run_test_job(job, text, fact):
    letter = fixer.reflow(text)
    job.stage("Finding the sentences that matter", 0)
    try:
        located = fixer.locate(API, ARGS, letter, fact)
    except (ValueError, RuntimeError):
        located = None  # highlights are a nice-to-have; the readings still count
    views = {c: rt.VIEWS[c](letter) for c in VIEW_ORDER}
    job.stage("Reading it the way busy people do", len(VIEW_ORDER) * TEST_RUNS)
    results = []
    with cf.ThreadPoolExecutor(max_workers=ARGS.workers) as ex:
        futs = [ex.submit(rt.run_one, API, ARGS, "letter", fact, c, views[c], r) for c in VIEW_ORDER for r in range(TEST_RUNS)]
        for f in cf.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"error": str(e)})
            job.tick()
    job.stage("Checking wrong answers against the letter", 0)
    rt.double_check(API, ARGS, letter, fact, results)
    out = summarize_test(letter, fact, results, located)
    # When most careful readers come back with nothing at all, the readers couldn't make sense of the
    # letter (a language the reader model reads poorly, such as Tamil, or a broken layout): say so.
    full = [r for r in results if r.get("cond") == "full" and "reader" in r]
    blank = [r for r in full if not any(r["reader"].get(k) for k in rt.SLOTS)]
    out["readers_blank"] = len(full) > 0 and len(blank) * 3 >= len(full) * 2
    language = fact.get("language") or "English"
    if out["cards"]:
        job.stage("Explaining the mistakes for the writer", 0)
        coach.explain_cards(API, out["cards"], letter, views, located, language)
    out["checklist"] = coach.checklist(letter, fact, located)
    out["language"] = language
    if not coach.is_english(language):
        job.stage("Preparing the reader's view in two languages", 0)
        out["reader_i18n"] = coach.reader_translations(API, fact, out["cards"], language)
    # Nothing to misread: the reader isn't asked to do anything and the letter states no date,
    # warning or contact. A score of 100 would only mean "there was nothing to get wrong".
    out["testable"] = fact["action_required"] is True or any(s in out["slots"] for s in rt.SLOTS)
    out["ran_at"], out["live"] = now_iso(), True
    return out


def _said(slot, reader, fact):
    return rt.said_text(slot, reader)


def _truth(slot, fact):
    return rt.truth_text(slot, fact)


def summarize_test(letter, fact, results, located=None):
    ok = [r for r in results if "score" in r]
    if not ok:
        err = next((r.get("error") for r in results if r.get("error")), "no readings came back")
        raise RuntimeError(f"Every reading failed — {err}")
    conditional = fact["action_required"] == "conditional"
    slots = rt.scored_slots(fact)
    disp = display_views(letter)
    total_words = len(rt.words(letter))
    views, grid = {}, {s: {} for s in slots}
    for c in VIEW_ORDER:
        rs = sorted((r for r in ok if r["cond"] == c), key=lambda r: r["run"])
        shown = len(rt.words(rt.VIEWS[c](letter)))
        views[c] = {"text": disp[c], "score": statistics.mean(r["score"] for r in rs) if rs else None,
                    "n": len(rs), "misreads": sum(r["misread"] for r in rs),
                    "share": min(100, round(100 * shown / max(1, total_words)))}
        for s in slots:
            grid[s][c] = [r["labels"].get(s, "missing") for r in rs]
    busy = [r for r in ok if r["cond"] in BUSY]
    status = {}
    for s in [s for s in rt.SLOTS if s in slots]:
        # red if any busy reader got it wrong most of the time; amber if it was mostly missed
        wrong = any(grid[s][c].count("wrong") * 2 > len(grid[s][c]) for c in BUSY if grid[s][c])
        labs = [r["labels"].get(s) for r in busy]
        status[s] = "wrong" if wrong else "missing" if labs.count("found") * 2 < len(labs) else "found"
    tally = collections.Counter()
    example = {}
    for r in busy:
        for s, v in r["labels"].items():
            if v == "wrong":
                tally[(r["cond"], s)] += 1
                example.setdefault((r["cond"], s), r)
    cards, used = [], set()
    # Mistakes most readers in a view made come first; one reader in three can be noise.
    def order(kv):
        (c, s), n = kv
        return (n * 2 <= views[c]["n"], CARD_PRIORITY.index(s), -n)

    for (c, s), n in sorted(tally.items(), key=order):
        if s in used or len(cards) >= 3:
            continue
        used.add(s)
        r = example[(c, s)]
        cards.append({"view": c, "slot": s, "label": SLOT_LABEL[s], "said": _said(s, r["reader"], fact),
                      "truth": _truth(s, fact), "count": n, "of": views[c]["n"], "note": r.get("note", "")})
    busy_scores = [views[c]["score"] for c in BUSY if views[c]["score"] is not None]
    return {"letter": letter, "views": views, "slots": slots, "slot_labels": SLOT_LABEL, "grid": grid,
            "located": located, "status": status, "cards": cards, "conditional": conditional,
            "overall": {"busy": statistics.mean(busy_scores) if busy_scores else 0,
                        "careful": views["full"]["score"] or 0,
                        "misread_rate": sum(r["misread"] for r in busy) / max(1, len(busy))},
            "models": MODELS, "runs": TEST_RUNS}


# -------------------------------------------------------------- the fix

def run_fix_job(job, text, fact):
    r = fixer.compute_fix(API, ARGS, "letter", text, fact, log=lambda *a: None, progress=job)
    out = summarize_fix(r)
    coach.localize_fix(API, out, fact.get("language") or "English")
    out["ran_at"], out["live"] = now_iso(), True
    return out


def _brief(res):
    return {"score": res["score"], "by_view": res.get("by_view", {}), "misread_rate": res["misread_rate"]}


def summarize_fix(r):
    pick = r["pick"]
    tried = []
    for c in r["ranked"]:
        conf = c.get("confirm")
        tried.append({"desc": c["desc"], "kind": c["kind"], "cost": c["cost"], "keeps_wording": c["keeps_wording"],
                      "screen": c["screen"]["score"], "screen_mis": c["screen"]["misread_rate"],
                      "confirm": conf["score"] if conf else None, "confirm_mis": conf["misread_rate"] if conf else None})
    return {"before": _brief(r["base"]), "after": _brief(pick["confirm"]),
            "change": {"desc": pick["desc"], "kind": pick["kind"], "keeps_wording": pick["keeps_wording"]},
            "warnings": [{"sentence": s, "word": w} for s, w in r["refs"]],
            "original_text": r["letter"], "fixed_text": pick["text"], "fixed_views": display_views(pick["text"]),
            "located": r["located"], "tried": tried, "box_heading": r.get("box_heading") or fixer.BOX_HEADING}


# ---------------------------------------------------------- answer keys

KIND_RULES = """"kind" says what sort of document this is:
- "letter": a letter or notice to one reader or group about one main matter (a bill, a decision, a recall, a request, a reminder).
- "newsletter": an update covering many unrelated topics, such as a school's termly letter, where no single request stands out.
- "template": a blank form or template with fields still to fill in, such as [date], [name] or ______.
- "not_a_letter": a guide, handbook, slide deck, report, legal decision or technical bulletin, not written to tell a reader what to do."""

EXTRACT_SYSTEM = """You read an official letter carefully, every word, and write down what the person who receives it must know.

Use only what the letter says, and be specific: exact dates, amounts, phone numbers and names. If the letter doesn't say something, write "Not stated in the letter."

Keep each answer short enough to read at a glance: one or two sentences, at most about 35 words. Give the main point, not every detail. For "contact", give the one main contact the letter tells the reader to use (to ask questions, reply, pay or appeal): an office or person, plus one phone number or email, not a list of every address, website and shop. If a contact only appears in the letterhead or footer and the letter never asks the reader to get in touch, write "Not stated in the letter."

Likewise, only give a "deadline" or "consequence" the letter actually states for the reader; event dates and general information are not deadlines.

"action_required" is "yes" if the reader must do something, "no" if the letter only informs, or "only if" if they only need to act in some cases (for example, only if they disagree) or are invited to do something optional (nominate, sign up, apply if interested). Encouragement such as "we encourage you to" or "please remind your child" is not a requirement.

If the letter gives more than one valid answer to a question (two dates, two warnings, two phone numbers), list them, at most three, the most important first. If the letter covers several topics, like a school newsletter, do the same: at most three items in each answer, what the reader must do first. Leave out general news and optional extras.

Write the title, summary and every answer in the same language as the letter. The one exception: when the letter doesn't say something, write exactly "Not stated in the letter." in English.

Reply with JSON only:
{"title": "a short title for the letter",
 "language": "the letter's language, named in English (for example English, Russian, Malay, Chinese)",
 "summary": "one plain sentence: what this letter is about and what it means for the reader",
 "box_heading": "the phrase 'What you need to do' in the letter's language",
 "action_required": "yes" or "no" or "only if",
 "action": "what the reader has to do",
 "deadline": "by when",
 "consequence": "what happens if they don't, or the main warning",
 "contact": "who to contact and how"}"""


KINDS = ("letter", "newsletter", "template", "not_a_letter")


def classify_kind(letter):
    """(kind, name): letter / newsletter / template / not_a_letter, and what the document is in a
    few words of its own language ("news article"), for the page's "not a letter" warning. Its own
    call: asked alongside the answer key, the model calls almost everything a letter."""
    user = (f"DOCUMENT:\n<<<\n{letter[:60000]}\n>>>\n\n{KIND_RULES}\n\n"
            '"name" says what the document is in 1 to 5 words, in the document\'s own language, lower case, '
            'with an article if the language uses one (for example: a news article, a school newsletter, a slide deck, an invoice).\n\n'
            'Reply with JSON only: {"kind": "letter" or "newsletter" or "template" or "not_a_letter", "name": "..."}')
    try:
        out = rt.parse_json(API.chat(fixer.REWORD_MODEL, "You classify documents.", user, 0.0, max_tokens=100))
    except (ValueError, RuntimeError):
        out = {}
    kind, name = str(out.get("kind", "")), " ".join(str(out.get("name") or "").split()).strip(" .\"'")
    return (kind if kind in KINDS else "letter"), name[:40]


def _flat(v):
    """An answer as plain text, even if the model sent a list or an object."""
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_flat(x)}" for k, x in v.items())
    if isinstance(v, list):
        return "; ".join(_flat(x) for x in v)
    return str(v)


def extract_facts(text):
    letter = fixer.reflow(text)
    if MOCK:
        return {"title": "Your letter", "design": "unknown", "kind": "letter", "action_required": True,
                "facts": {s: "Mock answer for " + s for s in rt.SLOTS}}
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        kind = ex.submit(classify_kind, letter)
        out = _answer_key(letter)
        kind, kind_name = kind.result()
    req = str(out.get("action_required", "yes")).lower()
    language = str(out.get("language") or "English").strip() or "English"
    if not coach.is_english(language):
        # Asked for answers in the letter's language, the model still often writes Malay or Tamil
        # letters' answers in English: translate them (text already in the language comes back as is).
        items = {k: _flat(out[k]) for k in ("title", "summary", *rt.SLOTS) if out.get(k) and not rt.NOT_STATED.search(_flat(out[k]))}
        out.update(coach._translate(API, items, language, max_tokens=2000) if items else {})
    return {"title": out.get("title") or "Your letter", "design": "unknown", "kind": kind,
            "kind_name": kind_name if kind != "letter" else "", "language": language, "summary": _flat(out.get("summary") or ""),
            "box_heading": _flat(out.get("box_heading") or fixer.BOX_HEADING).strip(" #*\n") or fixer.BOX_HEADING,
            "action_required": True if req.startswith("y") else False if req.startswith("n") else "conditional",
            "facts": {s: _flat(out.get(s) or "Not stated in the letter.") for s in rt.SLOTS}}


def extract_with_ui(text):
    """The answer key, plus the letter page's texts in the letter's language (None for English).
    The page texts are looked up or translated while the answer key is being written."""
    letter = fixer.reflow(text)
    if MOCK:
        return extract_facts(text), None
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        early = ex.submit(lambda: coach.ui_for(API, coach.detect_language(API, letter)))
        fact = extract_facts(text)
        ui = early.result()
    if ui is None and not coach.is_english(fact["language"]):  # the quick guess said English; trust the key
        ui = coach.ui_for(API, fact["language"])
    elif ui is not None and coach.is_english(fact["language"]):
        ui = None
    return fact, ui


def _answer_key(letter):
    # The task is repeated after the letter: on long letters the model loses the system prompt
    # and starts turning the letter itself into JSON.
    user = ("LETTER:\n<<<\n" + letter + "\n>>>\n\nTASK: write the answer key for this letter as described. Reply with JSON only, "
            "with exactly these keys: title, language, summary, box_heading, action_required, action, deadline, consequence, contact.")
    for _ in range(2):
        try:
            out = rt.parse_json(API.chat(fixer.REWORD_MODEL, EXTRACT_SYSTEM, user, 0.0, max_tokens=1600))
        except ValueError:
            out = {}
        if "action" in out and "deadline" in out:
            return out
        user += "\n\nOnly the answer-key JSON object with those nine keys, nothing else."
    raise ValueError("Couldn't write an answer key for this document. Try again, or paste just the letter's main pages.")


def check_fact(fact):
    if not isinstance(fact, dict) or not isinstance(fact.get("facts"), dict):
        raise ValueError("missing answer key")
    for s in rt.SLOTS:
        if not str(fact["facts"].get(s, "")).strip():
            raise ValueError(f"the answer key needs '{SLOT_LABEL[s]}'")
    if fact.get("action_required") not in (True, False, "conditional"):
        raise ValueError("action_required must be true, false or 'conditional'")
    fact.setdefault("title", "Your letter")
    fact.setdefault("design", "unknown")
    return fact


def locate_sample(sample_id):
    """Find the must-know sentences for a cached sample result that doesn't have them yet."""
    s = load_sample(sample_id)
    if not s or not s["test"]:
        return None
    located = fixer.locate(API, ARGS, s["text"], s["fact"])
    if not MOCK:
        s["test"]["located"] = located
        save_cache(sample_id, "test", s["test"])
    return located
