import Image from "next/image";

/**
 * The opening sheet: one real scene, read the way the product reads one.
 *
 * Sentinel-2 true colour over the Sundarbans, where the Ganges–Brahmaputra
 * meets the Bay of Bengal. Mangrove, farmland, river channels and a sediment
 * plume sit side by side, the everyday questions a district officer asks, so
 * the annotations name what an answer would be about.
 */
const CALLOUTS = [
  { x: 20, y: 30, label: "Mangrove forest", note: "Dense, dark canopy" },
  { x: 62, y: 20, label: "Farmland & aquaculture", note: "Field parcels and ponds" },
  { x: 47, y: 43, label: "River channel", note: "Distributary to the Bay" },
  { x: 40, y: 80, label: "Sediment plume", note: "Silt carried offshore" },
] as const;

export function HeroSheet() {
  return (
    <figure className="border-rule-strong bg-paper-raised relative border shadow-[0_30px_60px_-30px_rgb(0_0_0/0.35)]">
      <div className="border-rule divide-rule grid grid-cols-2 divide-x border-b sm:grid-cols-4">
        {[
          ["Scene", "Sundarbans delta"],
          ["Platform", "Sentinel-2 MSI"],
          ["Bands", "B04 · B03 · B02"],
          ["Rendering", "True colour"],
        ].map(([label, value]) => (
          <div key={label} className="px-3 py-2">
            <div className="text-ink-faint marginal">{label}</div>
            <div className="text-ink tabular mt-0.5 text-xs sm:text-sm">{value}</div>
          </div>
        ))}
      </div>

      <div className="group relative aspect-[16/9] overflow-hidden">
        <Image
          src="/imagery/hero-sundarbans.webp"
          alt="Sentinel-2 true-colour image of the Sundarbans: mangrove forest, farmland, river channels and a sediment plume in the Bay of Bengal"
          fill
          priority
          sizes="(min-width: 1024px) 55vw, 100vw"
          className="object-cover transition-transform duration-[2400ms] ease-out group-hover:scale-[1.04]"
        />
        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-transparent"
        />

        <ul className="pointer-events-none absolute inset-0 hidden sm:block">
          {CALLOUTS.map((c) => (
            <li
              key={c.label}
              className="absolute flex -translate-y-1/2 items-center gap-2"
              style={{ left: `${c.x}%`, top: `${c.y}%` }}
            >
              <span className="relative grid size-3 place-items-center">
                <span className="absolute size-3 animate-ping rounded-full bg-white/60" />
                <span className="size-2 rounded-full bg-white ring-2 ring-black/30" />
              </span>
              <span className="rounded-xs bg-black/60 px-2 py-1 leading-tight text-white backdrop-blur-sm">
                <span className="block text-xs font-medium">{c.label}</span>
                <span className="block text-[0.625rem] text-white/75">{c.note}</span>
              </span>
            </li>
          ))}
        </ul>

        <p className="absolute right-3 bottom-3 left-3 text-sm text-white drop-shadow sm:text-base">
          “How much of this delta is mangrove, and is it shrinking?”
        </p>
      </div>

      <figcaption className="border-rule marginal flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t px-3 py-2">
        <span>The Ganges–Brahmaputra delta at the Bay of Bengal, India and Bangladesh.</span>
        <span className="text-ink-faint">Contains modified Copernicus Sentinel data · ESA · CC BY-SA 3.0 IGO</span>
      </figcaption>
    </figure>
  );
}
