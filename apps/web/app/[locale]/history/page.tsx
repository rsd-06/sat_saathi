import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryList } from "@/components/history-list";
import { SiteHeader } from "@/components/site-header";

export default async function HistoryPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <>
      <SiteHeader signedIn />
      <main className="mx-auto max-w-[88rem] px-4 py-10 sm:px-6">
        <h1 className="font-serif text-ink text-3xl tracking-tight">
          {t("history.title")}
        </h1>
        <div className="mt-6">
          <HistoryList />
        </div>
      </main>
    </>
  );
}
