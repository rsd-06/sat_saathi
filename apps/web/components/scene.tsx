/**
 * A drawn stand-in for satellite imagery. Real rasters arrive from the tiler
 * in a later phase; until then the interface still has to be judged against
 * something that behaves like a scene — water, fields, a channel, a flood
 * margin — rather than a grey rectangle.
 */

type Variant = "flood" | "ndwi" | "sar" | "change";

const FIELDS = [
  { x: 12, y: 96, w: 58, h: 34, t: 0.72 },
  { x: 74, y: 92, w: 42, h: 38, t: 0.51 },
  { x: 120, y: 98, w: 48, h: 30, t: 0.83 },
  { x: 16, y: 134, w: 44, h: 28, t: 0.42 },
  { x: 64, y: 136, w: 52, h: 26, t: 0.65 },
  { x: 122, y: 132, w: 40, h: 32, t: 0.29 },
  { x: 170, y: 104, w: 46, h: 36, t: 0.58 },
  { x: 176, y: 146, w: 38, h: 26, t: 0.37 },
  { x: 24, y: 168, w: 56, h: 24, t: 0.61 },
  { x: 88, y: 168, w: 44, h: 26, t: 0.24 },
];

const CHANNEL =
  "M -6 62 C 40 58, 62 74, 96 72 C 132 70, 152 52, 190 56 C 222 60, 240 50, 262 46";
const FLOOD =
  "M -6 44 C 30 40, 54 58, 92 56 C 126 54, 150 36, 188 40 C 220 44, 242 34, 262 30 L 262 96 C 236 92, 214 104, 186 100 C 148 94, 126 112, 92 110 C 56 108, 32 92, -6 96 Z";

function ramp(t: number, variant: Variant) {
  if (variant === "ndwi") {
    // Low (dry) through high (water): relief brown to toposheet blue.
    const mix = Math.round(t * 100);
    return `color-mix(in oklab, var(--color-water) ${mix}%, var(--color-relief))`;
  }
  if (variant === "sar") {
    const l = 18 + t * 52;
    return `hsl(140 6% ${l}%)`;
  }
  const mix = Math.round(t * 100);
  return `color-mix(in oklab, var(--color-vegetation) ${mix}%, var(--color-relief))`;
}

export function Scene({
  variant = "flood",
  className = "",
  showFlood = true,
}: {
  variant?: Variant;
  className?: string;
  showFlood?: boolean;
}) {
  const water =
    variant === "sar" ? "#0d1210" : "var(--color-water)";

  return (
    <svg
      viewBox="0 0 256 208"
      role="img"
      aria-label="Satellite scene: a river channel with flooded ground and field parcels"
      className={`block h-full w-full ${className}`}
      preserveAspectRatio="xMidYMid slice"
    >
      <rect
        width="256"
        height="208"
        fill={variant === "sar" ? "#141a17" : "var(--color-relief-wash)"}
      />

      {FIELDS.map((f, i) => (
        <rect
          key={i}
          x={f.x}
          y={f.y}
          width={f.w}
          height={f.h}
          fill={ramp(f.t, variant)}
          stroke={variant === "sar" ? "#1f2a24" : "var(--color-paper)"}
          strokeWidth="0.75"
          opacity={variant === "sar" ? 0.9 : 1}
        />
      ))}

      {showFlood && (
        <path
          d={FLOOD}
          fill={water}
          opacity={variant === "change" ? 0.32 : 0.55}
        />
      )}
      <path d={CHANNEL} fill="none" stroke={water} strokeWidth="7" />
      <path
        d={CHANNEL}
        fill="none"
        stroke={variant === "sar" ? "#2b3a33" : "var(--color-water)"}
        strokeWidth="2"
        opacity="0.8"
      />

      {variant === "change" && (
        <path
          d={FLOOD}
          fill="none"
          stroke="var(--color-alert)"
          strokeWidth="1.5"
          strokeDasharray="4 2.5"
        />
      )}
    </svg>
  );
}
