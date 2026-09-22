import type { ReactNode } from "react";

type Props = {
  /** Marginal information, in reading order along the top edge of the sheet. */
  margin?: ReactNode[];
  /** Runs along the bottom edge, where a sheet carries its scale and legend. */
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
};

/**
 * A drawn sheet: the image sits inside a ruled frame, and everything known
 * about it lives in the margin rather than in a separate card. This is the
 * one structural idea the whole interface is built from.
 */
export function Sheet({ margin, footer, children, className = "" }: Props) {
  return (
    <figure className={`border-rule-strong bg-paper-raised border ${className}`}>
      {margin && margin.length > 0 && (
        <div className="border-rule divide-rule flex flex-wrap items-center divide-x border-b">
          {margin.map((item, i) => (
            <div key={i} className="marginal px-2.5 py-1.5">
              {item}
            </div>
          ))}
        </div>
      )}
      <div className="relative">{children}</div>
      {footer && (
        <figcaption className="border-rule border-t px-2.5 py-1.5">
          {footer}
        </figcaption>
      )}
    </figure>
  );
}
