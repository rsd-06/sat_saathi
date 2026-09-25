"use client";

import { useFormatter, useTranslations } from "next-intl";

import { StatusDot } from "./status-dot";
import type { StepOut } from "@/lib/api";

type Summary = Record<string, unknown>;

const str = (v: unknown) => (v === undefined || v === null ? "" : String(v));

/** Parses the trace's flat box list: "label[x1,y1,x2,y2]:status;…" (0-1000). */
export function parseBoxes(raw: unknown) {
  const out: {
    label: string;
    box: [number, number, number, number];
    status: string;
  }[] = [];
  for (const m of str(raw).matchAll(/([^;[\]]+)\[([-\d.,\s]+)\](?::(\w+))?/g)) {
    const [x1, y1, x2, y2] = (m[2] ?? "").split(",").map(Number);
    if ([x1, y1, x2, y2].every((n) => Number.isFinite(n))) {
      out.push({
        label: (m[1] ?? "").trim(),
        box: [x1!, y1!, x2!, y2!],
        status: m[3] ?? "model",
      });
    }
  }
  return out;
}

/** The four things an officer asks of a run: who routed it, was the input
 *  sound, what is in the scene, and what is the answer. Read from the trace. */
export function PipelineStages({ steps }: { steps: StepOut[] }) {
  const t = useTranslations("pipeline");
  const format = useFormatter();
  const by = (k: string) => steps.find((s) => s.step_key === k);
  const understand = by("understand");
  const imagery = by("imagery");
  const vlm = by("vision_language");
  const verify = by("verify");
  const img = (imagery?.output_summary ?? {}) as Summary;
  const v = (vlm?.output_summary ?? {}) as Summary;
  const ver = (verify?.output_summary ?? {}) as Summary;
  const fixture = vlm?.is_stub || v.source === "fixture";

  const task = str(vlm?.params?.task) || str(v.task);
  const adapter = str(v.adapter) || str(vlm?.tool_name);
  const sensor = str(img.sensor_type);
  const confidence = typeof v.confidence === "number" ? v.confidence : null;
  const band = str(v.confidence_band) || str(ver.confidence_band);
  const marked = parseBoxes(v.boxes_2d);

  const stages: {
    key: string;
    step?: StepOut;
    lines: [string, string][];
    text?: string;
  }[] = [
    {
      key: "orchestrator",
      step: understand,
      lines: [
        [
          t("intent"),
          str(understand?.output_summary?.intent).replace(/_/g, " "),
        ],
        [t("task"), task],
        [
          t("routedTo"),
          adapter
            ? `${adapter}${vlm?.tool_name ? ` (${vlm.tool_name})` : ""}`
            : "",
        ],
        [t("why"), sensor ? t("because", { sensor, task: task || "vqa" }) : ""],
      ],
    },
    {
      key: "verification",
      step: imagery,
      lines: [
        [t("sensor"), sensor],
        [
          t("size"),
          img.width
            ? `${str(img.width)} × ${str(img.height)} px · ${str(img.bands)} ${t("bands")}`
            : "",
        ],
        [
          t("crs"),
          img.georeferenced
            ? str(img.crs)
            : img.crs
              ? t("notGeoreferenced")
              : "",
        ],
      ],
    },
    {
      key: "caption",
      step: vlm,
      text: str(v.caption),
      lines: [[t("adapter"), str(v.caption_adapter)]],
    },
    {
      key: "vqa",
      step: vlm,
      // A grounding answer is JSON; the boxes are drawn, so say it in words.
      text: marked.length
        ? t("marked", { count: marked.length, label: marked[0]!.label })
        : str(v.answer),
      lines: [
        [
          t("confidence"),
          confidence === null
            ? ""
            : `${format.number(confidence, { style: "percent" })}${band ? ` · ${t(`band.${band}`)}` : ""}`,
        ],
        [t("boxes"), v.boxes ? `${str(v.boxes)} (${str(v.box_status)})` : ""],
        [
          t("prior"),
          v.prior_metric ? `${str(v.prior_metric)} = ${str(v.prior)}` : "",
        ],
        [
          t("verdictLabel"),
          ver.verdict ? t(`verdict.${str(ver.verdict)}`) : "",
        ],
      ],
    },
  ];

  return (
    <section>
      <h2 className="font-serif text-ink text-lg tracking-tight">
        {t("title")}
      </h2>
      {fixture && vlm?.status === "succeeded" && (
        <p className="marginal text-relief mt-1">{t("fixture")}</p>
      )}
      <ol className="mt-3 space-y-2">
        {stages.map((s, i) => {
          const status = s.step?.status ?? "pending";
          const lines = s.lines.filter(([, value]) => value);
          return (
            <li
              key={s.key}
              className="border-rule-strong bg-paper-raised border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className="marginal tabular text-ink-faint">{i + 1}</span>
                <StatusDot status={status} />
                <span className="text-ink text-sm font-medium">
                  {t(`${s.key}.title`)}
                </span>
              </div>
              {status === "pending" || status === "running" ? (
                <p className="marginal mt-1">{t(`${s.key}.body`)}</p>
              ) : (
                <>
                  {s.text && (
                    <p className="text-ink mt-1.5 text-sm leading-relaxed">
                      {s.text}
                    </p>
                  )}
                  {lines.length > 0 && (
                    <dl className="mt-1.5 space-y-0.5">
                      {lines.map(([label, value]) => (
                        <div key={label} className="marginal">
                          <span className="text-ink-faint">{label} · </span>
                          <span className="text-ink-muted break-words">
                            {value}
                          </span>
                        </div>
                      ))}
                    </dl>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
