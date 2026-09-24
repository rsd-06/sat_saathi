import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { ReviewQueue } from "@/components/review-queue";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <PageShell
      title={t("review.title")}
      subtitle={t("answer.review.body", { threshold: 75 })}
      width="narrow"
    >
      <ReviewQueue />
    </PageShell>
  );
}
