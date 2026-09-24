"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { LanguageSwitcher } from "./language-switcher";
import { ModelStatus } from "./model-status";
import { StatusDot } from "./status-dot";
import { API_BASE, getHealth } from "@/lib/api";

type Health = Awaited<ReturnType<typeof getHealth>> | null;

export function SettingsPanel() {
  const t = useTranslations();
  const locale = useLocale();
  const [health, setHealth] = useState<Health>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => {
        setHealth(data);
        setReachable(true);
      })
      .catch(() => setReachable(false));
  }, []);

  const checks = (health?.checks ?? {}) as Record<
    string,
    { status: string; detail: string | null }
  >;

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-ink text-sm font-medium">
          {t("settings.language")}
        </h2>
        <p className="marginal mt-1">{locale}</p>
        <div className="mt-2">
          <LanguageSwitcher />
        </div>
      </section>

      <section>
        <h2 className="text-ink text-sm font-medium">{t("settings.api")}</h2>
        <p className="marginal mt-1">{API_BASE}</p>

        <div className="border-rule divide-rule mt-3 divide-y border-y">
          <div className="flex items-center justify-between py-2">
            <span className="marginal">{t("settings.mode")}</span>
            <span className="marginal flex items-center gap-1.5">
              <StatusDot
                status={reachable ? "succeeded" : reachable === false ? "failed" : "pending"}
              />
              {reachable === null
                ? "…"
                : reachable
                  ? t("settings.reachable")
                  : t("settings.unreachable")}
            </span>
          </div>

          {/* Each dependency reports itself; nothing here is assumed healthy. */}
          {Object.entries(checks).map(([name, check]) => (
            <div key={name} className="flex items-center justify-between py-2">
              <span className="marginal">{name}</span>
              <span className="marginal flex items-center gap-1.5">
                <StatusDot
                  status={
                    check.status === "ok"
                      ? "succeeded"
                      : check.status === "skipped"
                        ? "pending"
                        : "failed"
                  }
                />
                {check.status}
              </span>
            </div>
          ))}
        </div>

        {health && (
          <p className="marginal mt-2">
            {t("settings.mode")} · {String(health.mode)}
          </p>
        )}
      </section>

      <ModelStatus />
    </div>
  );
}
