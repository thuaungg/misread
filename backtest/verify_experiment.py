"""Experiment: does checking a "wrong" answer against the letter itself separate real misreads
from unfair flags? Compares two models against hand labels for 30 random flags + 4 known misreads.

    python backtest/verify_experiment.py
"""
import concurrent.futures as cf
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
import core  # noqa: E402
import fixer  # noqa: E402
import run_test as rt  # noqa: E402

# Hand labels for the 30 cards drawn with random.seed(11): G = genuinely wrong, U = unfair, D = debatable
HAND = "D U D D G U G U D U U G U U U U U D U U U U U G D D U G G D".split()

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


def verify(model, letter, slot, said, careful):
    user = (f"LETTER:\n<<<\n{letter}\n>>>\n\nQUESTION: {QUESTION[slot]}\nCAREFUL READER: {careful}\nREADER'S ANSWER: {said}\n\n"
            'TASK: judge the reader\'s answer against the letter. Reply with JSON only: '
            '{"verdict": "consistent" or "conflicts" or "off_point", "why": "one short sentence"}')
    for _ in range(2):
        out = rt.parse_json(core.API.chat(model, VERIFY_SYSTEM, user, 0.0, max_tokens=200))
        if out.get("verdict") in ("consistent", "conflicts", "off_point"):
            return out["verdict"]
    return "error"


def main():
    cards = []
    for f in sorted((HERE / "results").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        for c in (r.get("test") or {}).get("cards", []):
            cards.append((r["id"], c))
    random.seed(11)
    sample = random.sample(cards, 30)
    items = [(lid, c["slot"], c["said"], HAND[i], c["truth"]) for i, (lid, c) in enumerate(sample)]
    # known real misreads from the example letters (must stay "conflicts")
    known = json.loads((HERE / "regression_v3.json").read_text(encoding="utf-8"))
    for sid in ("cms_nomnc", "nc_renewal", "irs_cp05"):
        fact = json.loads((HERE.parent / "facts" / f"{sid}.json").read_text(encoding="utf-8"))
        for slot, view, said in known[sid]["cards"]:
            if slot in ("deadline", "contact", "consequence", "need_to_act"):
                items.append((sid, slot, said, "K", core._truth(slot, fact)))
    letters = {}
    for lid, *_ in items:
        p = HERE / "text" / f"{lid}.txt"
        src = p if p.exists() else HERE.parent / "letters" / f"{lid}.md"
        letters[lid] = fixer.reflow(src.read_text(encoding="utf-8"))

    rows = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {(i, m): ex.submit(verify, m, letters[lid], slot, said, careful)
                for i, (lid, slot, said, _, careful) in enumerate(items) for m in (rt.GRADER_MODEL, fixer.REWORD_MODEL)}
        for i, (lid, slot, said, hand, _) in enumerate(items):
            rows.append((lid, slot, hand, futs[(i, rt.GRADER_MODEL)].result(), futs[(i, fixer.REWORD_MODEL)].result(), said))
    for m_i, name in ((3, "Super"), (4, "Ultra")):
        keep_g = sum(r[m_i] == "conflicts" for r in rows if r[2] == "G")
        drop_u = sum(r[m_i] != "conflicts" for r in rows if r[2] == "U")
        keep_k = sum(r[m_i] == "conflicts" for r in rows if r[2] == "K")
        d_kept = sum(r[m_i] == "conflicts" for r in rows if r[2] == "D")
        print(f"{name}: keeps {keep_g}/{HAND.count('G')} genuine, drops {drop_u}/{HAND.count('U')} unfair, "
              f"keeps {d_kept}/{HAND.count('D')} debatable, keeps {keep_k}/{sum(r[2] == 'K' for r in rows)} known misreads")
    for r in rows:
        print(f"  {r[2]} super={r[3]:10} ultra={r[4]:10} {r[0][:24]:24} {r[1]:11} {r[5][:70]}")
    print(f"API calls {core.API.calls}, tokens in {core.API.tokens['in']:,}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
