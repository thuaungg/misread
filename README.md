# Misread

**Find out how busy people will misread your letter before you send it.**

Most people don't read a letter. They skim it, or see the first screen on a phone, or glance at it
on the way past. Misread shows your letter to AI readers the same way, checks what they understood
against what the letter really asks, and finds the smallest edit that stops the misreads.

**Live demo:** [starcrossed.cloud/misread](https://starcrossed.cloud/misread/)
· try the [Indonesian school-trip letter](https://starcrossed.cloud/misread/#/letter/id_talenta_livein_id),
where phone readers take the trip date for the payment deadline.

Built for the Nebius x NVIDIA Global AI Hackathon (Best Apps and Agents). Every model call is
NVIDIA Nemotron on [Nebius Token Factory](https://tokenfactory.nebius.com).

---

## What it does

1. **Upload or paste a letter**: PDF, Word (.docx) or text. The file is read in your browser;
   bold and large text are kept for the skim view.
2. **Check the answer key.** Nemotron writes down what the letter asks: what to do, the deadline,
   what happens if you don't, who to contact, and whether you need to act at all. You check it and
   fix anything it got wrong.
3. **Busy readers read it.** The letter is cut into four views of what a reader actually sees:

   | View | What the reader sees |
   | --- | --- |
   | Full read | the whole letter (the baseline) |
   | Skim | headings, bold text and the first line of each paragraph |
   | Glance | about 1 word in 5, top to bottom |
   | Phone | the first 110 words, one phone screen |

   Twelve readings (three per view) answer the same questions, and each answer is graded right,
   missing or **wrong**. A wrong answer is a misread: a confident mistake, like the wrong deadline
   or "nothing to do". Every "wrong" is checked again against the letter before it is shown.
4. **See what went wrong.** A score per view, each misread with why it happened and how to fix it,
   the sentences highlighted in the letter, and a checklist (phone screen, bold, repetition, length).
5. **Fix it** (optional). About a dozen small edits are tried: bold a sentence, make it a heading,
   move it to the top, add a "What you need to do" box built only from the letter's own sentences,
   and one rewording. Each is read again by busy readers. The best edit that beats the original is
   shown; if none does, Misread says so.
6. **Reader view**: a plain summary for the person receiving the letter, readable in 15 languages.

### Any language

The page follows the letter: paste a letter in any language and the whole page switches to that
language. Thirteen examples are built in, each a real public letter in a different language:
English, Indonesian, Russian, Chinese, Spanish, Burmese, Korean, Portuguese, French, Japanese,
Vietnamese, Malay and Hindi. Languages written without spaces are measured fairly (Chinese,
Japanese and Korean at 2 characters a word; Thai, Lao and Khmer at 6 letters; Burmese at about
2.5 syllables).

### The models

| Job | Model |
| --- | --- |
| Busy readers | `nvidia/Nemotron-3_5-Lightning` |
| Grading, finding sentences, detecting the language | `nvidia/nemotron-3-super-120b-a12b` |
| Answer key, coaching, rewording, translation | `nvidia/Nemotron-3-Ultra-550b-a55b` |

---

## Run it yourself

You need Python 3.11 or newer. There's nothing to install: the app uses only the standard library.

1. Get an API key at [tokenfactory.nebius.com](https://tokenfactory.nebius.com).
2. Copy `.env.example` to `.env` and paste your key after `NEBIUS_API_KEY=`.
   `.env` is ignored by git.
3. Start the app:

   ```bash
   python app/server.py
   ```

4. Open [http://localhost:8080](http://localhost:8080).

The key stays on the server; it is never sent to the browser.

| Option | What it does |
| --- | --- |
| `--offline` | saved results only; never calls the API |
| `--mock` | a fake model for trying every button at no cost; nothing is saved |
| `--port 8090` | use another port |
| `--public` | for a public server: never overwrites the saved examples |
| `--max-jobs 4` | how many runs are processed at once (default 2) |

The test and the fixer also run from the command line, without the app:

```bash
python run_test.py --docs cms_nomnc
python fixer.py --doc cms_nomnc
```

Their reports go in `results/`.

---

## Does it work? The backtest

Misread was tested on 100 real public letters: 50 from Singapore schools and agencies and 50 from
the US and UK. The links are in [`backtest/manifest.json`](backtest/manifest.json); the full results
are in [`backtest/summary.md`](backtest/summary.md).

In the latest run:

- On the 71 real letters (the rest are newsletters, forms and templates), 49 of 51 "wrong answer"
  cards held up when checked again against the letter (96%).
- In a hand review of 30 random flags from all 100 documents, 8 were genuine mistakes, 17
  debatable and 5 unfair (in an earlier run it was 7, 7 and 16).
  [`backtest/hand_review.md`](backtest/hand_review.md) explains how they were judged.

Scores move a little from run to run, because the readers are AI models.

---

## Privacy

Letters are never written to disk or to logs. The server forgets a finished run after 15 minutes.

---

## Known limits

- **The readers are models of busy reading, not real people.** They are also more careful than most
  people, so the results are a best case: if a model reader misses the deadline, real people will too.
- **Scanned PDFs** have no text to read; there is no OCR yet.
- **Tamil** isn't offered as a letter language: the reader model returns blank answers on Tamil
  letters, and many Tamil PDFs have broken fonts.
- **Burmese** letters read well, but Nemotron's written Burmese is weak; treat Burmese coaching and
  summaries with care. Most real Burmese PDFs use the old Zawgyi encoding, which shows a
  "Text may be garbled" warning.

---

## What's in this repo

| Path | What it is |
| --- | --- |
| `app/server.py` | web server (standard library only) |
| `app/core.py` | runs, the built-in examples, saved results |
| `app/coach.py` | tips, the checklist, page and Reader view translations |
| `app/static/` | the page: `index.html`, `app.js`, `app.css`, English page text `ui_en.json` |
| `app/cache/` | saved results for the examples, and machine page translations |
| `app/ui_reviewed/` | hand-checked page translations (these win over machine ones) |
| `app/DESIGN.md` | design rules and the research behind them |
| `run_test.py` | builds the views, runs the readers, grades the answers |
| `fixer.py` | finds the key sentences, tries edits, picks the best |
| `letters/`, `facts/` | the 13 example letters and their hand-checked answer keys |
| `sources.json` | where each example came from and what was changed |
| `backtest/` | the 100-letter backtest: scripts, extracted text, results |

The example letters are public documents from schools and government agencies. Some details were
replaced with sample values (names, phone numbers, a bank account, blank fields); each example's
page lists what was changed.

---

## License

[MIT](LICENSE). The example and backtest letters belong to their publishers and are included only
for testing.
