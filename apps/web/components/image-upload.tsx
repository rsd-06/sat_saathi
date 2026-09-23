"use client";

import { useRef, useState, type DragEvent } from "react";

import type { AssetOut } from "@/lib/api";
import { useTranslations } from "next-intl";

export type LoadedImage = {
  file: File;
  url: string;
  element: HTMLImageElement | null;
  width: number;
  height: number;
};

const PREVIEWABLE = ["image/png", "image/jpeg", "image/webp", "image/avif"];
const ACCEPT = [...PREVIEWABLE, ".tif", ".tiff"].join(",");

export function ImageUpload({
  loaded,
  asset,
  busy,
  onLoad,
  onClear,
}: {
  loaded: LoadedImage | null;
  asset: AssetOut | null;
  busy: boolean;
  onLoad: (image: LoadedImage) => void;
  onClear: () => void;
}) {
  const t = useTranslations();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept(file: File | undefined) {
    if (!file) return;
    setError(null);

    const isGeotiff = /\.tiff?$/i.test(file.name);
    if (!PREVIEWABLE.includes(file.type) && !isGeotiff) {
      setError(t("upload.error.unsupported"));
      return;
    }

    // A browser cannot decode a GeoTIFF, but the server reads it properly.
    // Upload it anyway and show the metadata instead of a picture.
    if (isGeotiff) {
      onLoad({
        file,
        url: "",
        element: null,
        width: 0,
        height: 0,
      });
      return;
    }

    const url = URL.createObjectURL(file);
    try {
      const element = await new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error("decode-failed"));
        img.src = url;
      });
      onLoad({
        file,
        url,
        element,
        width: element.naturalWidth,
        height: element.naturalHeight,
      });
    } catch {
      URL.revokeObjectURL(url);
      setError(t("upload.error.decode"));
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    void accept(e.dataTransfer.files[0]);
  }

  if (loaded) {
    return (
      <div className="border-rule-strong border">
        <div className="border-rule marginal flex items-center justify-between gap-2 border-b px-2.5 py-1.5">
          <span className="text-ink truncate">{loaded.file.name}</span>
          <button
            type="button"
            onClick={onClear}
            className="text-accent hover:text-accent-hover shrink-0 transition-colors"
          >
            {t("workspace.inputs.remove")}
          </button>
        </div>
        {busy && (
          <p className="marginal border-rule border-b px-2.5 py-1.5">
            {t("workspace.inputs.reading")}…
          </p>
        )}
        {/* Once registered, everything shown comes from the server's own read
            of the file rather than from the browser's guess about it. */}
        <dl className="divide-rule divide-y">
          {[
            [
              t("upload.meta.dimensions"),
              asset
                ? `${asset.width} × ${asset.height} px`
                : `${loaded.width} × ${loaded.height} px`,
            ],
            [t("upload.meta.size"), `${(loaded.file.size / 1024).toFixed(0)} KB`],
            [
              t("workspace.bands.title"),
              asset ? String(asset.band_count) : "—",
            ],
            [
              t("workspace.checks.sensor"),
              asset?.sensor_type ?? "—",
            ],
            [
              t("workspace.checks.crs"),
              asset?.crs ?? t("upload.meta.noCrs"),
            ],
          ].map(([k, v]) => (
            <div
              key={k}
              className="marginal flex items-center justify-between gap-2 px-2.5 py-1.5"
            >
              <dt>{k}</dt>
              <dd className="text-ink tabular truncate">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    );
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border px-3 py-8 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent-wash/50"
            : "border-rule-strong bg-paper-raised"
        }`}
      >
        <p className="marginal">
          {t("workspace.inputs.drop")}{" "}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="text-accent hover:text-accent-hover underline underline-offset-2 transition-colors"
          >
            {t("workspace.inputs.browse")}
          </button>
        </p>
        <p className="marginal mt-1">{t("upload.accepts")}</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => void accept(e.target.files?.[0])}
        />
      </div>
      {error && (
        <p className="border-alert bg-alert-wash/60 text-ink marginal mt-2 border-l-2 px-2.5 py-2">
          {error}
        </p>
      )}
    </div>
  );
}
