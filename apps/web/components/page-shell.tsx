import type { ReactNode } from "react";

import { SiteHeader } from "./site-header";

/**
 * The frame every working page sits in.
 *
 * A sheet carries its identity in the top margin, so each page states what it
 * is and what it is of, above a rule, in the same place every time. Repeating
 * one structure is what makes five screens read as one instrument rather than
 * five pages that happen to share a palette.
 *
 * `actions` is the page's own primary action, on the same line as its title,
 * because on every one of these screens there is exactly one obvious next
 * thing to do.
 */
export function PageShell({
  title,
  subtitle,
  actions,
  marginalia,
  children,
  width = "wide",
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** Labelled facts about this page, along the top edge. */
  marginalia?: { label: string; value: ReactNode }[];
  children: ReactNode;
  width?: "wide" | "narrow";
}) {
  const max = width === "narrow" ? "max-w-[56rem]" : "max-w-[88rem]";

  return (
    <>
      <SiteHeader />
      <main className={`mx-auto ${max} px-4 py-8 sm:px-6 sm:py-10`}>
        <header className="border-rule-strong border-b pb-5">
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              <h1 className="font-serif text-ink text-3xl leading-tight tracking-tight">
                {title}
              </h1>
              {subtitle && (
                <p className="text-ink-muted mt-2 max-w-prose text-sm leading-relaxed">
                  {subtitle}
                </p>
              )}
            </div>
            {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
          </div>

          {marginalia && marginalia.length > 0 && (
            <dl className="divide-rule border-rule mt-5 grid grid-cols-2 border-t sm:flex sm:divide-x">
              {marginalia.map((item) => (
                <div key={item.label} className="py-2 sm:pr-6 sm:pl-6 sm:first:pl-0">
                  <dt className="marginal">{item.label}</dt>
                  <dd className="text-ink tabular mt-0.5 text-sm">{item.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </header>

        <div className="mt-8">{children}</div>
      </main>
    </>
  );
}
