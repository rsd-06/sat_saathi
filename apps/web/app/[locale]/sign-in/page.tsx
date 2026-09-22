import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthLayout } from "@/components/auth-layout";
import { Field } from "@/components/field";
import { Link } from "@/i18n/navigation";

export default async function SignInPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <AuthLayout
      title={t("auth.signIn.title")}
      subtitle={t("auth.signIn.subtitle")}
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
      {/* No auth backend yet: this is a link, not a submit. */}
      <div className="mt-7 space-y-4">
        <Field
          id="email"
          type="email"
          autoComplete="email"
          label={t("auth.field.email")}
          hint={t("auth.field.emailHint")}
          placeholder="name@nic.in"
        />
        <Field
          id="password"
          type="password"
          autoComplete="current-password"
          label={t("auth.field.password")}
        />

        <div className="flex items-center justify-between pt-1">
          <Link
            href="/dashboard"
            className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
          >
            {t("auth.action.signIn")}
          </Link>
          <span className="text-ink-faint text-sm">
            {t("auth.action.forgot")}
          </span>
        </div>
      </div>
    </AuthLayout>
  );
}
