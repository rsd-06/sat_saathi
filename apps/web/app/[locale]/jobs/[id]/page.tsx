import { setRequestLocale } from "next-intl/server";

import { JobView } from "@/components/job-view";
import { SiteHeader } from "@/components/site-header";

export default async function JobPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <>
      <SiteHeader signedIn />
      <main className="mx-auto max-w-[70rem] px-4 py-8 sm:px-6">
        <JobView jobId={id} />
      </main>
    </>
  );
}
