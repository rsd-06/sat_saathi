"use client";

import { useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";

import type { AssetOut } from "@/lib/api";
import { TIFF_EXTENSIONS, hasTiffExtension, looksLikeTiff } from "@/lib/tiff";

export type LoadedImage = {
  file: File;
  url: string;
  element: HTMLImageElement | null;
  width: number;
  height: number;
};

const ACCEPT = [...TIFF_EXTENSIONS, "image/tiff"].join(",");

export function ImageUpload({
  loaded,
  asset,
  busy,
  progress,
  maxMb,
  onLoad,
  onClear,
}: {
  loaded: LoadedImage | null;
  asset: AssetOut | null;
  busy: boolean;
  /** 0–100 while bytes are in flight, null once the server is reading. */
  progress?: number | null;
  /** The server's limit, checked here so an oversized file is refused before
   *  it has gone up the wire rather than after. */
  maxMb: number;
  onLoad: (image: LoadedImage) => void;
  onClear: () => void;
}) {
  const t = useTranslations();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openPicker() {
    inputRef.current?.click();
  }

  async function accept(file: File | undefined) {
    // Reset the input first. Without this, choosing the same file again after
    // an error fires no change event and the picker silently does nothing.
    if (inputRef.current) inputRef.current.value = "";

    if (!file) return;
    setError(null);

    if (file.size === 0) {
      setError(t("upload.error.empty"));
      return;
    }
    const megabytes = file.size / (1024 * 1024);
    if (megabytes > maxMb) {
      setError(
        t("upload.error.tooLarge", { size: megabytes.toFixed(0), max: maxMb }),
      );
      return;
    }

    // GeoTIFF only. Anything else is refused here, before a byte is sent, and
    // again on the server, which is the check that actually counts.
    if (!hasTiffExtension(file.name)) {
      setError(t("upload.error.unsupported"));
      return;
    }
    // A JPEG renamed to scene.tif has the right extension and the wrong bytes.
    if (!(await looksLikeTiff(file))) {
      setError(t("upload.error.notTiff"));
      return;
    }

    // A browser cannot decode a TIFF, so there is no preview: the server
    // reads the file and the metadata it reports stands in for a picture.
    onLoad({ file, url: "", element: null, width: 0, height: 0 });
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void accept(event.dataTransfer.files[0]);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  }

  if (loaded) {
    const uploading = progress !== null && progress !== undefined;
    return (
      <div className="border-rule-strong bg-paper-raised border">
        <div className="border-rule marginal flex items-center justify-between gap-2 border-b px-2.5 py-1.5">
          <span className="text-ink truncate">{loaded.file.name}</span>
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="text-accent hover:text-accent-hover shrink-0 transition-colors disabled:opacity-50"
          >
            {t("workspace.inputs.remove")}
          </button>
        </div>

        {busy && (
          <div className="border-rule border-b px-2.5 py-1.5">
            <p className="marginal">
              {uploading
                ? t("upload.progress", { percent: Math.round(progress) })
                : `${t("workspace.inputs.reading")}…`}
            </p>
            {/* A determinate bar while bytes move, indeterminate once the
                server has them and is reading headers. */}
            <div className="bg-paper-sunk mt-1.5 h-0.5 w-full overflow-hidden">
              <div
                className={`bg-accent h-full transition-[width] duration-200 ${
                  uploading ? "" : "w-1/3 animate-pulse"
                }`}
                style={uploading ? { width: `${progress}%` } : undefined}
              />
            </div>
          </div>
        )}

        {/* Once registered, everything shown comes from the server's own read
            of the file rather than from the browser's guess about it. */}
        <dl className="divide-rule divide-y">
          {[
            [
              t("upload.meta.dimensions"),
              asset ? `${asset.width} × ${asset.height} px` : "—",
            ],
            [t("upload.meta.size"), `${(loaded.file.size / 1024).toFixed(0)} KB`],
            [t("workspace.bands.title"), asset ? String(asset.band_count) : "—"],
            [t("workspace.checks.sensor"), asset?.sensor_type ?? "—"],
            [t("workspace.checks.crs"), asset?.crs ?? t("upload.meta.noCrs")],
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
      {/* The input is a sibling of the drop zone, never a child of it.
          Inside, the synthetic click from `openPicker` bubbles straight back
          into the zone's own onClick, which calls it again — and the browser
          suppresses the file dialog rather than recursing. That looks exactly
          like a picker that refuses to open. */}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => void accept(e.target.files?.[0])}
      />

      {/* The whole area takes a drop, a click and the keyboard. A target this
          large that only responded to one small link inside it would be a
          worse target than a plain button. */}
      <div
        role="button"
        tabIndex={0}
        onClick={openPicker}
        onKeyDown={onKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        aria-describedby="upload-accepts"
        className={`cursor-pointer border px-3 py-10 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent-wash/50"
            : "border-rule-strong bg-paper-raised hover:border-accent/60"
        }`}
      >
        <p className="marginal">
          {t("workspace.inputs.drop")}{" "}
          <span className="text-accent underline underline-offset-2">
            {t("workspace.inputs.browse")}
          </span>
        </p>
        <p id="upload-accepts" className="marginal mt-1">
          {t("upload.accepts", { max: maxMb })}
        </p>
      </div>
      {error && (
        <p
          role="alert"
          className="border-alert bg-alert-wash/60 text-ink marginal mt-2 border-l-2 px-2.5 py-2"
        >
          {error}
        </p>
      )}
    </div>
  );
}
