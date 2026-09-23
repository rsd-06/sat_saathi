"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { setAssetBands, type AssetOut } from "@/lib/api";

/** Keys come from the API; the labels are ours to localise. */
const PRESETS = [
  "sentinel-2-l2a",
  "landsat-8-9-oli",
  "resourcesat-2-liss3",
  "resourcesat-liss4",
  "cartosat-2s-mx",
  "sentinel-1-grd",
  "eos-04-risat",
] as const;

const ROLES = ["blue", "green", "red", "nir", "swir1", "vv", "vh"] as const;

export function BandMapping({
  asset,
  onChange,
}: {
  asset: AssetOut;
  onChange: (asset: AssetOut) => void;
}) {
  const t = useTranslations();
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState(false);
  const [draft, setDraft] = useState<Record<string, number>>(
    (asset.band_map as Record<string, number>) ?? {},
  );

  async function apply(body: { preset?: string; band_map?: Record<string, number> }) {
    setBusy(true);
    try {
      onChange(await setAssetBands(asset.id, body));
    } finally {
      setBusy(false);
    }
  }

  const unavailable = asset.unavailable_indices as Record<string, string[]>;

  return (
    <div className="space-y-5">
      <section>
        <h3 className="text-ink text-sm font-medium">
          {t("workspace.bands.title")}
        </h3>
        <p className="marginal mt-1">{t("workspace.bands.presetHint")}</p>

        <select
          value={asset.sensor_preset ?? ""}
          disabled={busy}
          onChange={(e) => {
            if (!e.target.value) return;
            void apply({ preset: e.target.value });
          }}
          className="border-rule-strong bg-paper-raised text-ink mt-2 w-full rounded-xs border px-2 py-1.5 text-sm"
        >
          <option value="">{t("workspace.bands.preset")}…</option>
          {PRESETS.map((key) => (
            <option key={key} value={key}>
              {t(`workspace.bands.presetName.${key}`)}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => setManual((v) => !v)}
          className="text-accent hover:text-accent-hover marginal mt-2 underline underline-offset-2"
        >
          {t("workspace.bands.manual")}
        </button>

        {manual && (
          <div className="border-rule mt-2 space-y-1.5 border-t pt-2">
            {ROLES.map((role) => (
              <label key={role} className="marginal flex items-center gap-2">
                <span className="w-14">{t(`workspace.bands.role.${role}`)}</span>
                <select
                  value={draft[role] ?? ""}
                  onChange={(e) =>
                    setDraft((prev) => {
                      const next = { ...prev };
                      if (!e.target.value) delete next[role];
                      else next[role] = Number(e.target.value);
                      return next;
                    })
                  }
                  className="border-rule-strong bg-paper-raised text-ink flex-1 rounded-xs border px-1.5 py-0.5"
                >
                  <option value="">—</option>
                  {Array.from({ length: asset.band_count }, (_, i) => i + 1).map(
                    (n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ),
                  )}
                </select>
              </label>
            ))}
            <button
              type="button"
              disabled={busy || Object.keys(draft).length === 0}
              onClick={() => void apply({ band_map: draft })}
              className="bg-accent hover:bg-accent-hover mt-1 w-full rounded-xs px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-40"
            >
              {t("workspace.bands.applyMapping")}
            </button>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-ink text-sm font-medium">
          {t("workspace.analyses.title")}
        </h3>
        {/* An index whose band is absent is struck through with the reason —
            the product never substitutes a band to fill the gap. */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(["ndvi", "ndwi", "lswi"] as const).map((name) => {
            const missing = unavailable[name];
            return (
              <span
                key={name}
                title={missing ? missing.join(", ") : undefined}
                className={`border px-2 py-1 text-xs uppercase ${
                  missing
                    ? "border-rule text-ink-faint line-through"
                    : "border-vegetation text-vegetation bg-vegetation-wash/50"
                }`}
              >
                {name}
              </span>
            );
          })}
        </div>
        {Object.entries(unavailable).map(([name, missing]) => (
          <p key={name} className="marginal mt-1.5">
            {t("workspace.analyses.needsBands", {
              index: name.toUpperCase(),
              bands: missing.join(", "),
            })}
          </p>
        ))}
      </section>
    </div>
  );
}
