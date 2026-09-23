"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { decideReview, listReview, type ReviewOut } from "@/lib/api";

export function ReviewQueue() {
  const t = useTranslations();
  const format = useFormatter();
  const [items, setItems] = useState<ReviewOut[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  function load() {
    listReview().then(setItems).catch(() => setFailed(true));
  }

  useEffect(load, []);

  async function decide(jobId: string, decision: "approve" | "reject") {
    setBusy(jobId);
    try {
      await decideReview(jobId, { decision, note: notes[jobId] ?? null });
      load();
    } finally {
      setBusy(null);
    }
  }

  if (failed) {
    return (
      <p className="border-alert bg-alert-wash/60 text-ink marginal border-l-2 px-3 py-2">
        {t("error.apiUnreachable.body")}
      </p>
    );
  }
  if (!items) return <p className="marginal">{t("workspace.inputs.reading")}…</p>;
  if (items.length === 0) {
    return <p className="text-ink-muted text-sm">{t("review.empty")}</p>;
  }

  return (
    <ul className="space-y-4">
      {items.map((item) => (
        <li
          key={item.id}
          className="border-rule-strong bg-paper-raised border"
        >
          <div className="border-rule flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
            <span className="marginal">
              {t("review.reason")} · {item.reason}
            </span>
            <span className="marginal">
              {t("review.confidence")}{" "}
              <span className="text-relief tabular font-medium">
                {item.confidence === null
                  ? "—"
                  : format.number(item.confidence, { style: "percent" })}
              </span>
            </span>
          </div>

          <div className="px-3 py-3">
            <p className="text-ink text-sm">{item.query_text}</p>

            <label className="marginal mt-3 block">
              {t("review.note")}
              <textarea
                rows={2}
                value={notes[item.job_id] ?? ""}
                onChange={(e) =>
                  setNotes((prev) => ({ ...prev, [item.job_id]: e.target.value }))
                }
                className="border-rule-strong bg-paper text-ink mt-1 block w-full rounded-xs border px-2 py-1.5 text-sm outline-none"
              />
            </label>
          </div>

          <div className="border-rule divide-rule flex divide-x border-t">
            <button
              type="button"
              disabled={busy === item.job_id}
              onClick={() => void decide(item.job_id, "approve")}
              className="text-vegetation hover:bg-vegetation-wash/50 marginal flex-1 px-2 py-2 transition-colors disabled:opacity-40"
            >
              {t("review.approve")}
            </button>
            <button
              type="button"
              disabled={busy === item.job_id}
              onClick={() => void decide(item.job_id, "reject")}
              className="text-alert hover:bg-alert-wash/50 marginal flex-1 px-2 py-2 transition-colors disabled:opacity-40"
            >
              {t("review.reject")}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
