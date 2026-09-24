import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";
import { GoogleButton } from "@/components/google-button";
import { Link } from "@/i18n/navigation";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";

/** Callback failures arrive as a short code in the URL, mapped to a key here. */
const OAUTH_ERRORS: Record<string, string> = {
  cancelled: "auth.error.googleCancelled",
  state_mismatch: "auth.error.googleState",
  unverified_email: "auth.error.googleUnverifiedEmail",
  google_unavailable: "auth.error.googleDisabled",
  google_failed: "auth.error.googleFailed",
  api_unreachable: "error.apiUnreachable.title",
  session_expired: "auth.error.sessionExpired",
};

export default async function SignInPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { locale } = await params;
  const { next, error } = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations();

  // Asked of the API, not inferred from a cookie. A dead cookie leaves
  // the form reachable; the next sign-in simply replaces it.
  if ((await getSession()).state === "signed-in") {
    redirect(`/${locale}/dashboard`);
  }

  const errorKey = error ? OAUTH_ERRORS[error] : undefined;

  return (
    <AuthLayout
      title={t("auth.signIn.title")}
      subtitle={t("auth.signIn.subtitle")}
      sheet="sar"
      footer={
        <>
          {t("auth.switch.toSignUp")}{" "}
          <Link
            href="/sign-up"
            className="text-accent hover:text-accent-hover underline decoration-current/30 underline-offset-4"
          >
            {t("auth.switch.toSignUpLink")}
          </Link>
        </>
      }
    >
      {errorKey && (
        <p
          role="alert"
          className="border-alert bg-alert-wash/60 text-ink mt-6 rounded-xs border-l-2 px-3 py-2 text-sm leading-snug"
        >
          {t(errorKey)}
        </p>
      )}
      <GoogleButton locale={locale} next={next} />
      <AuthForm mode="sign-in" locale={locale} next={next} />
    </AuthLayout>
  );
}
