"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { StatusDot } from "./status-dot";
import type { RunStep } from "@/lib/orchestrator";

/** Reasons a step declined to produce a figure, spelled out in the trace. */
const NOTES: Record<string, string> = {
  "rgb-no-crs":
    "Three visible bands and no coordinate system. Area on the ground is not derivable from this file.",
  "ndvi-ndwi-unavailable":
    "NDVI, NDWI and LSWI need a near-infrared or SWIR band. This file has none, so they were not computed rather than approximated.",
  "intent-defaulted":
    "No keyword in the question matched a known task, so this fell back to a general land-cover reading. Rephrasing with a term like water, crop, change or built-up will route it deliberately.",
};

function Detail({ step }: { step: RunStep }) {
  const t = useTranslations();
  const rows: [string, string][] = [];

  if (step.params) {
    rows.push([
      t("workspace.trace.params"),
      Object.entries(step.params)
        .map(([k, v]) => `${k}=${v}`)
        .join("  "),
    ]);
  }
  if (step.output) {
    rows.push([
      t("workspace.trace.output"),
      Object.entries(step.output)
        .map(([k, v]) => `${k}=${v}`)
        .join("  "),
    ]);
  }
  if (step.artifacts?.length) {
    rows.push([
      t("workspace.trace.artifacts"),
      step.artifacts.map((a) => a.name).join("  "),
    ]);
  }

  return (
    <div className="border-rule mt-2 space-y-1.5 border-l pl-3">
      <div className="marginal">
        {t("workspace.trace.tool")} · {step.tool} {step.version}
      </div>
      {rows.map(([label, value]) => (
        <div key={label} className="marginal">
          <span className="text-ink-faint">{label} · </span>
          <span className="text-ink-muted tabular break-all">{value}</span>
        </div>
      ))}
      {step.note && NOTES[step.note] && (
        <div className="marginal text-relief">{NOTES[step.note]}</div>
      )}
      {step.isStub && (
        <div className="marginal text-relief">
          {t("workspace.trace.stubHint")}
        </div>
      )}
    </div>
  );
}

export function Trace({ steps }: { steps: RunStep[] }) {
  const t = useTranslations();
  const [pinned, setPinned] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const listRef = useRef<HTMLOListElement>(null);

  const running = steps.find((s) => s.status === "running")?.key ?? null;
  // While a run is live the current step opens itself; a click pins one open.
  const open = pinned ?? running;

  // Keep the active step in view without yanking the whole page around.
  useEffect(() => {
    if (!running || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-step="${running}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [running]);

  async function copyTrace() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(steps, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard blocked; the trace is still on screen. */
    }
  }

  function downloadTrace() {
    const blob = new Blob(
      [JSON.stringify({ trace_version: 1, steps }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "satsaathi-trace.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("workspace.trace.title")}
        </h2>
        <div className="flex shrink-0 items-baseline gap-3">
          <button
            type="button"
            onClick={copyTrace}
            className="text-accent hover:text-accent-hover marginal transition-colors"
          >
            {copied ? t("workspace.trace.copied") : t("workspace.trace.copy")}
          </button>
          <button
            type="button"
            onClick={downloadTrace}
            className="text-accent hover:text-accent-hover marginal transition-colors"
          >
            JSON
          </button>
        </div>
      </div>
      <p className="marginal mt-1">{t("workspace.trace.subtitle")}</p>

      <ol ref={listRef} className="border-rule mt-4 border-t">
        {steps.map((step, i) => {
          const isOpen = open === step.key;
          return (
            <li
              key={step.key}
              data-step={step.key}
              className="border-rule border-b"
            >
              <button
                type="button"
                onClick={() => setPinned(isOpen ? null : step.key)}
                aria-expanded={isOpen}
                className="hover:bg-paper-sunk/60 flex w-full items-baseline gap-2.5 px-1 py-2.5 text-left transition-colors"
              >
                <span className="marginal text-ink-faint tabular w-5 shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <StatusDot status={step.status} className="translate-y-[-2px]" />
                <span className="min-w-0 flex-1">
                  <span
                    className={`block text-sm ${
                      step.status === "pending" ? "text-ink-faint" : "text-ink"
                    }`}
                  >
                    {t(`steps.${step.key}.title`)}
                  </span>
                  {isOpen && (
                    <span className="marginal mt-0.5 block">
                      {t(`steps.${step.key}.body`)}
                    </span>
                  )}
                </span>
                {step.isStub && (
                  <span className="marginal text-relief shrink-0">
                    {t("workspace.trace.stub")}
                  </span>
                )}
                <span className="marginal tabular w-14 shrink-0 text-right">
                  {step.durationMs === null
                    ? step.status === "running"
                      ? "…"
                      : "—"
                    : t("workspace.trace.duration", { ms: step.durationMs })}
                </span>
              </button>
              {isOpen && step.status !== "pending" && (
                <div className="pb-3 pl-8">
                  <Detail step={step} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
