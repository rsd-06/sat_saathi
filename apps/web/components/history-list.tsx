"use client";

import { useEffect, useMemo, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { StatusDot } from "./status-dot";
import {
  deleteAnalysis,
  listAnalyses,
  listJobs,
  type AnalysisOut,
  type JobPage,
} from "@/lib/api";

type Entry =
  | { type: "job"; at: string; job: JobPage["items"][number] }
  | { type: "analysis"; at: string; analysis: AnalysisOut };

type Filter = "all" | "qa" | "change" | "crossmodal";

const FILTERS: [Filter, string][] = [
  ["all", "All"],
  ["qa", "Questions"],
  ["change", "Change detection"],
  ["crossmodal", "Cross-modal"],
];

/**
 * Everything this account has run, from the database and nothing else.
 *
 * Questions are jobs on the server; change and cross-modal analyses are saved
 * from the workspace when they finish. Both are listed newest first.
 */
export function HistoryList() {
  const t = useTranslations();
  const format = useFormatter();
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listJobs(100), listAnalyses(100)])
      .then(([jobs, analyses]) =>
        setEntries(
          [
            ...jobs.items.map((job): Entry => ({ type: "job", at: job.created_at, job })),
            ...analyses.map((analysis): Entry => ({
              type: "analysis",
              at: analysis.created_at,
              analysis,
            })),
          ].sort((a, b) => b.at.localeCompare(a.at)),
        ),
      )
      .catch(() => setFailed(true));
  }, []);

  const counts = useMemo(() => {
    const c = { all: 0, qa: 0, change: 0, crossmodal: 0 };
    for (const e of entries ?? []) {
      c.all++;
      c[e.type === "job" ? "qa" : e.analysis.kind]++;
    }
    return c;
  }, [entries]);

  const shown = (entries ?? []).filter(
    (e) =>
      filter === "all" ||
      (filter === "qa" ? e.type === "job" : e.type === "analysis" && e.analysis.kind === filter),
  );

  async function remove(id: string) {
    await deleteAnalysis(id).catch(() => undefined);
    setEntries((es) => es?.filter((e) => e.type !== "analysis" || e.analysis.id !== id) ?? null);
  }

  const when = (iso: string) =>
    format.dateTime(new Date(iso), {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  if (failed) {
    return (
      <p className="border-alert bg-alert-wash/60 text-ink border-l-2 px-4 py-3 text-sm">
        {t("error.apiUnreachable.body")}
      </p>
    );
  }
  if (!entries) {
    return (
      <div className="space-y-2" aria-busy>
        {[0, 1, 2].map((i) => (
          <div key={i} className="bg-paper-sunk h-16 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            aria-pressed={filter === key}
            className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
              filter === key
                ? "border-accent bg-accent text-white"
                : "border-rule-strong text-ink-muted hover:text-ink hover:border-ink-muted"
            }`}
          >
            {label} <span className="tabular opacity-70">{counts[key]}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="border-rule-strong mt-6 border border-dashed px-6 py-12 text-center">
          <p className="text-ink font-serif text-xl">Nothing here yet</p>
          <p className="text-ink-muted mx-auto mt-2 max-w-md text-sm">
            {filter === "qa"
              ? "Ask a question about an image in the workspace and it will be listed here."
              : filter === "all"
                ? t("history.empty")
                : "Add two or more images to the image stack in the workspace. Each finished analysis is saved here."}
          </p>
          <Link
            href="/workspace"
            className="text-accent hover:text-accent-hover mt-4 inline-block text-sm font-medium underline underline-offset-4"
          >
            Open the workspace
          </Link>
        </div>
      ) : (
        <ul className="border-rule divide-rule mt-5 divide-y border-y">
          {shown.map((e) =>
            e.type === "job" ? (
              <li key={`j-${e.job.id}`}>
                <Link
                  href={`/jobs/${e.job.id}`}
                  className="hover:bg-paper-sunk/60 group grid grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-1 px-2 py-4 transition-colors"
                >
                  <Badge tone="accent">Q&amp;A</Badge>
                  <span className="min-w-0">
                    <span className="text-ink group-hover:text-accent block truncate text-[0.9375rem] transition-colors">
                      {e.job.query_text}
                    </span>
                    <span className="marginal mt-0.5 flex flex-wrap items-center gap-x-3">
                      <span className="flex items-center gap-1.5">
                        <StatusDot status={e.job.status} />
                        {t(`job.status.${e.job.status}`)}
                      </span>
                      <span>{t(`job.mode.${e.job.mode}`)}</span>
                      <span className="uppercase">{e.job.query_lang}</span>
                      {e.job.confidence !== null && (
                        <span>
                          {format.number(e.job.confidence, { style: "percent" })} confidence
                        </span>
                      )}
                    </span>
                  </span>
                  <span className="marginal tabular text-right">{when(e.at)}</span>
                </Link>
              </li>
            ) : (
              <li key={`a-${e.analysis.id}`}>
                <button
                  type="button"
                  onClick={() => setOpen(open === e.analysis.id ? null : e.analysis.id)}
                  aria-expanded={open === e.analysis.id}
                  className="hover:bg-paper-sunk/60 group grid w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 px-2 py-4 text-left transition-colors"
                >
                  <Badge tone={e.analysis.kind === "change" ? "relief" : "vegetation"}>
                    {e.analysis.kind === "change"
                      ? e.analysis.variant === "multi"
                        ? "Multi"
                        : "Bi"
                      : "Cross"}
                  </Badge>
                  <span className="min-w-0">
                    <span className="text-ink group-hover:text-accent block truncate text-[0.9375rem] transition-colors">
                      {e.analysis.title}
                    </span>
                    <span className="marginal mt-0.5 block truncate">{e.analysis.summary}</span>
                  </span>
                  <span className="marginal tabular text-right">{when(e.at)}</span>
                </button>
                {open === e.analysis.id && (
                  <AnalysisDetail analysis={e.analysis} onDelete={() => void remove(e.analysis.id)} />
                )}
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}

function Badge({ tone, children }: { tone: "accent" | "relief" | "vegetation"; children: React.ReactNode }) {
  const tones = {
    accent: "bg-accent-wash text-accent",
    relief: "bg-relief-wash text-relief",
    vegetation: "bg-vegetation-wash text-vegetation",
  };
  return (
    <span
      className={`${tones[tone]} grid h-9 w-14 place-items-center rounded-xs text-[0.6875rem] font-semibold tracking-wide uppercase`}
    >
      {children}
    </span>
  );
}

function AnalysisDetail({ analysis, onDelete }: { analysis: AnalysisOut; onDelete: () => void }) {
  const byCategory = (analysis.stats.by_category ?? {}) as Record<string, number>;
  const intervals = (analysis.stats.intervals ?? []) as {
    from: string;
    to: string;
    changed_pct: number;
  }[];
  const max = Math.max(1, ...Object.values(byCategory), ...intervals.map((i) => i.changed_pct));

  return (
    <div className="bg-paper-sunk/50 border-rule space-y-4 border-t px-4 py-4 sm:pl-20">
      <p className="text-ink text-sm leading-relaxed">{analysis.summary}</p>

      <div className="flex flex-wrap gap-2">
        {analysis.frames.map((f) => (
          <span key={`${f.name}-${f.date}`} className="border-rule-strong bg-paper-raised border px-2 py-1 text-xs">
            <span className="text-ink-faint uppercase">{f.kind}</span> · {f.date} ·{" "}
            <span className="text-ink-muted">{f.name}</span>
          </span>
        ))}
      </div>

      {intervals.length > 0 && (
        <div>
          <p className="marginal mb-1.5">Change per interval</p>
          {intervals.map((i) => (
            <Bar key={`${i.from}-${i.to}`} label={`${i.from} → ${i.to}`} value={i.changed_pct} max={max} />
          ))}
        </div>
      )}
      {Object.keys(byCategory).length > 0 && (
        <div>
          <p className="marginal mb-1.5">By category</p>
          {Object.entries(byCategory).map(([label, value]) => (
            <Bar key={label} label={label} value={value} max={max} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        <span className="marginal">
          Method: pixel heuristic in the browser ({analysis.method}), not a trained model.
        </span>
        <button
          type="button"
          onClick={onDelete}
          className="text-alert hover:bg-alert-wash/50 rounded-xs px-2 py-1 text-xs transition-colors"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className="grid grid-cols-[minmax(0,14rem)_1fr_3.5rem] items-center gap-3 py-0.5 text-xs">
      <span className="text-ink-muted truncate">{label}</span>
      <span className="bg-paper-raised h-2">
        <span className="bg-accent block h-2" style={{ width: `${(value / max) * 100}%` }} />
      </span>
      <span className="tabular text-ink text-right">{value.toFixed(1)}%</span>
    </div>
  );
}
