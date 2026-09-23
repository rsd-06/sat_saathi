import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";
import { Link } from "@/i18n/navigation";

export default async function SignInPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
}) {
  const { locale } = await params;
  const { next } = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations();

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
      <AuthForm mode="sign-in" locale={locale} next={next} />
    </AuthLayout>
  );
}
