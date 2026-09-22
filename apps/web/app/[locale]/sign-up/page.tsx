import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthLayout } from "@/components/auth-layout";
import { Field } from "@/components/field";
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
      <div className="mt-7 space-y-4">
        <Field
          id="name"
          autoComplete="name"
          label={t("auth.field.name")}
          placeholder="—"
        />
        <Field
          id="email"
          type="email"
          autoComplete="email"
          label={t("auth.field.email")}
          hint={t("auth.field.emailHint")}
          placeholder="name@nic.in"
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="department"
            label={t("auth.field.department")}
            placeholder="—"
          />
          <Field
            id="district"
            label={t("auth.field.district")}
            placeholder="—"
          />
        </div>
        <Field
          id="password"
          type="password"
          autoComplete="new-password"
          label={t("auth.field.password")}
          hint={t("auth.field.passwordHint")}
        />

        <div className="pt-1">
          <Link
            href="/dashboard"
            className="bg-accent hover:bg-accent-hover inline-block rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
          >
            {t("auth.action.signUp")}
          </Link>
        </div>
      </div>
    </AuthLayout>
  );
}
