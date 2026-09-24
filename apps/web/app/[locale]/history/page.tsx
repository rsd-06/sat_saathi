import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryList } from "@/components/history-list";
import { PageShell } from "@/components/page-shell";
import { Link } from "@/i18n/navigation";

export default async function HistoryPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <PageShell
      title={t("history.title")}
      actions={
        <Link
          href="/workspace"
          className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
        >
          {t("dashboard.newAnalysis")}
        </Link>
      }
    >
      <HistoryList />
    </PageShell>
  );
}
