# TODO

## Answers

- [ ] **Replace `answer.template` with a real answer composer.** Today the final
  answer is the vision-language model's own text, passed through unchanged
  (`python/tools/src/satsaathi_tools/builtin.py`, `AnswerTemplate`). It is marked a
  stub because it only joins text; it does not write. A language-model step should
  turn the model's output, the question and any measurements into a full answer in
  the asker's language.
- [x] Stopgap (2026-09-25): the final answer is the model's text verbatim, with no
  added punctuation. Adding a full stop had turned a Hindi "।" into "।.".
- [ ] **Expand short answers.** Yes/no and counting questions come back as one
  word ("Yes.", "2."). Until the composer exists, pair the VQA answer with the
  caption so the officer gets a sentence.
- [ ] **Replace `intent.keyword`** with a trained intent classifier. It is also a
  stub: questions are routed by keyword lists.
- [ ] **Confidence is low across the board** (31–49% on test images), so most
  answers are held for review. Calibrate, or improve the adapters, before
  relying on the 75% release threshold.

## Web

- [ ] Translate the new workspace panels (change detection, cross-modal
  validation, image stack, profile) into Hindi, Tamil and Bangla; they are
  English-only.
- [ ] Change and cross-modal analyses are pixel heuristics in the browser, not
  models. Replace with model-backed tools when weights exist.
