import { getTranslations, setRequestLocale } from "next-intl/server";

import { DashboardBody } from "@/components/dashboard-body";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/site-header";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-[88rem] px-4 py-10 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-ink text-3xl tracking-tight">
              {t("dashboard.greeting")}
            </h1>
            <p className="text-ink-muted mt-2 text-sm">
              {t("dashboard.subtitle")}
            </p>
          </div>
          <Link
            href="/workspace"
            className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
          >
            {t("dashboard.newAnalysis")}
          </Link>
        </div>
        <DashboardBody />
      </main>
    </>
  );
}
