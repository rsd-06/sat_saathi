import { getTranslations, setRequestLocale } from "next-intl/server";

import { ReviewQueue } from "@/components/review-queue";
import { SiteHeader } from "@/components/site-header";

export default async function ReviewPage({
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
      <main className="mx-auto max-w-[60rem] px-4 py-10 sm:px-6">
        <h1 className="font-serif text-ink text-3xl tracking-tight">
          {t("review.title")}
        </h1>
        <p className="text-ink-muted mt-2 text-sm">
          {t("answer.review.body", { threshold: 75 })}
        </p>
        <div className="mt-6">
          <ReviewQueue />
        </div>
      </main>
    </>
  );
}
