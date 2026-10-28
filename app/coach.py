"""Writer coaching: why busy readers got something wrong, how to rewrite it, and a short
checklist for the letter. Explanations are written in the letter's own language, with an
English copy when the letter isn't in English.
"""
import collections
import concurrent.futures as cf
import json
import pathlib
import re
import unicodedata

import fixer
import run_test as rt

PHONE_WORDS = 110  # the phone view: about the first screen
LONG_LETTER = 600  # words; past this, most of a letter goes unread

VIEW_SEES = {
    "skim": "only the headings, bold text and the first line of each paragraph",
    "glance20": "about one word in five: the top of the letter and the start of each paragraph",
    "phone": f"only the first screen on a phone, about the first {PHONE_WORDS} words",
}

COACH_SYSTEM = """You coach people who write official letters. A busy reader saw only part of a letter and got one thing wrong. Explain it so the writer can fix the letter.

Reply with JSON only:
{"why": "one short sentence: why this reader got it wrong, based on what they could and couldn't see",
 "fix": "one short sentence: the specific change to the letter that would prevent it (move, bold, add a heading, put the date first, remove a confusing line, ...)"}

Be concrete and refer to the actual sentence or date. Plain words, no jargon."""


def is_english(language):
    return not language or language.strip().lower() in ("english", "en")


def _first_words(s, n=8):
    return rt.join_words(rt.words(fixer.core(s))[:n]).lower()


def _visible(sentence, view_text):
    """Did this view show the start of the sentence?"""
    return bool(sentence) and _first_words(sentence) in fixer.plain(view_text).lower()


def _position(letter, sentence):
    """Word number where the sentence starts, or None."""
    i = letter.find(sentence)
    return None if i < 0 else len(rt.words(fixer.plain(letter[:i])))


def _stands_out(sentence):
    return rt.is_heading(sentence) or (sentence.startswith("**") and sentence.rstrip(" .").endswith("**"))


def _explain_one(api, card, letter, views, located, language):
    slot = card["slot"]
    sentence = located.get("action" if slot == "need_to_act" else slot) if located else None
    facts = [f"VIEW: the reader saw {VIEW_SEES.get(card['view'], 'part of the letter')}."]
    if sentence:
        pos = _position(letter, sentence)
        facts.append(f"THE SENTENCE WITH THE RIGHT ANSWER: \"{fixer.core(sentence)}\"")
        if pos is not None:
            facts.append(f"It starts at word {pos} of {len(rt.words(fixer.plain(letter)))}.")
        facts.append("It is bold or a heading." if _stands_out(sentence) else "It is plain text, not bold and not a heading.")
        facts.append("This reader's view showed it." if _visible(sentence, views[card["view"]]) else "This reader's view did not show it.")
    else:
        facts.append("The letter has no single clear sentence that states the right answer.")
    want = (f'Write "why" and "fix" in {language}, and also add "why_en" and "fix_en" in English.'
            if not is_english(language) else 'Write in English.')
    user = (f"WHAT THE READER SAW:\n<<<\n{views[card['view']][:2500]}\n>>>\n\n"
            f"QUESTION: {card['label']}\nTHEY SAID: {card['said']}\nACTUALLY: {card['truth']}\n\n"
            + "\n".join(facts) + f"\n\n{want} Reply with JSON only.")
    out = rt.parse_json(api.chat(fixer.REWORD_MODEL, COACH_SYSTEM, user, 0.2, max_tokens=500))
    tip = {"why": str(out.get("why") or "").strip(), "fix": str(out.get("fix") or "").strip()}
    if not is_english(language):
        tip["why_en"], tip["fix_en"] = str(out.get("why_en") or "").strip(), str(out.get("fix_en") or "").strip()
    return tip if tip["why"] or tip["fix"] else None


def explain_cards(api, cards, letter, views, located, language="English"):
    """Adds a "coach" tip to each wrong-answer card (in place). A failed call just leaves it out."""
    def go(card):
        try:
            return _explain_one(api, card, letter, views, located, language)
        except Exception:  # noqa: BLE001 - a missing tip shouldn't sink the test
            return None

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for card, tip in zip(cards, ex.map(go, cards)):
            if tip:
                card["coach"] = tip
    if is_english(language):
        return
    # the model sometimes answers one of them in English: make sure every tip is in the letter's language
    items = {f"c{i}_{k}": c["coach"][k] for i, c in enumerate(cards) if c.get("coach") for k in ("why", "fix") if c["coach"].get(k)}
    if items:
        got = _translate(api, items, language, max_tokens=2500)
        for i, c in enumerate(cards):
            for k in ("why", "fix"):
                if got.get(f"c{i}_{k}"):
                    c["coach"][k] = got[f"c{i}_{k}"]
    # and an English copy of each, for the English switch, where the model left one out
    missing = {f"c{i}_{k}": c["coach"][k] for i, c in enumerate(cards) if c.get("coach")
               for k in ("why", "fix") if c["coach"].get(k) and not c["coach"].get(k + "_en")}
    if missing:
        got = _translate(api, missing, "English", max_tokens=2500)
        for i, c in enumerate(cards):
            for k in ("why", "fix"):
                if got.get(f"c{i}_{k}"):
                    c["coach"][k + "_en"] = got[f"c{i}_{k}"]


def repetition(letter):
    """Share of the words that repeat a sentence already said earlier (0-1)."""
    seen, repeated, total = set(), 0, 0
    for s in fixer.sentences(letter):
        key = re.sub(r"\W+", " ", fixer.core(s).lower()).strip()
        n = fixer.word_count(s)
        total += n
        if key in seen:
            repeated += n
        seen.add(key)
    return repeated / total if total else 0.0


def checklist(letter, fact, located):
    """A short, rule-based checklist for the writer. Each item: ok (True/False), title, detail."""
    located = located or {}
    total = len(rt.words(fixer.plain(letter)))
    items = []
    for slot, name in (("action", "What to do"), ("deadline", "The deadline")):
        s = located.get(slot)
        if not s:
            continue
        pos = _position(letter, s)
        if pos is None:
            continue
        ok = pos < PHONE_WORDS
        items.append({"ok": ok, "key": f"ck_{slot}_{'ok' if ok else 'no'}", "detail_key": f"ck_phone_{'ok' if ok else 'no'}",
                      "vars": {"pos": pos, "total": total, "limit": PHONE_WORDS}, "title": f"{name} is on the first phone screen" if ok else f"{name} is below the first phone screen",
                      "detail": (f"It starts at word {pos}, so phone readers see it." if ok else
                                 f"It starts at word {pos} of {total}. On a phone people see about the first {PHONE_WORDS} words, "
                                 "so put it at the top.")})
    key = list(dict.fromkeys(v for v in located.values() if v))
    if key:
        bold = sum(_stands_out(s) for s in key)
        items.append({"ok": bold == len(key), "key": "ck_bold_ok" if bold == len(key) else "ck_bold_no", "detail_key": "ck_bold",
                      "vars": {"n": len(key) - bold, "total": len(key)},
                      "title": "Key sentences stand out" if bold == len(key) else f"{len(key) - bold} of {len(key)} key sentences are plain text",
                      "detail": "Skimmers read headings and bold text first. Make the sentences readers must act on bold, "
                                "or gather them in a short “What you need to do” box at the top."})
    rep = repetition(letter)
    items.append({"ok": rep < 0.1, "key": "ck_rep_ok" if rep < 0.1 else "ck_rep_no", "vars": {"pct": round(rep * 100)}, "title": "No repeated text" if rep < 0.1 else f"{round(rep * 100)}% of the text repeats itself",
                  "detail": ("Nothing is said twice." if rep < 0.1 else
                             "The same sentences appear more than once. Cut the repeats: readers skip what looks familiar, "
                             "and the important parts get buried.")})
    ok = total <= LONG_LETTER
    items.append({"ok": ok, "key": "ck_len", "detail_key": "ck_len_ok" if ok else "ck_len_no",
                  "vars": {"words": f"{total:,}", "limit": LONG_LETTER}, "title": f"Length: {total:,} words",
                  "detail": ("Short enough to be read." if ok else
                             f"Most people read only about a fifth of a long page. Aim for under {LONG_LETTER} words, "
                             "or put what the reader must do at the very top.")})
    return items


# The reader's view in two languages. Labels are the reader-view headings; the content is the
# answer key and the mistakes, so the busy reader can read everything in the language they choose.
READER_LABELS = {
    "in_short": "In short",
    "what_to_do": "What to do",
    "by_when": "By when",
    "if_you_dont": "If you don't",
    "who_to_contact": "Who to contact",
    "nothing_to_do": "Nothing you need to do right now.",
    "highlights": "The highlighted parts of the letter say this.",
    "mistakes_title": "Mistakes people make when they skim this",
    "skim_think": "If you only skim, you might think",
    "actually": "But actually",
}

TRANSLATE_SYSTEM = """You translate short texts for an app. You are always told the TARGET LANGUAGE: every text you return must be in that language.
A text that is already in the target language is returned unchanged. Translate faithfully and plainly.
Keep amounts, names, phone numbers, websites, form names and {placeholders} exactly as they are. Write dates the way the
target language writes them, with exactly the same day, month, year and time."""


LABEL_CACHE = pathlib.Path(__file__).resolve().parent / "cache" / "labels"


def _translate(api, items, language, max_tokens=4000):
    """{key: text} -> {key: text in language}; keys that come back empty are left out."""
    user = (f"TARGET LANGUAGE: {language}\n\n"
            f"TEXTS (JSON, key -> text):\n{json.dumps(items, ensure_ascii=False)}\n\n"
            f"Reply with JSON only: the same keys, each text in {language}. Texts already in {language} stay exactly as they are.")
    for _ in range(2):
        try:
            out = rt.parse_json(api.chat(fixer.REWORD_MODEL, TRANSLATE_SYSTEM, user, 0.0, max_tokens=max_tokens))
        except Exception:  # noqa: BLE001
            continue
        got = {k: str(out[k]).strip() for k in items if isinstance(out, dict) and out.get(k)}
        if got:
            return got
    return {}


def labels_for(api, language):
    """The reader-view labels in a language: translated once, then kept on disk and reused."""
    LABEL_CACHE.mkdir(parents=True, exist_ok=True)
    path = LABEL_CACHE / (re.sub(r"[^a-z0-9]+", "-", language.lower()).strip("-") + ".json")
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if set(saved) >= set(READER_LABELS):
                return saved
        except ValueError:
            pass
    got = _translate(api, READER_LABELS, language, max_tokens=800)
    if set(got) >= set(READER_LABELS):
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
        return got
    return {**READER_LABELS, **got}


def _reader_content(fact, cards):
    """The letter-specific texts of the reader's view: summary, the answers, and each misreading."""
    content = {}
    if fact.get("summary"):
        content["summary"] = str(fact["summary"])[:1000]
    for s in rt.SLOTS:
        v = str(fact["facts"].get(s, ""))
        if v and not v.lower().startswith("not stated"):
            content[f"fact_{s}"] = v[:1000]
    for i, c in enumerate(cards[:8]):
        content[f"card{i}_said"], content[f"card{i}_truth"] = str(c["said"])[:600], str(c["truth"])[:600]
    return content


# "Read it in my language": the languages a reader can pick (English names; the page shows each in itself).
# Singapore's languages first, then those of the largest migrant-worker communities.
READ_IN = ["English", "Chinese", "Malay", "Tamil", "Hindi", "Bengali", "Burmese", "Filipino", "Indonesian",
           "Vietnamese", "Thai", "Japanese", "Korean", "Russian", "Spanish"]


def read_in(api, fact, cards, language):
    """The reader's view of a letter in a language the reader picks: the page's own texts (cached
    per language) plus this letter's summary, answers and misreadings, translated."""
    content = _reader_content(fact, cards)
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        ui = ex.submit(ui_for, api, language)
        text = ex.submit(_translate, api, content, language) if content else None
        ui, got = ui.result(), (text.result() if text else {})
    return {"language": language, "ui": ui, "text": {k: got.get(k, v) for k, v in content.items()},
            "complete": len(got) >= len(content) * 0.8}


def reader_translations(api, fact, cards, language):
    """For a letter that isn't in English: the reader's view in English and in the letter's
    language, as {"en": {...}, "local": {...}, "en_ok": bool}. Labels come from a per-language
    cache, so they show in the letter's language even if translating this letter's text fails."""
    if is_english(language):
        return None
    content = _reader_content(fact, cards)
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        labels = ex.submit(labels_for, api, language)
        en = ex.submit(_translate, api, content, "English")
        local = ex.submit(_translate, api, content, language)
        labels, en, local = labels.result(), en.result(), local.result()
    # anything missing falls back to the original text, so a gap never shows as blank
    return {"local": {**labels, **{k: local.get(k, v) for k, v in content.items()}},
            "en": {**READER_LABELS, **{k: en.get(k, v) for k, v in content.items()}},
            "en_ok": bool(en) and len(en) >= len(content) * 0.8}


# ---------------------------------------------------------------- the letter page in any language

UI_EN = json.loads((pathlib.Path(__file__).resolve().parent / "static" / "ui_en.json").read_text(encoding="utf-8"))
UI_CACHE = pathlib.Path(__file__).resolve().parent / "cache" / "ui"
PLACEHOLDER = re.compile(r"\{\w+\}")


# Each language's name in itself, for the language switch. The model, asked to "translate" a
# language's name, often hands back the English name, so common ones are written here.
NATIVE_NAMES = {
    "chinese": "中文", "mandarin": "中文", "simplified chinese": "简体中文", "traditional chinese": "繁體中文",
    "malay": "Bahasa Melayu", "indonesian": "Bahasa Indonesia", "tamil": "தமிழ்", "hindi": "हिन्दी",
    "bengali": "বাংলা", "russian": "Русский", "ukrainian": "Українська", "japanese": "日本語", "korean": "한국어",
    "vietnamese": "Tiếng Việt", "thai": "ไทย", "burmese": "မြန်မာ", "myanmar": "မြန်မာ", "tagalog": "Filipino",
    "filipino": "Filipino", "arabic": "العربية", "hebrew": "עברית", "spanish": "Español", "french": "Français",
    "german": "Deutsch", "italian": "Italiano", "portuguese": "Português", "dutch": "Nederlands", "polish": "Polski",
    "greek": "Ελληνικά", "turkish": "Türkçe", "punjabi": "ਪੰਜਾਬੀ", "urdu": "اردو", "nepali": "नेपाली", "sinhala": "සිංහල",
}


def native_name(api, language):
    known = NATIVE_NAMES.get(language.strip().lower())
    if known:
        return known
    got = _translate(api, {"_native_name": language}, language, max_tokens=60)
    return got.get("_native_name") or language


def ui_for(api, language):
    """The letter page's texts (static/ui_en.json) in a language, plus "_native_name" (the
    language's own name). Translated once, kept on disk, reused. None for English."""
    if is_english(language):
        return None
    UI_CACHE.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", language.lower()).strip("-")
    path = UI_CACHE / (slug + ".json")
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if set(UI_EN) <= set(saved):
                return _with_reviewed(saved, slug, language)
        except ValueError:
            pass
    keys = list(UI_EN)
    chunks = [dict((k, UI_EN[k]) for k in keys[i:i + 45]) for i in range(0, len(keys), 45)]
    with cf.ThreadPoolExecutor(max_workers=len(chunks)) as ex:
        parts = list(ex.map(lambda c: _translate(api, c, language, max_tokens=4000), chunks))
    got = {}
    for part in parts:
        for k, v in part.items():
            # a translation that loses a {placeholder} would print wrong numbers: keep the English
            if set(PLACEHOLDER.findall(UI_EN[k])) <= set(PLACEHOLDER.findall(v)):
                got[k] = v
    # Lines the model skipped get one more try on their own.
    skipped = {k: UI_EN[k] for k in UI_EN if k not in got or (got[k] == UI_EN[k] and len(UI_EN[k]) > 12)}
    if skipped:  # in small groups: one bad reply then costs only a few lines
        keys = list(skipped)
        groups = [{k: skipped[k] for k in keys[i:i + 15]} for i in range(0, len(keys), 15)]
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for part in ex.map(lambda g: _translate(api, g, language, max_tokens=3000), groups):
                for k, v in part.items():
                    if v != UI_EN[k] and set(PLACEHOLDER.findall(UI_EN[k])) <= set(PLACEHOLDER.findall(v)):
                        got[k] = v
    # The model sometimes slips in words from another script (Telugu or Korean inside Tamil): retry
    # those once, and keep the English for any that still come back mixed.
    mixed = _mixed_script(got)
    if mixed:
        again = _translate(api, {k: UI_EN[k] for k in mixed}, language, max_tokens=2000)
        for k in mixed:
            got.pop(k)
            if again.get(k) and not _mixed_script({**got, k: again[k]}) and \
                    set(PLACEHOLDER.findall(UI_EN[k])) <= set(PLACEHOLDER.findall(again[k])):
                got[k] = again[k]
    native = native_name(api, language)
    table = {**UI_EN, **got, "_native_name": native}
    if len(got) >= len(UI_EN) * 0.9:  # only keep a near-complete table, so a bad run is retried next time
        path.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    return _with_reviewed(table, slug, language)


# Hand-checked translations (app/ui_reviewed/<language>.json) win over the machine's.
UI_REVIEWED = pathlib.Path(__file__).resolve().parent / "ui_reviewed"
JAPANESE = {"CJK", "HIRAGANA", "KATAKANA", "KATAKANA-HIRAGANA", "HALFWIDTH", "FULLWIDTH", "IDEOGRAPHIC"}


def _with_reviewed(table, slug, language):
    reviewed = {}
    p = UI_REVIEWED / (slug + ".json")
    if p.exists():
        try:
            reviewed = {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k in UI_EN}
        except ValueError:
            pass
    return {**table, **reviewed, "_native_name": NATIVE_NAMES.get(language.strip().lower(), table.get("_native_name"))}


def _script(ch):
    return unicodedata.name(ch, "?").split(" ")[0]


def _mixed_script(texts):
    """Keys whose text has letters from a script other than Latin and the table's main script."""
    counts = collections.Counter(_script(ch) for v in texts.values() for ch in v if ch.isalpha() and _script(ch) != "LATIN")
    if not counts:
        return []
    main = counts.most_common(1)[0][0]
    allowed = {"LATIN", main} | (JAPANESE if main in JAPANESE else set()) | ({"CJK"} if main == "HANGUL" else set())
    return [k for k, v in texts.items() if any(ch.isalpha() and _script(ch) not in allowed for ch in v)]


DETECT_SYSTEM = 'Name the language this text is written in, in English. Reply with JSON only: {"language": "..."}'


def detect_language(api, letter):
    try:
        out = rt.parse_json(api.chat(rt.GRADER_MODEL, DETECT_SYSTEM, letter[:1500], 0.0, max_tokens=30))
        return str(out.get("language") or "English").strip() or "English"
    except Exception:  # noqa: BLE001
        return "English"


def localize_fix(api, fix, language):
    """For a letter that isn't in English, add the recommended change in the letter's language."""
    if is_english(language):
        return
    # The quoted sentence is the letter's own words, already in its language: the translator, seeing
    # it, would take the whole line as translated. So it's swapped for {q} and put back afterwards.
    descs = {"change": fix["change"]["desc"], **{f"t{i}": t["desc"] for i, t in enumerate(fix["tried"])}}
    heading = fix.get("box_heading")  # the added box's name, already in the letter's language
    if heading:
        descs = {k: v.replace("“What you need to do”", f"“{heading}”") for k, v in descs.items()}
    quotes = {k: re.findall(r"“[^”]*”", v) for k, v in descs.items()}
    items = {k: re.sub(r"“[^”]*”", "{q}", v) for k, v in descs.items()}
    got = _translate(api, items, language, max_tokens=3000)

    def back(k):
        text = got.get(k)
        if not text or text.count("{q}") != len(quotes[k]):
            return None
        for q in quotes[k]:
            text = text.replace("{q}", q, 1)
        return text

    if back("change"):
        fix["change"]["desc_local"] = back("change")
    for i, t in enumerate(fix["tried"]):
        if back(f"t{i}"):
            t["desc_local"] = back(f"t{i}")
