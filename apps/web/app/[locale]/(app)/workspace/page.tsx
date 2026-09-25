import { setRequestLocale } from "next-intl/server";

import { SiteHeader } from "@/components/site-header";
import { Workspace } from "@/components/workspace";
import { getPublicConfig } from "@/lib/config";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const config = await getPublicConfig();

  return (
    <>
      <SiteHeader />
      <main>
        <Workspace
          maxUploadMb={config.max_upload_mb}
          reviewThresholdPct={config.review_threshold_pct}
        />
      </main>
    </>
  );
}
