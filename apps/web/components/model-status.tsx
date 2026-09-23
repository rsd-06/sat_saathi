"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { listModels, type ModelsOut } from "@/lib/api";
import { StatusDot } from "./status-dot";

/**
 * Which models this deployment actually has.
 *
 * The honest version of a capability list. Every model the system knows about
 * appears, installed or not, so an operator can see what to put on the box
 * rather than discovering a step was fixture output by reading a trace.
 */
export function ModelStatus() {
  const t = useTranslations();
  const [data, setData] = useState<ModelsOut | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    listModels()
      .then(setData)
      .catch(() => setFailed(true));
  }, []);

  if (failed) return null;

  const models = data?.models ?? [];
  const measuring = data ? data.tool_count - data.stub_tool_count : 0;

  return (
    <section>
      <h2 className="text-ink text-sm font-medium">{t("settings.models.title")}</h2>
      <p className="marginal mt-1 max-w-prose">{t("settings.models.body")}</p>

      {data && (
        <p className="marginal mt-3">
          {t("settings.models.count", {
            available: data.available_count,
            total: models.length,
          })}
          {" · "}
          {t("settings.models.measuring", {
            measuring,
            total: data.tool_count,
          })}
        </p>
      )}

      {data && data.available_count === 0 && (
        <p className="border-relief bg-relief-wash/50 text-ink marginal mt-3 border-l-2 px-3 py-2">
          {t("settings.models.empty")}
        </p>
      )}

      <div className="border-rule divide-rule mt-3 divide-y border-y">
        {models.map((model) => (
          <div key={model.name} className="py-2.5">
            {/* Name and status share a row and stay aligned across rows; the
                description sits under them rather than pushing them around. */}
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
                <StatusDot status={model.available ? "succeeded" : "pending"} />
                <span className="truncate">{model.name}</span>
              </span>

              <span className="marginal flex shrink-0 items-baseline gap-4">
                <span className="tabular">{model.revision}</span>
                <span
                  className={`w-24 text-right ${
                    model.available ? "text-vegetation" : "text-ink-faint"
                  }`}
                >
                  {model.available
                    ? t("settings.models.installed")
                    : t("settings.models.missing")}
                </span>
                <span className="text-ink-faint w-10 text-right uppercase">
                  {model.queue}
                </span>
              </span>
            </div>

            {/* Operator detail, deliberately not localised: it names hardware
                and sensors, and a translated path helps nobody. */}
            <p className="marginal mt-1 max-w-prose pl-4">{model.note}</p>
          </div>
        ))}
      </div>

      {data && (
        <p className="marginal mt-2">
          {t("settings.models.directory")}: <span className="tabular">{data.models_dir}</span>
        </p>
      )}
    </section>
  );
}
