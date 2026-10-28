# Misread — design rules

Bold, friendly, a bit loud — a tool a 17-year-old would screenshot, that a
judge understands in five seconds. Style: **neo-brutalism** (thick black
outlines, hard offset shadows, flat bright colour) with one yellow highlighter
accent, because the product is about what readers highlight and miss.

## References
- **Pinterest "aesthetic web UI" boards** — neo-brutalism, bento grids,
  retro OS windows, one neon accent on a calm background.
- **Gumroad, Figma community pages** — neo-brutalist buttons that press in.
- **Hemingway Editor / Grammarly** — the letter on one side, colour-coded
  highlights, a side panel of problems; clicking a problem jumps to it.
- **Nielsen Norman Group** — show progress for anything over ~10 seconds.

## Rules
1. **Upload first.** The hero is one line plus the drop zone. Three examples
   follow; the other ten sit behind "See all 13".
2. **Show, don't explain.** No sentences describing the tech on screen. Model
   names appear only as small labels (loading steps, "Powered by" tile). The
   explaining happens in the demo voice-over.
3. **Every letter shows its source** as chips: "IRS original ↗", "Sample values
   added" (opens what we filled in), and a warning chip for newsletters,
   templates and non-letters.
4. **Colour: 60 / 30 / 10.** 60% beige (the page, window bars, quiet tiles), 30% white
   paper (cards and the letter), 10% yellow (the main button, the highlighter, small
   accents). Red / amber / green mean wrong / missed / right and stay small: score
   numbers and borders, chips and highlights, never whole tiles.
5. **Buttons look pressable:** 2px black border, 4px hard shadow, lift on
   hover, press flat on click. One yellow primary button per screen.
6. **Motion has a job:** View Transitions between screens, tabs and versions;
   a highlighter sweep over the letter and a 12-cell reader grid while a run
   is going; numbers count up. All motion stops under reduced-motion.
7. **Type:** Bricolage Grotesque for UI and headings, IBM Plex Mono for small
   labels, Source Serif 4 only for the letter so it reads as a document.
8. **Plain words.** Sentence case, buttons start with a verb, errors say what
   to do next. Say in the demo and description that the readers are AI simulations.

## Tokens
| Token | Value | Use |
|---|---|---|
| `--bg` | #f6f1e7 | cream page with a dot grid |
| `--paper` | #ffffff | cards, the letter (the 30%) |
| `--beige-2` | #ece3d1 | window bars, quiet tiles (part of the 60%) |
| `--ink` | #121212 | text, borders, shadows |
| `--hl` | #ffe14d | highlighter, primary buttons (the 10%) |
| `--wrong` / bg / ink | #ff5a3c / #ffe1d9 / #b8270d | wrong answers |
| `--missing` / bg / ink | #f2a20c / #fff0c7 / #7d5200 | missed |
| `--found` / bg / ink | #19b36b / #d4f5e3 / #0b6e40 | right |
| `--sh` | 4px 4px 0 ink | hard shadow |

## Two views of the results
- **For the writer** (default): score, what readers got wrong with *why* and *fix* for each
  mistake, the fix, and a letter checklist (first phone screen, bold key sentences,
  repeated text, length).
- **For the reader**: "In short" (what to do, by when, if you don't, who to contact) and the
  letter with yellow "read this" highlights. `?mode=reader` opens it directly.
- Content follows the letter's language (answer key, readers, coaching, the fix); the
  interface stays English, with English under translated coaching.
