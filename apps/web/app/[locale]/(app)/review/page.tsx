import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { ReviewQueue } from "@/components/review-queue";
import { getPublicConfig } from "@/lib/config";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  const config = await getPublicConfig();

  return (
    <PageShell
      title={t("review.title")}
      subtitle={t("answer.review.body", { threshold: config.review_threshold_pct })}
      width="narrow"
    >
      <ReviewQueue />
    </PageShell>
  );
}
