"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";

/**
 * Multi-temporal change and cross-modal validation, computed in the browser.
 *
 * There are no trained weights behind these yet, so nothing here pretends to
 * be a model: every number is a pixel statistic over the images as given, and
 * the panel says so. The rules are simple and stated next to each result, so
 * they can be swapped for model output later without changing the interface.
 */

export type FrameKind = "optical" | "ndvi" | "ndwi" | "sar";
export type Frame = {
  id: string;
  name: string;
  url: string;
  kind: FrameKind;
  date: string;
  img: HTMLImageElement;
  primary?: boolean;
};
export type Mode = "auto" | "single" | "change" | "crossmodal";
export type ChangeChoice = "auto" | "bi" | "multi";
export type FeatureKey =
  | "changeMap"
  | "stats"
  | "timeline"
  | "persistence"
  | "layers"
  | "agreement"
  | "notes";
export type Features = Record<FeatureKey, boolean>;

export const ALL_FEATURES: Features = {
  changeMap: true,
  stats: true,
  timeline: true,
  persistence: true,
  layers: true,
  agreement: true,
  notes: true,
};

const FEATURE_LABEL: Record<FeatureKey, string> = {
  changeMap: "Change map",
  stats: "Area statistics",
  timeline: "Timeline",
  persistence: "Persistence heat",
  layers: "Source layers",
  agreement: "Agreement map",
  notes: "Complementary notes",
};

const KIND_LABEL: Record<FrameKind, string> = {
  optical: "Optical (RGB)",
  ndvi: "NDVI",
  ndwi: "NDWI",
  sar: "SAR",
};

const MODE_LABEL: Record<Mode, string> = {
  auto: "Auto",
  single: "Single-image Q&A",
  change: "Multi-temporal change",
  crossmodal: "Cross-modal validation",
};

// ----------------------------------------------------------------- report --

/** What a finished analysis hands back, to be kept in the account's history. */
export type Report = {
  kind: "change" | "crossmodal";
  variant: "bi" | "multi" | null;
  title: string;
  summary: string;
  stats: Record<string, unknown>;
  frames: { name: string; kind: string; date: string }[];
};

const ReportContext = createContext<(r: Report) => void>(() => undefined);

const round = (x: number) => Math.round(x * 10) / 10;
const meta = (f: Frame) => ({ name: f.name, kind: f.kind, date: f.date });

/** Reports once per distinct result, not once per render. */
function useReport(report: Report) {
  const send = useContext(ReportContext);
  const key = JSON.stringify(report);
  useEffect(() => {
    send(JSON.parse(key) as Report);
  }, [key, send]);
}

// ---------------------------------------------------------------- loading --

export async function loadFrame(file: File): Promise<Frame> {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.src = url;
  await img.decode();
  return {
    id: crypto.randomUUID(),
    name: file.name,
    url,
    img,
    kind: guessKind(img),
    date: dateFromName(file.name) ?? new Date(file.lastModified).toISOString().slice(0, 10),
  };
}

function dateFromName(name: string): string | null {
  const m = name.match(/(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])/);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
}

/** Grey images are most likely SAR; colour ones optical. The user can correct it. */
function guessKind(img: HTMLImageElement): FrameKind {
  const { d } = pixels(img, 64, 64);
  let spread = 0;
  for (let i = 0; i < d.length; i += 4) {
    spread += Math.abs(d[i]! - d[i + 1]!) + Math.abs(d[i + 1]! - d[i + 2]!);
  }
  return spread / (d.length / 4) < 12 ? "sar" : "optical";
}

// ------------------------------------------------------------- resolution --

export function resolveMode(mode: Mode, frames: Frame[], choice: ChangeChoice) {
  const sar = frames.filter((f) => f.kind === "sar").length;
  const other = frames.length - sar;
  let resolved: Exclude<Mode, "auto">;
  let why: string;
  if (mode !== "auto") {
    resolved = mode;
    why = "Chosen manually.";
  } else if (frames.length < 2) {
    resolved = "single";
    why = "One image, so Auto picked question answering. Add more images to compare them.";
  } else if (sar > 0 && other > 0) {
    resolved = "crossmodal";
    why = `${other} optical/index image(s) and ${sar} SAR image(s), so Auto picked cross-modal validation.`;
  } else {
    resolved = "change";
    why = `${frames.length} images of the same kind, so Auto picked change over time.`;
  }
  const changeKind: "bi" | "multi" =
    choice === "auto" ? (frames.length > 2 ? "multi" : "bi") : choice;
  return { mode: resolved, changeKind, why };
}

// ----------------------------------------------------------------- pixels --

type Px = { w: number; h: number; d: Uint8ClampedArray };

function pixels(img: HTMLImageElement, w: number, h: number): Px {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const x = c.getContext("2d", { willReadFrequently: true })!;
  x.drawImage(img, 0, 0, w, h);
  return { w, h, d: x.getImageData(0, 0, w, h).data };
}

/** One grid for every frame: the first frame's aspect, at most 360 px. */
function gridOf(img: HTMLImageElement): [number, number] {
  const s = Math.min(1, 360 / Math.max(img.naturalWidth, img.naturalHeight));
  return [
    Math.max(1, Math.round(img.naturalWidth * s)),
    Math.max(1, Math.round(img.naturalHeight * s)),
  ];
}

const lum = (d: Uint8ClampedArray, i: number) =>
  0.299 * d[i]! + 0.587 * d[i + 1]! + 0.114 * d[i + 2]!;
const exg = (d: Uint8ClampedArray, i: number) =>
  (2 * d[i + 1]! - d[i]! - d[i + 2]!) / 255;
const sat = (d: Uint8ClampedArray, i: number) => {
  const mx = Math.max(d[i]!, d[i + 1]!, d[i + 2]!);
  const mn = Math.min(d[i]!, d[i + 1]!, d[i + 2]!);
  return mx === 0 ? 0 : (mx - mn) / mx;
};

type Cat = { label: string; color: [number, number, number]; rule: string };

function overlay(base: Px, cat: Uint8Array, cats: Cat[]): ImageData {
  const out = new ImageData(base.w, base.h);
  for (let p = 0, i = 0; p < cat.length; p++, i += 4) {
    const c = cat[p]!;
    if (c > 0) {
      const [r, g, b] = cats[c - 1]!.color;
      out.data[i] = r;
      out.data[i + 1] = g;
      out.data[i + 2] = b;
    } else {
      const v = 70 + lum(base.d, i) * 0.55;
      out.data[i] = out.data[i + 1] = out.data[i + 2] = v;
    }
    out.data[i + 3] = 255;
  }
  return out;
}

// ---------------------------------------------------------------- change --

const CHANGE: Cat[] = [
  { label: "Vegetation gain", color: [46, 160, 67], rule: "greenness (2G−R−B) or NDVI rose" },
  { label: "Vegetation loss", color: [217, 119, 6], rule: "greenness (2G−R−B) or NDVI fell" },
  { label: "Water gain / darkening", color: [37, 99, 235], rule: "brightness or SAR backscatter dropped, or NDWI rose" },
  { label: "Brightening / bare or built-up", color: [219, 39, 119], rule: "brightness or SAR backscatter rose" },
  { label: "Other change", color: [202, 138, 4], rule: "changed, with no dominant direction" },
];

type ChangeResult = { cat: Uint8Array; pct: number; byCat: number[]; threshold: number };

function detectChange(a: Px, b: Px, kind: FrameKind): ChangeResult {
  const n = a.w * a.h;
  const diff = new Float32Array(n);
  let sum = 0;
  let sq = 0;
  for (let p = 0, i = 0; p < n; p++, i += 4) {
    const v =
      Math.hypot(b.d[i]! - a.d[i]!, b.d[i + 1]! - a.d[i + 1]!, b.d[i + 2]! - a.d[i + 2]!) / 441.7;
    diff[p] = v;
    sum += v;
    sq += v * v;
  }
  const mean = sum / n;
  const sd = Math.sqrt(Math.max(0, sq / n - mean * mean));
  // Adaptive: what stands out from this pair's own noise, never below 10 %.
  const threshold = Math.max(0.1, mean + 1.5 * sd);
  const cat = new Uint8Array(n);
  const counts = [0, 0, 0, 0, 0];
  for (let p = 0, i = 0; p < n; p++, i += 4) {
    if (diff[p]! < threshold) continue;
    const dl = lum(b.d, i) - lum(a.d, i);
    let c: number;
    if (kind === "sar") c = dl < 0 ? 3 : 4;
    else if (kind === "ndvi") c = dl > 0 ? 1 : 2;
    else if (kind === "ndwi") c = dl > 0 ? 3 : 5;
    else {
      const de = exg(b.d, i) - exg(a.d, i);
      c = de > 0.08 ? 1 : de < -0.08 ? 2 : dl < -25 ? 3 : dl > 25 ? 4 : 5;
    }
    cat[p] = c;
    counts[c - 1]!++;
  }
  const changed = counts.reduce((s, x) => s + x, 0);
  return { cat, pct: (changed / n) * 100, byCat: counts.map((x) => (x / n) * 100), threshold };
}

// ------------------------------------------------------------ cross-modal --

const CROSS: Cat[] = [
  { label: "Water confirmed by both", color: [37, 99, 235], rule: "optical/index water and low SAR backscatter" },
  { label: "Water under cloud (SAR only)", color: [6, 182, 212], rule: "optical sees cloud, SAR sees water" },
  { label: "Dark in SAR only", color: [147, 197, 253], rule: "low backscatter, optical disagrees: wet soil, tarmac or flooded vegetation?" },
  { label: "Water in optical only", color: [147, 51, 234], rule: "optical water, SAR disagrees: shadow or dark soil?" },
  { label: "Vegetation confirmed", color: [46, 160, 67], rule: "optical/index vegetation and moderate SAR volume scattering" },
  { label: "Structures (strong SAR return)", color: [220, 38, 38], rule: "very bright SAR: buildings, double bounce" },
  { label: "Cloud gap filled by SAR", color: [156, 163, 175], rule: "optical is cloud-covered; SAR is the only view" },
];

function crossModal(o: Px, oKind: FrameKind, s: Px) {
  const n = o.w * o.h;
  let sMean = 0;
  for (let i = 0; i < s.d.length; i += 4) sMean += lum(s.d, i);
  sMean /= n;
  const waterT = Math.min(70, sMean * 0.6);
  const strongT = Math.max(190, sMean * 1.7);
  const cat = new Uint8Array(n);
  const counts = new Array(CROSS.length).fill(0) as number[];
  let oWater = 0, sWater = 0, oVeg = 0, cloud = 0, both = 0, union = 0, strong = 0;

  for (let p = 0, i = 0; p < n; p++, i += 4) {
    const v = lum(o.d, i) / 255;
    let ow = false, ov = false, oc = false;
    if (oKind === "ndvi") {
      const ndvi = 2 * v - 1;
      ov = ndvi > 0.3;
      ow = ndvi < -0.05;
    } else if (oKind === "ndwi") {
      const ndwi = 2 * v - 1;
      ow = ndwi > 0.1;
      ov = ndwi < -0.2;
    } else {
      const l = lum(o.d, i);
      oc = l > 200 && sat(o.d, i) < 0.12;
      ov = !oc && exg(o.d, i) > 0.08;
      ow = !oc && !ov && o.d[i + 2]! >= o.d[i]! && l < 95;
    }
    const sl = lum(s.d, i);
    const sw = sl < waterT;
    const ss = sl > strongT;

    oWater += +ow; sWater += +sw; oVeg += +ov; cloud += +oc; strong += +ss;
    if (ow && sw) both++;
    if (ow || sw) union++;

    let c = 0;
    if (ow && sw) c = 1;
    else if (sw && oc) c = 2;
    else if (sw) c = 3;
    else if (ow) c = 4;
    else if (ss) c = 6;
    else if (ov) c = 5;
    else if (oc) c = 7;
    cat[p] = c;
    if (c) counts[c - 1]!++;
  }
  const pct = (x: number) => (x / n) * 100;
  return {
    cat,
    byCat: counts.map(pct),
    oWater: pct(oWater),
    sWater: pct(sWater),
    oVeg: pct(oVeg),
    cloud: pct(cloud),
    strong: pct(strong),
    iou: union ? (both / union) * 100 : 0,
  };
}

// --------------------------------------------------------------- controls --

function Segmented<T extends string>({
  value,
  options,
  onChange,
  hint,
}: {
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (v: T) => void;
  hint?: T;
}) {
  return (
    <div className="border-rule-strong divide-rule-strong inline-flex flex-wrap divide-x border">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`px-2.5 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            value === o.value
              ? "bg-accent text-white"
              : hint === o.value
                ? "text-accent bg-paper-sunk"
                : "text-ink-muted hover:text-ink"
          }`}
        >
          {o.label}
          {hint === o.value && value !== o.value ? " ●" : ""}
        </button>
      ))}
    </div>
  );
}

export function ModeBar({
  mode,
  onMode,
  changeChoice,
  onChangeChoice,
  features,
  onFeatures,
  frames,
}: {
  mode: Mode;
  onMode: (m: Mode) => void;
  changeChoice: ChangeChoice;
  onChangeChoice: (c: ChangeChoice) => void;
  features: Features;
  onFeatures: (f: Features) => void;
  frames: Frame[];
}) {
  const r = resolveMode(mode, frames, changeChoice);
  const relevant: FeatureKey[] =
    r.mode === "change"
      ? r.changeKind === "multi"
        ? ["changeMap", "stats", "timeline", "persistence"]
        : ["changeMap", "stats"]
      : r.mode === "crossmodal"
        ? ["layers", "agreement", "stats", "notes"]
        : [];

  return (
    <div className="border-rule-strong bg-paper-raised mb-3 space-y-2 border px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="marginal w-20">Mode</span>
        <Segmented
          value={mode}
          hint={r.mode}
          onChange={onMode}
          options={(Object.keys(MODE_LABEL) as Mode[]).map((m) => ({ value: m, label: MODE_LABEL[m] }))}
        />
      </div>
      {r.mode === "change" && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="marginal w-20">Comparison</span>
          <Segmented
            value={changeChoice}
            hint={r.changeKind}
            onChange={onChangeChoice}
            options={[
              { value: "auto", label: "Auto" },
              { value: "bi", label: "Bi-temporal (2 dates)" },
              { value: "multi", label: "Multi-temporal (3+ dates)", disabled: frames.length < 3 },
            ]}
          />
        </div>
      )}
      {relevant.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="marginal w-20">Features</span>
          {relevant.map((k) => (
            <label key={k} className="text-ink flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={features[k]}
                onChange={(e) => onFeatures({ ...features, [k]: e.target.checked })}
                className="accent-[var(--color-accent)]"
              />
              {FEATURE_LABEL[k]}
            </label>
          ))}
        </div>
      )}
      <p className="marginal">
        <span className="text-ink">Now running: {MODE_LABEL[r.mode]}
        {r.mode === "change" ? ` · ${r.changeKind === "bi" ? "bi-temporal" : "multi-temporal"}` : ""}.</span>{" "}
        {r.why}
      </p>
    </div>
  );
}

export function StackInputs({
  frames,
  onAdd,
  onUpdate,
  onRemove,
}: {
  frames: Frame[];
  onAdd: (files: File[]) => void;
  onUpdate: (id: string, patch: Partial<Frame>) => void;
  onRemove: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <section>
      <h2 className="font-serif text-ink text-lg tracking-tight">Image stack</h2>
      <p className="marginal mt-1">
        Add several dates for change detection, or an optical/NDVI/NDWI image plus a SAR image
        for cross-modal validation. PNG, JPEG or WebP. Analysis runs in your browser.
      </p>
      <input
        ref={input}
        type="file"
        multiple
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onAdd(files);
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="border-rule-strong hover:border-accent text-ink mt-2 w-full border border-dashed px-3 py-2 text-xs transition-colors"
      >
        + Add images
      </button>
      <ul className="mt-2 space-y-2">
        {frames.map((f, i) => (
          <li key={f.id} className="border-rule bg-paper-raised flex gap-2 border p-1.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={f.url} alt="" className="h-14 w-14 shrink-0 object-cover" />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-center gap-1">
                <span className="marginal tabular">#{i + 1}</span>
                <span className="text-ink truncate text-xs" title={f.name}>
                  {f.name}
                </span>
                {f.primary ? (
                  <span className="marginal ml-auto">Q&A image</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => onRemove(f.id)}
                    className="marginal hover:text-alert ml-auto"
                    aria-label={`Remove ${f.name}`}
                  >
                    ✕
                  </button>
                )}
              </div>
              <div className="flex gap-1">
                <select
                  value={f.kind}
                  onChange={(e) => onUpdate(f.id, { kind: e.target.value as FrameKind })}
                  className="border-rule-strong bg-paper-raised text-ink min-w-0 flex-1 border px-1 py-0.5 text-xs"
                >
                  {(Object.keys(KIND_LABEL) as FrameKind[]).map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={f.date}
                  onChange={(e) => onUpdate(f.id, { date: e.target.value })}
                  className="border-rule-strong bg-paper-raised text-ink border px-1 py-0.5 text-xs"
                />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------- views --

function Raster({ data, label }: { data: ImageData; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    c.width = data.width;
    c.height = data.height;
    c.getContext("2d")!.putImageData(data, 0, 0);
  }, [data]);
  return (
    <figure className="min-w-0">
      <canvas ref={ref} className="border-rule block h-auto w-full border" />
      <figcaption className="marginal mt-1">{label}</figcaption>
    </figure>
  );
}

function Legend({ cats, values }: { cats: Cat[]; values: number[] }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {cats.map((c, i) => (
          <tr key={c.label} className="border-rule border-b align-top">
            <td className="py-1 pr-2">
              <span
                className="inline-block h-3 w-3"
                style={{ background: `rgb(${c.color.join(",")})` }}
              />
            </td>
            <td className="text-ink py-1 pr-2">
              {c.label}
              <div className="marginal">{c.rule}</div>
            </td>
            <td className="tabular text-ink py-1 text-right">{values[i]!.toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-rule-strong bg-paper-raised border p-3">
      <h3 className="font-serif text-ink mb-2 text-base tracking-tight">{title}</h3>
      {children}
    </section>
  );
}

const HONEST = (
  <p className="border-accent bg-paper-sunk marginal border-l-2 px-2.5 py-1.5">
    Heuristic analysis: pixel statistics computed in your browser, not a trained model. It
    assumes the images are co-registered (same footprint). Percentages are shares of the
    scene.
  </p>
);

export function AnalysisView({
  frames,
  mode,
  changeKind,
  features,
  pair,
  onPair,
  onResult,
}: {
  frames: Frame[];
  mode: "change" | "crossmodal";
  changeKind: "bi" | "multi";
  features: Features;
  pair: [string, string] | null;
  onPair: (p: [string, string]) => void;
  onResult?: (r: Report) => void;
}) {
  const noop = useMemo(() => () => undefined, []);
  return (
    <ReportContext.Provider value={onResult ?? noop}>
      <AnalysisBody
        frames={frames}
        mode={mode}
        changeKind={changeKind}
        features={features}
        pair={pair}
        onPair={onPair}
      />
    </ReportContext.Provider>
  );
}

function AnalysisBody({
  frames,
  mode,
  changeKind,
  features,
  pair,
  onPair,
}: {
  frames: Frame[];
  mode: "change" | "crossmodal";
  changeKind: "bi" | "multi";
  features: Features;
  pair: [string, string] | null;
  onPair: (p: [string, string]) => void;
}) {
  const sorted = useMemo(() => [...frames].sort((a, b) => a.date.localeCompare(b.date)), [frames]);
  const grid = useMemo(() => (sorted[0]! ? gridOf(sorted[0]!.img) : ([1, 1] as [number, number])), [sorted]);
  const px = useMemo(
    () => new Map(sorted.map((f) => [f.id, pixels(f.img, grid[0], grid[1])])),
    [sorted, grid],
  );

  if (mode === "crossmodal") {
    // The latest SAR image, checked against the optical view nearest to it in time.
    const sar = [...sorted].reverse().find((f) => f.kind === "sar");
    const gap = (f: Frame) => Math.abs(Date.parse(f.date) - Date.parse(sar?.date ?? f.date));
    const opt = sorted
      .filter((f) => f.kind !== "sar")
      .sort((x, y) => gap(x) - gap(y))[0];
    if (!opt || !sar)
      return (
        <Panel title="Cross-modal validation">
          <p className="text-ink-muted text-sm">
            Needs one optical, NDVI or NDWI image and one SAR image. Set each image&apos;s type in
            the image stack.
          </p>
        </Panel>
      );
    return <CrossView opt={opt} sar={sar} o={px.get(opt.id)!} s={px.get(sar.id)!} features={features} />;
  }

  if (sorted.length < 2)
    return (
      <Panel title="Multi-temporal change">
        <p className="text-ink-muted text-sm">Add at least two images of the same place.</p>
      </Panel>
    );

  if (changeKind === "bi") {
    const a = sorted.find((f) => f.id === pair?.[0]) ?? sorted[0]!;
    const b = sorted.find((f) => f.id === pair?.[1]) ?? sorted[sorted.length - 1]!;
    return (
      <BiView
        frames={sorted}
        a={a}
        b={b}
        pa={px.get(a.id)!}
        pb={px.get(b.id)!}
        features={features}
        onPair={onPair}
      />
    );
  }
  return <MultiView frames={sorted} px={px} features={features} />;
}

function BiView({
  frames, a, b, pa, pb, features, onPair,
}: {
  frames: Frame[]; a: Frame; b: Frame; pa: Px; pb: Px; features: Features;
  onPair: (p: [string, string]) => void;
}) {
  const r = useMemo(() => detectChange(pa, pb, b.kind), [pa, pb, b.kind]);
  const map = useMemo(() => overlay(pb, r.cat, CHANGE), [pb, r]);
  const top = r.byCat.indexOf(Math.max(...r.byCat));
  useReport({
    kind: "change",
    variant: "bi",
    title: `Bi-temporal change · ${a.date} → ${b.date}`,
    summary: `${r.pct.toFixed(1)}% of the scene changed between ${a.date} and ${b.date}${
      r.pct > 0.5 ? `, mostly ${CHANGE[top]!.label.toLowerCase()} (${r.byCat[top]!.toFixed(1)}%)` : ""
    }.`,
    stats: {
      changed_pct: round(r.pct),
      by_category: Object.fromEntries(CHANGE.map((c, i) => [c.label, round(r.byCat[i]!)])),
    },
    frames: [meta(a), meta(b)],
  });
  const pick = (which: 0 | 1, id: string) => onPair(which === 0 ? [id, b.id] : [a.id, id]);

  return (
    <div className="space-y-3">
      {HONEST}
      <Panel title="Bi-temporal change">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="marginal">Before</span>
          <FramePick frames={frames} value={a.id} onChange={(id) => pick(0, id)} />
          <span className="marginal">After</span>
          <FramePick frames={frames} value={b.id} onChange={(id) => pick(1, id)} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <figure><img src={a.url} alt="" className="border-rule w-full border" /><figcaption className="marginal mt-1">Before · {a.date}</figcaption></figure>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <figure><img src={b.url} alt="" className="border-rule w-full border" /><figcaption className="marginal mt-1">After · {b.date}</figcaption></figure>
          {features.changeMap && <Raster data={map} label="Change map (on the after image)" />}
        </div>
        <p className="text-ink mt-3 text-sm">
          Between {a.date} and {b.date}, <strong>{r.pct.toFixed(1)}%</strong> of the scene
          changed{r.pct > 0.5 ? <>; mostly <strong>{CHANGE[top]!.label.toLowerCase()}</strong> ({r.byCat[top]!.toFixed(1)}%)</> : ""}.
        </p>
      </Panel>
      {features.stats && (
        <Panel title="Area statistics">
          <Legend cats={CHANGE} values={r.byCat} />
          <p className="marginal mt-2">Change threshold for this pair: {(r.threshold * 100).toFixed(0)}% colour distance (mean + 1.5σ).</p>
        </Panel>
      )}
    </div>
  );
}

function FramePick({ frames, value, onChange }: { frames: Frame[]; value: string; onChange: (id: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="border-rule-strong bg-paper-raised text-ink border px-1 py-0.5 text-xs">
      {frames.map((f) => (
        <option key={f.id} value={f.id}>{f.date} · {f.name}</option>
      ))}
    </select>
  );
}

function MultiView({ frames, px, features }: { frames: Frame[]; px: Map<string, Px>; features: Features }) {
  const result = useMemo(() => {
    const steps = frames.slice(1).map((f, i) => {
      const prev = frames[i]!;
      return { from: prev, to: f, r: detectChange(px.get(prev.id)!, px.get(f.id)!, f.kind) };
    });
    const first = px.get(frames[0]!.id)!;
    const last = px.get(frames[frames.length - 1]!.id)!;
    const total = detectChange(first, last, frames[frames.length - 1]!.kind);
    const n = first.w * first.h;
    const hits = new Uint8Array(n);
    for (const s of steps) for (let p = 0; p < n; p++) if (s.r.cat[p]!) hits[p]!++;
    const heat = new ImageData(first.w, first.h);
    let persistent = 0;
    for (let p = 0, i = 0; p < n; p++, i += 4) {
      const t = (hits[p]! - 1) / Math.max(1, steps.length - 1);
      if (hits[p]! >= 2) persistent++;
      const g = 70 + lum(last.d, i) * 0.55;
      heat.data[i] = hits[p]! ? 220 : g;
      heat.data[i + 1] = hits[p]! ? Math.round(200 * (1 - t)) : g;
      heat.data[i + 2] = hits[p]! ? 40 : g;
      heat.data[i + 3] = 255;
    }
    return { steps, total, totalMap: overlay(last, total.cat, CHANGE), heat, persistent: (persistent / n) * 100 };
  }, [frames, px]);

  const max = Math.max(1, ...result.steps.map((s) => s.r.pct));
  const biggest = result.steps.reduce((m, s) => (s.r.pct > m.r.pct ? s : m), result.steps[0]!);
  const top = result.total.byCat.indexOf(Math.max(...result.total.byCat));
  useReport({
    kind: "change",
    variant: "multi",
    title: `Multi-temporal change · ${frames.length} dates, ${frames[0]!.date} → ${frames[frames.length - 1]!.date}`,
    summary: `${result.total.pct.toFixed(1)}% of the scene differs from first to last, mostly ${CHANGE[top]!.label.toLowerCase()}. Biggest step: ${biggest.from.date} → ${biggest.to.date} (${biggest.r.pct.toFixed(1)}%). ${result.persistent.toFixed(1)}% of pixels changed in two or more intervals.`,
    stats: {
      changed_pct: round(result.total.pct),
      persistent_pct: round(result.persistent),
      intervals: result.steps.map((st) => ({ from: st.from.date, to: st.to.date, changed_pct: round(st.r.pct) })),
      by_category: Object.fromEntries(CHANGE.map((c, i) => [c.label, round(result.total.byCat[i]!)])),
    },
    frames: frames.map(meta),
  });

  return (
    <div className="space-y-3">
      {HONEST}
      <Panel title={`Multi-temporal change · ${frames.length} dates`}>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {frames.map((f) => (
            <figure key={f.id} className="w-28 shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={f.url} alt="" className="border-rule w-full border" />
              <figcaption className="marginal mt-1 truncate">{f.date}</figcaption>
            </figure>
          ))}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {features.changeMap && <Raster data={result.totalMap} label={`Overall change · ${frames[0]!.date} → ${frames[frames.length - 1]!.date}`} />}
          {features.persistence && <Raster data={result.heat} label="Persistence: yellow = changed once, red = changed in every interval" />}
        </div>
        <p className="text-ink mt-3 text-sm">
          Across {frames.length} dates, <strong>{result.total.pct.toFixed(1)}%</strong> of the scene
          differs from first to last, mostly <strong>{CHANGE[top]!.label.toLowerCase()}</strong>.
          The biggest step was <strong>{biggest.from.date} → {biggest.to.date}</strong> (
          {biggest.r.pct.toFixed(1)}%). {result.persistent >= 0.5
            ? `${result.persistent.toFixed(1)}% of pixels changed in two or more intervals, which points to ongoing development rather than a one-off event.`
            : "Change in each interval hit different places; nothing kept changing."}
        </p>
      </Panel>
      {features.timeline && (
        <Panel title="Timeline of change">
          <ol className="space-y-1.5">
            {result.steps.map((s) => (
              <li key={s.to.id} className="grid grid-cols-[9rem_1fr_3.5rem] items-center gap-2 text-xs">
                <span className="marginal tabular">{s.from.date} → {s.to.date}</span>
                <span className="bg-paper-sunk h-3">
                  <span className="bg-accent block h-3" style={{ width: `${(s.r.pct / max) * 100}%` }} />
                </span>
                <span className="tabular text-ink text-right">{s.r.pct.toFixed(1)}%</span>
              </li>
            ))}
          </ol>
        </Panel>
      )}
      {features.stats && (
        <Panel title="Area statistics · first → last">
          <Legend cats={CHANGE} values={result.total.byCat} />
        </Panel>
      )}
    </div>
  );
}

function CrossView({ opt, sar, o, s, features }: { opt: Frame; sar: Frame; o: Px; s: Px; features: Features }) {
  const r = useMemo(() => crossModal(o, opt.kind, s), [o, opt.kind, s]);
  const map = useMemo(() => overlay(o, r.cat, CROSS), [o, r]);
  const f = (x: number) => `${x.toFixed(1)}%`;
  const notes = [
    `The ${KIND_LABEL[opt.kind]} image marks ${f(r.oVeg)} as vegetation and ${f(r.oWater)} as water${r.cloud > 0.5 ? `; ${f(r.cloud)} is under cloud` : ""}.`,
    `SAR marks ${f(r.sWater)} as low backscatter (water or smooth surface) and ${f(r.strong)} as strong returns (structures).`,
    `The two sensors agree on ${f(r.iou)} of the water they see between them (intersection over union).`,
    r.byCat[1]! > 0.5 && `Under cloud, SAR shows ${f(r.byCat[1]!)} of the scene as water that the optical image cannot see.`,
    r.byCat[3]! > 0.5 && `${f(r.byCat[3]!)} looks like water only in the optical view. That is often shadow or dark soil, and SAR does not confirm it.`,
    r.byCat[2]! > 0.5 && `${f(r.byCat[2]!)} is dark only in SAR. It could be wet soil, tarmac or flooded vegetation, so check it on the ground.`,
    r.byCat[4]! > 0.5 && `SAR's moderate volume scattering supports ${f(r.byCat[4]!)} of the scene as vegetation.`,
  ].filter(Boolean) as string[];
  useReport({
    kind: "crossmodal",
    variant: null,
    title: `Cross-modal validation · ${KIND_LABEL[opt.kind]} ${opt.date} + SAR ${sar.date}`,
    summary: notes.join(" "),
    stats: {
      water_agreement_iou_pct: round(r.iou),
      optical_water_pct: round(r.oWater),
      sar_water_pct: round(r.sWater),
      optical_vegetation_pct: round(r.oVeg),
      cloud_pct: round(r.cloud),
      by_category: Object.fromEntries(CROSS.map((c, i) => [c.label, round(r.byCat[i]!)])),
    },
    frames: [meta(opt), meta(sar)],
  });

  return (
    <div className="space-y-3">
      {HONEST}
      <Panel title="Cross-modal validation">
        <div className="grid gap-3 sm:grid-cols-3">
          {features.layers && (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <figure><img src={opt.url} alt="" className="border-rule w-full border" /><figcaption className="marginal mt-1">{KIND_LABEL[opt.kind]} · {opt.date}</figcaption></figure>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <figure><img src={sar.url} alt="" className="border-rule w-full border" /><figcaption className="marginal mt-1">SAR · {sar.date}</figcaption></figure>
            </>
          )}
          {features.agreement && <Raster data={map} label="Agreement map" />}
        </div>
      </Panel>
      {features.stats && (
        <Panel title="What each sensor contributes">
          <Legend cats={CROSS} values={r.byCat} />
        </Panel>
      )}
      {features.notes && (
        <Panel title="Complementary notes">
          <ul className="text-ink list-disc space-y-1 pl-5 text-sm">
            {notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </Panel>
      )}
    </div>
  );
}
