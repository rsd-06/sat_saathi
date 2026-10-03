# Brag Plan: SatSaathi

## What is this app?
A copilot that lets a district officer upload satellite imagery and ask a question in English, Hindi, Tamil or Bangla, and gets an answer measured from the pixels, with every step recorded. Its distinguishing claim is honesty: it refuses to guess.

## The angle
Every other AI demo is about what the model can say. This one is about what it **won't**. The video is a quiet product film built on the project's own rule: *compute, don't guess*. The hook is the delta image and the headline; the payoff is a system that says "NDVI needs nir, red" and "Sent for expert review" instead of inventing a number.

Honesty constraint on the video itself: nothing is shown that the product does not do. No voice, no PDF, no translated answers, no invented hectares or percentages. Every product string on screen is verbatim from the UI or the test suite; connective lines ("One question, asked four ways.", "It would rather say no than guess.") are framing and assert nothing new.

## Hook (first 2-3 seconds)
The Sundarbans delta from the real landing page, in its survey-sheet frame with the marginalia strip, and the headline settling in two halves: **"Ask the satellite,"** then **"in your language."**

## Key moments (the middle)
- The same question in four scripts: English, हिन्दी, தமிழ், বাংলা — the actual routing test inputs from the repo, arriving one row at a time.
- The working flow: a GeoTIFF is read (`sample-scene.tif`, 240 × 160 px, 4 bands, EPSG:32645) and the eight-step trace fills in row by row, with "Placeholder" honestly marked on the two steps that are placeholders today.
- The refusal: three struck-through indices with the exact bands they would have needed, then the confidence gate: "Confidence fell below 75%, / Sent for expert review."

## Outro / punchline
**SatSaathi** — "Ask the satellite, in your language." — Team MidDevz · Smart India Hackathon 2026 · SIH26167. Then the music falls away.

## User flow worth showing
Entry → key action → result: upload a GeoTIFF (read on the server) → the live eight-step trace → an answer that is either measured or held for a specialist.

## Tone
- Preset: polished
- Creative direction: quiet survey-sheet film; confidence through restraint
- Interpretation: slow reveals, mixed-case serif type, one idea per scene, 0.6s crossfades, silence at the end. The product's own paper-and-ink design language carries it.

## Format: landscape — 1920x1080
## Duration: 24s

## Visual identity (from the project: `apps/web/app/globals.css`)
- Background: #f7f7f4 (survey paper) with a faint 56px grid; raised #fdfdfb
- Accent: #33367a (indigo); data colours water #2e5e8c, vegetation #4a7a3f, relief #8a6a3c, alert #a33526
- Text: #1c1f1d ink, #5c625e muted
- Display font: Noto Serif Variable
- Body font: Noto Sans Variable (+ Devanagari, Tamil, Bengali)
- Strongest visual element: the toposheet-style frame — hairline rules, a marginalia strip along the top edge, registration marks at the corners

## Share copy (draft)
Introducing SatSaathi: ask the satellite, in your language. Answers are measured from the pixels, every step is recorded, and when it can't be sure it says so.

## Audio direction
- Role: warm bed with sparse, soft accents
- Music: `happy-beats-business-moves-vol-10` (110 BPM, beat every 0.55s)
- Music treatment: starts at 0, ~0.5 volume, fades in over 0.8s, fades out over the last 1.8s into near-silence for the outro
- Music cue guidance: bundled preset read. Strong cues locked: 4.10s (hook to languages), 15.82s (trace to refusal), 20.74s (logo lands). Beat grid used for one-by-one reveals, e.g. language rows every other beat (4.64, 5.74, 6.82, 7.79), trace rows every beat (10.38 → 14.20).
- Audio-reactive treatment: none. The extraction helper ships with a Hyperframes domain skill that is not installed here; skipped rather than faked.
- SFX posture: sparse, motion-matched, low high-frequency risk only
- Audio-coupled moments: language rows (soft click), trace rows (softer click), review card (single bong), logo (one bell)
- Restraint rule: no sound on text that is merely settling; nothing bright; the outro is nearly silent

## Storyboard

### Scene 1 — The delta — 4.1s
Delta image washes into the survey-sheet frame; marginalia strip (Scene · Platform · Bands · Rendering) draws across the top. Headline in two halves, held ≥2s together. Two real annotation tags (Mangrove forest, River channel) arrive on beats.
Sequential/interaction: headline halves at beats 0.82 and 1.90; tags at 2.46 and 3.01
Audio intent: calm, curious
Audio-coupled idea: one soft bong as the headline completes
Music: warm bed enters
Transition mood: slow crossfade (beat-locked 4.10s) → Scene 2

### Scene 2 — Four languages — 5.7s
"One question, asked four ways." Four rows, each a language label plus the question in its own script, revealing every other beat, all four held ≥2s.
Sequential/interaction: yes — rows at 4.64, 5.74, 6.82, 7.79
Audio intent: gentle accumulation
Audio-coupled idea: a soft tick as each row lands
Transition mood: crossfade → Scene 3

### Scene 3 — The trace — 6.0s
Left: the Imagery panel for `sample-scene.tif`. Right: "What the system did" and its subtitle; eight steps fill in one per beat, status dots turning green, "Placeholder" on the two steps that are placeholders today. Full list held ~1.6s.
Sequential/interaction: yes — eight rows at beats 10.38 → 14.20
Audio intent: steady, working
Audio-coupled idea: softer tick per row
Transition mood: crossfade (beat-locked 15.82s) → Scene 4

### Scene 4 — It would rather say no — 4.9s
Heading, then the "Available measurements" panel with NDVI / NDWI / LSWI struck through and the three reasons; then the confidence card: "Confidence fell below 75%," / "Sent for expert review."
Sequential/interaction: yes — reasons at 16.93, 17.47, 18.01; review card at 18.55 and 19.10
Audio intent: serious, a little weight
Audio-coupled idea: one bong as the review card lands
Transition mood: slow crossfade (beat-locked 20.74s) → Scene 5

### Scene 5 — Outro — 3.3s
SatSaathi at full scale, tagline, team line, imagery credit. Music fades to near-silence.
Sequential/interaction: none
Audio intent: resolve
Audio-coupled idea: one bell as the name lands
Transition mood: end

**Music mood for this video:** warm, restrained
**Audio summary:** a soft bed with quiet ticks that build with each list, one weighty note at the refusal, one bell on the name, then near-silence.
