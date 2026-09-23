import { getTranslations, setRequestLocale } from "next-intl/server";

import { SettingsPanel } from "@/components/settings-panel";
import { SiteHeader } from "@/components/site-header";

export default async function SettingsPage({
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
      <main className="mx-auto max-w-[40rem] px-4 py-10 sm:px-6">
        <h1 className="font-serif text-ink text-3xl tracking-tight">
          {t("settings.title")}
        </h1>
        <div className="mt-8">
          <SettingsPanel />
        </div>
      </main>
    </>
  );
}
