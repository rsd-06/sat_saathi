# Hyperframes Composition Brief: SatSaathi

## Objective
A short, polished launch-style film for SatSaathi, for a LinkedIn post.

## Output
- Composition directory: `docs/brag-output/composition/`
- Rendered video: `docs/brag-output/brag.mp4`
- Format: landscape, 1920x1080
- Duration: 24 seconds

## Source Material
- Project root: the repository root
- Primary files read: `README.md`, `apps/web/app/globals.css` (tokens), `apps/web/components/hero-sheet.tsx`, `apps/web/components/trace.tsx`, `packages/i18n/messages/en.json`, `python/tools/tests/test_builtin.py` (the four-language questions), `TODO.md` (which steps are placeholders)
- Product name: SatSaathi
- Tagline: "Ask the satellite, in your language."
- Key UI moments recreated: the hero sheet, the Imagery panel, the eight-step trace, the Available-measurements refusal, the confidence-gate card
- Copy that must appear verbatim:
  - Ask the satellite, in your language.
  - How much of this area is under water? (and its Hindi, Tamil and Bangla forms)
  - What the system did / Every step, in order, with its parameters and what it produced.
  - Question received · Imagery registered · Question understood · Imagery prepared · Measurements computed · Imagery read · Claims checked · Answer written
  - NDVI needs nir, red. · NDWI needs green, nir. · LSWI needs nir, swir1.
  - Confidence fell below 75% · Sent for expert review

## Creative Direction
- Tone preset: polished
- Creative direction: quiet survey-sheet film; confidence through restraint
- Angle: the product is defined by what it refuses to do. Show the working flow, then the refusal.
- Hook: the delta image and the two-part headline
- Outro: SatSaathi, the tagline, the team line, then near-silence
- Avoid: generic SaaS language; abstract filler; anything the product does not do (voice, PDF report, translated answers, invented measurements)

## Visual Identity
- Background #f7f7f4 with a faint grid, raised #fdfdfb, ink #1c1f1d, muted #5c625e
- Accent #33367a; data colours water #2e5e8c, vegetation #4a7a3f, relief #8a6a3c, alert #a33526
- Display Noto Serif; body Noto Sans; Noto Sans Devanagari / Tamil / Bengali for the language scene (all vendored locally)

## Storyboard
See `brag-plan.md`.
1. The delta — 4.1s
2. Four languages — 5.7s
3. The trace — 6.0s
4. It would rather say no — 4.9s
5. Outro — 3.3s

## Audio
- Role: warm bed, sparse soft accents
- Music: `assets/music/bed.mp3` (vol-10, 110 BPM)
- Music treatment: fade in 0.8s, ~0.5 volume, fade out over the last 1.8s
- Music cue guidance: bundled preset. Strong cues locked at 4.10, 15.82, 20.74. Beat grid for reveals.
- Audio-reactive treatment: none. The extraction helper belongs to a Hyperframes domain skill that is not installed; skipped, not faked.
- Audio-coupled moments: language rows, trace rows, review card, logo
- SFX: low high-frequency-risk files only, copied into `assets/sfx/`
- Honest limits: no voiceover

## Hyperframes Instructions
Composition rules followed (from the scaffold's own `CLAUDE.md` and the CLI docs): one paused GSAP timeline registered on `window.__timelines`, timed `.clip` elements with `data-start`/`data-duration`, deterministic logic only, no network fetches (GSAP, fonts, image and audio are all local). Only the GSAP properties the runtime documents are animated: opacity, x, y, scale, scaleX, width, height, visibility. `npx hyperframes check` is the gate before render.
