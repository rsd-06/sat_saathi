import { getTranslations, setRequestLocale } from "next-intl/server";

import { DashboardBody } from "@/components/dashboard-body";
import { PageShell } from "@/components/page-shell";
import { Link } from "@/i18n/navigation";
import { currentUser } from "@/lib/session";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  const user = await currentUser();

  return (
    <PageShell
      title={t("dashboard.greeting")}
      subtitle={t("dashboard.subtitle")}
      marginalia={
        user
          ? [
              { label: t("auth.field.name"), value: user.full_name },
              ...(user.department
                ? [{ label: t("auth.field.department"), value: user.department }]
                : []),
              ...(user.district
                ? [{ label: t("auth.field.district"), value: user.district }]
                : []),
            ]
          : undefined
      }
      actions={
        <Link
          href="/workspace"
          className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
        >
          {t("dashboard.newAnalysis")}
        </Link>
      }
    >
      <DashboardBody />
    </PageShell>
  );
}
