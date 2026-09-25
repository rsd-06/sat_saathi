"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { decideReview, listAllReview, type ReviewOut } from "@/lib/api";

type Tab = "pending" | "resolved";

/**
 * Answers held back because the system was not sure enough to release them.
 *
 * A reviewer sees why each was held and how confident the run was, opens the
 * full answer and trace, then approves or rejects it with a note. Decisions
 * stay listed under Resolved, so nothing disappears without a record.
 */
export function ReviewQueue({ thresholdPct }: { thresholdPct: number }) {
  const t = useTranslations();
  const format = useFormatter();
  const [items, setItems] = useState<ReviewOut[] | null>(null);
  const [tab, setTab] = useState<Tab>("pending");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    listAllReview().then(setItems).catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  const pending = useMemo(() => (items ?? []).filter((i) => i.status === "pending"), [items]);
  const resolved = useMemo(() => (items ?? []).filter((i) => i.status !== "pending"), [items]);
  const shown = tab === "pending" ? pending : resolved;
  const approved = resolved.filter((i) => i.status === "approved").length;

  async function decide(jobId: string, decision: "approve" | "reject") {
    setBusy(jobId);
    try {
      await decideReview(jobId, { decision, note: notes[jobId]?.trim() || null });
      load();
    } finally {
      setBusy(null);
    }
  }

  if (failed) {
    return (
      <p className="border-alert bg-alert-wash/60 text-ink border-l-2 px-4 py-3 text-sm">
        {t("error.apiUnreachable.body")}
      </p>
    );
  }
  if (!items) {
    return (
      <div className="space-y-3" aria-busy>
        {[0, 1].map((i) => (
          <div key={i} className="bg-paper-sunk h-40 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <dl className="grid grid-cols-3 gap-6">
        {[
          ["Waiting for you", pending.length, "text-relief", "bg-relief-wash/30"],
          ["Approved", approved, "text-vegetation", "bg-vegetation-wash/30"],
          ["Rejected", resolved.length - approved, "text-alert", "bg-alert-wash/30"],
        ].map(([label, value, tone, bg]) => (
          <div key={label as string} className={`rounded-2xl border border-black/5 px-6 py-5 shadow-sm ${bg}`}>
            <dt className="text-ink-muted text-sm font-medium">{label}</dt>
            <dd className={`font-serif tabular mt-2 text-4xl font-semibold ${tone}`}>{value}</dd>
          </div>
        ))}
      </dl>

      <div className="border-rule mt-6 flex gap-6 border-b" role="tablist">
        {(
          [
            ["pending", `Pending (${pending.length})`],
            ["resolved", `Resolved (${resolved.length})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 pb-2.5 text-sm font-medium transition-colors ${
              tab === key ? "border-accent text-ink" : "text-ink-muted hover:text-ink border-transparent"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="border-rule-strong mt-6 border border-dashed px-6 py-12 text-center">
          <p className="text-ink font-serif text-xl">
            {tab === "pending" ? "All clear" : "No decisions yet"}
          </p>
          <p className="text-ink-muted mx-auto mt-2 max-w-md text-sm">
            {tab === "pending"
              ? `Answers below ${thresholdPct}% confidence are held here before anyone relies on them. None are waiting.`
              : "Approved and rejected answers are kept here with the reviewer's note."}
          </p>
        </div>
      ) : (
        <ul className="mt-6 space-y-4">
          {shown.map((item) => {
            const pct = item.confidence === null ? null : Math.round(item.confidence * 100);
            return (
              <li key={item.id} className="bg-paper rounded-2xl border border-black/5 shadow-md hover:shadow-lg transition-shadow overflow-hidden">
                <div className="flex flex-wrap items-start justify-between gap-6 px-6 pt-6">
                  <div className="min-w-0 flex-1">
                    <p className="marginal">
                      Held {format.relativeTime(new Date(item.created_at))} · {t("review.reason")}:{" "}
                      <span className="text-ink font-medium">{item.reason}</span>
                    </p>
                    <p className="text-ink mt-2 font-serif text-xl leading-snug">
                      {item.query_text}
                    </p>
                  </div>
                  <div className="w-48 shrink-0 bg-paper-sunk/50 rounded-lg p-3">
                    <div className="flex items-baseline justify-between mb-2">
                      <span className="marginal font-medium">{t("review.confidence")}</span>
                      <span className="tabular text-ink text-sm font-bold">
                        {pct === null ? "—" : `${pct}%`}
                      </span>
                    </div>
                    <div className="bg-paper-sunk relative h-2.5 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${pct !== null && pct >= thresholdPct ? "bg-vegetation" : "bg-relief"}`}
                        style={{ width: `${pct ?? 0}%` }}
                      />
                      <div
                        className="bg-ink absolute top-0 bottom-0 w-0.5"
                        style={{ left: `${thresholdPct}%` }}
                        title={`Release threshold ${thresholdPct}%`}
                      />
                    </div>
                    <p className="text-ink-faint mt-1.5 text-right text-xs">threshold {thresholdPct}%</p>
                  </div>
                </div>

                <div className="px-4 pt-3 pb-4">
                  <Link
                    href={`/jobs/${item.job_id}`}
                    className="text-accent hover:text-accent-hover text-sm font-medium underline decoration-current/30 underline-offset-4"
                  >
                    Open the answer and its trace →
                  </Link>

                  {item.status === "pending" ? (
                    <label className="mt-3 block">
                      <span className="marginal">{t("review.note")}</span>
                      <textarea
                        rows={2}
                        value={notes[item.job_id] ?? ""}
                        placeholder="Why you approve or reject it (kept with the decision)"
                        onChange={(e) =>
                          setNotes((prev) => ({ ...prev, [item.job_id]: e.target.value }))
                        }
                        className="border-rule-strong bg-paper text-ink placeholder:text-ink-faint focus:border-accent mt-1 block w-full rounded-xs border px-3 py-2 text-sm outline-none"
                      />
                    </label>
                  ) : (
                    <p className="mt-3 text-sm">
                      <span
                        className={`rounded-xs px-2 py-0.5 text-xs font-semibold uppercase ${
                          item.status === "approved"
                            ? "bg-vegetation-wash text-vegetation"
                            : "bg-alert-wash text-alert"
                        }`}
                      >
                        {item.status}
                      </span>
                      {item.resolved_at && (
                        <span className="marginal ml-2">
                          {format.relativeTime(new Date(item.resolved_at))}
                        </span>
                      )}
                      {item.reviewer_note && (
                        <span className="text-ink-muted mt-1.5 block italic">
                          “{item.reviewer_note}”
                        </span>
                      )}
                    </p>
                  )}
                </div>

                {item.status === "pending" && (
                  <div className="border-rule bg-paper-sunk/30 flex justify-end gap-3 border-t px-6 py-4">
                    <button
                      type="button"
                      disabled={busy === item.job_id}
                      onClick={() => void decide(item.job_id, "reject")}
                      className="border-alert/30 text-alert hover:bg-alert-wash/80 rounded-full border px-6 py-2.5 text-sm font-medium transition-all hover:-translate-y-0.5 disabled:opacity-40 disabled:hover:translate-y-0"
                    >
                      {t("review.reject")}
                    </button>
                    <button
                      type="button"
                      disabled={busy === item.job_id}
                      onClick={() => void decide(item.job_id, "approve")}
                      className="bg-vegetation shadow-sm rounded-full px-7 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 hover:shadow-md hover:-translate-y-0.5 disabled:opacity-40 disabled:hover:translate-y-0"
                    >
                      {t("review.approve")}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
