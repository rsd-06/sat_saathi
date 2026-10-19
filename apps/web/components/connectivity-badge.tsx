import { getTranslations } from "next-intl/server";

/**
 * Reads the API's reported mode. Until the API client lands this reflects the
 * build-time default; it is deliberately not a live ping from the browser.
 */
export async function ConnectivityBadge() {
  const t = await getTranslations();
  const online = process.env.NEXT_PUBLIC_SATSAATHI_MODE !== "offline";

  return (
    <span
      className="marginal flex items-center gap-1.5"
      title={online ? t("status.onlineHint") : t("status.offlineHint")}
    >
      <span
        aria-hidden
        className={`size-1.5 rounded-full ${
          online ? "bg-vegetation" : "bg-relief"
        }`}
      />
      <span className="sr-only sm:not-sr-only">
        {online ? t("status.online") : t("status.offline")}
      </span>
    </span>
  );
}
