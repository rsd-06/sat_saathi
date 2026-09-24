import { getTranslations } from "next-intl/server";

/**
 * The way in through Google.
 *
 * A plain link rather than a button with a click handler: starting an OAuth
 * flow is a navigation, and a navigation should work before any JavaScript
 * has run. It is hidden entirely when the server has no credentials
 * configured, because offering a door that cannot open is worse than not
 * offering it.
 */
export async function GoogleButton({
  locale,
  next,
}: {
  locale: string;
  next?: string;
}) {
  const t = await getTranslations();
  const configured = Boolean(
    process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET,
  );
  if (!configured) return null;

  const href = `/api/auth/google/start?locale=${encodeURIComponent(locale)}${
    next ? `&next=${encodeURIComponent(next)}` : ""
  }`;

  return (
    <div className="mt-7">
      <a
        href={href}
        className="border-rule-strong bg-paper-raised text-ink hover:border-accent flex w-full items-center justify-center gap-3 rounded-xs border px-4 py-2.5 text-sm font-medium transition-colors"
      >
        <GoogleMark />
        {t("auth.google.continue")}
      </a>

      <div className="mt-6 flex items-center gap-3" aria-hidden>
        <span className="bg-rule h-px flex-1" />
        <span className="marginal">{t("auth.google.or")}</span>
        <span className="bg-rule h-px flex-1" />
      </div>
    </div>
  );
}

/** Google's mark, at its official colours. */
function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden className="shrink-0">
      <path
        fill="#4285F4"
        d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z"
      />
      <path
        fill="#34A853"
        d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z"
      />
      <path
        fill="#FBBC05"
        d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34A21.99 21.99 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z"
      />
      <path
        fill="#EA4335"
        d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z"
      />
    </svg>
  );
}
