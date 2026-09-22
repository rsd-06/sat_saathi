import { setRequestLocale } from "next-intl/server";

import { SiteHeader } from "@/components/site-header";
import { Workspace } from "@/components/workspace";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <>
      <SiteHeader signedIn />
      <main>
        <Workspace />
      </main>
    </>
  );
}
