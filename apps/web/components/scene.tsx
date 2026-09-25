import Image from "next/image";

type Variant = "flood" | "ndwi" | "sar" | "change" | "pair";

const SENTINEL_1 = "Copernicus Sentinel-1 (2020), processed by Pierre Markuse · CC BY 2.0";
const SENTINEL_2 = "Copernicus Sentinel-2 · ESA · CC BY-SA 3.0 IGO";

const IMAGES = {
  optical: {
    src: "/imagery/sundarbans.webp",
    alt: "Sentinel-2 optical image of the Sundarbans delta",
    label: "Optical · Sentinel-2",
  },
  before: {
    src: "/imagery/dhubri-2020-06-07.webp",
    alt: "Sentinel-1 radar of the Brahmaputra at Dhubri, 7 June 2020",
    label: "SAR · 7 Jun 2020",
  },
  after: {
    src: "/imagery/dhubri-2020-07-13.webp",
    alt: "Sentinel-1 radar of the Brahmaputra in flood at Dhubri, 13 July 2020",
    label: "SAR · 13 Jul 2020",
  },
} as const;

function Tile({
  image,
  sizes,
  showLabel,
}: {
  image: (typeof IMAGES)[keyof typeof IMAGES];
  sizes: string;
  showLabel: boolean;
}) {
  return (
    <div className="relative h-full w-full overflow-hidden">
      <Image src={image.src} alt={image.alt} fill sizes={sizes} className="object-cover" />
      {showLabel && (
        <span className="bg-ink/70 absolute bottom-2 left-2 px-1.5 py-0.5 text-[0.625rem] font-medium tracking-wide text-white uppercase">
          {image.label}
        </span>
      )}
    </div>
  );
}

/**
 * A real satellite scene, wherever the site shows what imagery looks like.
 * Optical is Sentinel-2 over the Sundarbans; SAR and change are Sentinel-1
 * over the 2020 Brahmaputra floods at Dhubri, Assam. Both open licences.
 *
 * `showFlood` is kept for callers written against the old drawn scenes: on
 * the SAR variant, false shows the pre-flood date instead of the flood.
 */
export function Scene({
  variant = "flood",
  className = "",
  showFlood = true,
  showLabel = true,
  sizes = "(min-width: 1024px) 33vw, 100vw",
}: {
  variant?: Variant;
  className?: string;
  showFlood?: boolean;
  showLabel?: boolean;
  sizes?: string;
}) {
  const credit = variant === "flood" || variant === "ndwi" ? SENTINEL_2 : SENTINEL_1;

  return (
    <div className={`relative h-full min-h-24 w-full ${className}`} title={credit}>
      {variant === "pair" ? (
        <div className="grid h-full grid-cols-2 gap-px bg-white">
          <Tile image={IMAGES.optical} sizes={sizes} showLabel={showLabel} />
          <Tile image={IMAGES.after} sizes={sizes} showLabel={showLabel} />
        </div>
      ) : variant === "change" ? (
        <div className="grid h-full grid-cols-2 gap-px bg-white">
          <Tile image={IMAGES.before} sizes={sizes} showLabel={showLabel} />
          <Tile image={IMAGES.after} sizes={sizes} showLabel={showLabel} />
        </div>
      ) : variant === "sar" ? (
        <Tile image={showFlood ? IMAGES.after : IMAGES.before} sizes={sizes} showLabel={showLabel} />
      ) : (
        <Tile image={IMAGES.optical} sizes={sizes} showLabel={showLabel} />
      )}
    </div>
  );
}
