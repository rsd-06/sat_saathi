# Launch film

A 24-second film for SatSaathi, made with [Hyperframes](https://hyperframes.heygen.com).

| File | |
|---|---|
| `brag.mp4` | The film, with the music bed |
| `brag-no-music.mp4` | The same film with only soft sound effects |
| `brag.jpg` | Poster frame (also baked in as frame 0) |
| `share-copy.txt` | Suggested post caption |
| `brag-plan.md`, `composition-brief.md` | The plan and the handoff brief |

Every product string on screen is verbatim from the app or its test suite, and nothing is shown that the product does not do.

## Credits

- Music: *Happy Beats / Business Moves, Vol. 10* by [ende.app](https://ende.app/en), CC BY 4.0
- Sound effects: [Kenney](https://kenney.nl/), CC0
- Imagery: contains modified Copernicus Sentinel data (ESA), CC BY-SA 3.0 IGO
- Fonts: Noto Serif and Noto Sans, SIL Open Font License

The composition source (`brag/composition/`) is not tracked because it copies several MB of fonts, audio and a vendored GSAP. Re-create it with `npx hyperframes init` and `brag-plan.md`.
