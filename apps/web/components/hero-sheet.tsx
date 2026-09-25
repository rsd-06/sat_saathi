"use client";

import Image from "next/image";
import { useRef, useState } from "react";

/**
 * The opening sheet: a real flood, before and after, under one slider.
 *
 * Sentinel-1 radar over Dhubri, Assam, a month apart in 2020. Radar sees
 * through the monsoon cloud that hides the ground from optical satellites,
 * so the flood is visible as it happened. Dragging the divider is the whole
 * product in one gesture: compare dates, see what changed.
 */
export function HeroSheet() {
  const [split, setSplit] = useState(52);
  const frame = useRef<HTMLDivElement>(null);

  function move(clientX: number) {
    const box = frame.current?.getBoundingClientRect();
    if (!box) return;
    setSplit(Math.min(98, Math.max(2, ((clientX - box.left) / box.width) * 100)));
  }

  return (
    <figure className="border-rule-strong bg-paper-raised relative border shadow-[0_30px_60px_-30px_rgb(0_0_0/0.35)]">
      <div className="border-rule divide-rule grid grid-cols-2 divide-x border-b sm:grid-cols-4">
        {[
          ["Centre", "25.868°N 90.143°E"],
          ["Platform", "Sentinel-1 GRD"],
          ["Polarisation", "VV · VH"],
          ["Dates", "7 Jun → 13 Jul 2020"],
        ].map(([label, value]) => (
          <div key={label} className="px-3 py-2">
            <div className="text-ink-faint marginal">{label}</div>
            <div className="text-ink tabular mt-0.5 text-xs sm:text-sm">{value}</div>
          </div>
        ))}
      </div>

      <div
        ref={frame}
        className="relative aspect-[1600/727] cursor-ew-resize touch-none overflow-hidden select-none"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          move(e.clientX);
        }}
        onPointerMove={(e) => {
          if (e.buttons) move(e.clientX);
        }}
      >
        <Image
          src="/imagery/dhubri-2020-07-13-new.jpg"
          alt="Sentinel-1 radar, 13 July 2020: the Brahmaputra in flood across Dhubri district"
          fill
          priority
          sizes="(min-width: 1024px) 50vw, 100vw"
          className="object-cover"
        />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
          <Image
            src="/imagery/dhubri-2020-06-07-new.jpg"
            alt="Sentinel-1 radar, 7 June 2020: the same river before the flood"
            fill
            priority
            sizes="(min-width: 1024px) 50vw, 100vw"
            className="object-cover"
          />
        </div>

        <span className="bg-ink/75 absolute top-3 left-3 px-2 py-1 text-[0.6875rem] font-medium tracking-wide text-white uppercase">
          Before · 7 Jun
        </span>
        <span className="bg-water absolute top-3 right-3 px-2 py-1 text-[0.6875rem] font-medium tracking-wide text-white uppercase">
          Flood · 13 Jul
        </span>

        <div className="absolute inset-y-0 w-0.5 bg-white shadow-[0_0_0_1px_rgb(0_0_0/0.25)]" style={{ left: `${split}%` }}>
          <input
            type="range"
            min={2}
            max={98}
            value={Math.round(split)}
            onChange={(e) => setSplit(Number(e.target.value))}
            aria-label="Compare before and after"
            className="sr-only"
          />
          <span
            aria-hidden
            className="text-ink absolute top-1/2 left-1/2 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-white text-sm shadow-md"
          >
            ⇆
          </span>
        </div>
      </div>

      <figcaption className="border-rule marginal flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t px-3 py-2">
        <span>
          <span className="text-ink">Blue is open water.</span> Drag to compare the Brahmaputra
          before and during the 2020 Assam floods.
        </span>
        <span className="text-ink-faint">
          Contains modified Copernicus Sentinel data (2020), processed by Pierre Markuse · CC BY 2.0
        </span>
      </figcaption>
    </figure>
  );
}
