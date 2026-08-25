# Worksheet Remix (prototype)

A small local web app: paste in a worksheet, tell it a child's special interest
(a game, film, or show), and it rewrites the worksheet around that theme —
keeping the actual learning content (numbers, spelling words, comprehension
skill) exactly the same, just reskinned to be more motivating for a child with
SEN.

This is a working prototype for exploring the idea, not a hosted product yet.
It runs on your own machine and uses your own Anthropic API key.

## What it actually does right now

- You paste worksheet text (or upload a `.txt`/`.docx` file).
- You type a theme (e.g. "Minecraft") — a few example chips are provided.
- It calls Claude with a prompt engineered to (a) never change numbers,
  answers, spelling words, or the comprehension skill being tested, and
  (b) reskin the surface wording/context to the theme, in short, literal,
  SEN-friendly language.
- The result renders as a clean worksheet on the right, with an answer key,
  a note for the teacher/parent about what was changed, and a print/Save-as-PDF
  button.
- Three example worksheets are pre-loaded (no API key needed) so you can see
  the intended output quality immediately — click "View" under any example
  in the left panel.

## What it doesn't do yet (known gaps, worth knowing before showing others)

- **No PDF/image worksheet support.** Most real SEN worksheets are PDFs or
  scans. This prototype only reads plain text or `.docx`. Getting from a PDF
  worksheet to structured text (via OCR, or PDF layout parsing) is the
  biggest piece of work standing between this and something genuinely usable
  day-to-day — worth prioritizing next if the concept tests well.
- **No accounts, saving, or worksheet library.** Every session starts fresh.
- **No image/diagram handling.** Worksheets with pictures, number lines, or
  diagrams aren't preserved — only text-based worksheets work well.
- **No output as a downloadable PDF file** (the "print" button uses your
  browser's print-to-PDF, which works but isn't polished).
- **The API key is typed into this app's own Settings box** and sent to your
  local server, which calls Anthropic directly. That's fine for trying it out
  yourself, but a real multi-user product would need proper auth and a
  server-side key instead of asking each user for their own.

## Running it

You'll need Python 3.10+ and an Anthropic API key from console.anthropic.com.

```bash
cd senworksheets
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5050 in your browser, click **⚙ Settings**, paste
in your API key (stored only in your browser), and try it with the example
chips or your own worksheet text.

## Files

- `app.py` — Flask backend; the one real endpoint is `POST /api/rewrite`.
- `prompts.py` — the system prompt that does the actual "reskin, don't
  reinvent" logic. This is the part worth iterating on most.
- `templates/index.html`, `static/app.js`, `static/style.css` — the frontend.
- `static/examples.js` — the three hand-written example worksheets shown in
  the app without needing an API key.

## Suggested next steps, roughly in order of impact

1. Try it on a handful of real worksheets you actually use, across a few
   subjects, and see where the AI's reskinning holds up vs. gets weird.
2. If the quality feels right, tackle PDF/scanned-worksheet input (OCR) —
   that's the gap between "cool demo" and "something a teacher could use
   Monday morning."
3. Decide on a real hosting story (this would move to a small server with
   your own Anthropic key billed centrally, rather than asking each user for
   theirs) and basic accounts so people can save worksheets.
4. Get feedback from an actual SEN teacher or two on the output — the
   prompt's assumptions about what's "SEN-friendly" (short sentences, literal
   language, no idioms) are a reasonable starting point but should be
   checked against real practice.
