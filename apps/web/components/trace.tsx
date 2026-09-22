"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { StatusDot } from "./status-dot";
import type { Step } from "@/lib/mock";

function Detail({ step }: { step: Step }) {
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
      {step.isStub && (
        <div className="marginal text-relief">{t("workspace.trace.stubHint")}</div>
      )}
    </div>
  );
}

export function Trace({ steps }: { steps: Step[] }) {
  const t = useTranslations();
  const [open, setOpen] = useState<string | null>("compute");
  const [copied, setCopied] = useState(false);

  async function copyTrace() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(steps, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard unavailable; the download action still works. */
    }
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("workspace.trace.title")}
        </h2>
        <button
          type="button"
          onClick={copyTrace}
          className="text-accent hover:text-accent-hover marginal transition-colors"
        >
          {copied ? t("workspace.trace.copied") : t("workspace.trace.copy")}
        </button>
      </div>
      <p className="marginal mt-1">{t("workspace.trace.subtitle")}</p>

      <ol className="border-rule mt-4 border-t">
        {steps.map((step, i) => {
          const isOpen = open === step.key;
          return (
            <li key={step.key} className="border-rule border-b">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : step.key)}
                aria-expanded={isOpen}
                className="hover:bg-paper-sunk/60 flex w-full items-baseline gap-2.5 px-1 py-2.5 text-left transition-colors"
              >
                <span className="marginal text-ink-faint tabular w-5 shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <StatusDot
                  status={step.status}
                  className="translate-y-[-2px]"
                />
                <span className="min-w-0 flex-1">
                  <span className="text-ink block text-sm">
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
                    ? "—"
                    : t("workspace.trace.duration", { ms: step.durationMs })}
                </span>
              </button>
              {isOpen && <div className="pb-3 pl-8">{<Detail step={step} />}</div>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
