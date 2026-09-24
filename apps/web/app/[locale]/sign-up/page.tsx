import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";
import { GoogleButton } from "@/components/google-button";
import { Link } from "@/i18n/navigation";

export default async function SignUpPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <AuthLayout
      title={t("auth.signUp.title")}
      subtitle={t("auth.signUp.subtitle")}
      sheet="flood"
      footer={
        <>
          {t("auth.switch.toSignIn")}{" "}
          <Link
            href="/sign-in"
            className="text-accent hover:text-accent-hover underline decoration-current/30 underline-offset-4"
          >
            {t("auth.switch.toSignInLink")}
          </Link>
        </>
      }
    >
      <GoogleButton locale={locale} />
      <AuthForm mode="sign-up" locale={locale} />
    </AuthLayout>
  );
}
