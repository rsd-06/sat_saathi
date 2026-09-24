import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { SettingsPanel } from "@/components/settings-panel";

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <PageShell title={t("settings.title")} width="narrow">
      <SettingsPanel />
    </PageShell>
  );
}
