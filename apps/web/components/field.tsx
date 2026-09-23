import type { ComponentProps, ReactNode } from "react";

type Props = ComponentProps<"input"> & {
  label: string;
  hint?: ReactNode;
  /** Shown in place of the hint, and marks the input invalid to assistive tech. */
  error?: string | null;
};

export function Field({ label, hint, error, id, ...input }: Props) {
  const messageId = error || hint ? `${id}-message` : undefined;

  return (
    <div>
      <label htmlFor={id} className="text-ink block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={messageId}
        aria-invalid={error ? true : undefined}
        {...input}
        className={`bg-paper-raised text-ink placeholder:text-ink-faint mt-1.5 block w-full rounded-xs border px-3 py-2 text-sm outline-none transition-[border-color,box-shadow] duration-200 ${
          error
            ? "border-alert focus:border-alert"
            : "border-rule-strong focus:border-accent"
        }`}
      />
      {(error || hint) && (
        <p
          id={messageId}
          // Errors announce themselves; a static hint must not.
          role={error ? "alert" : undefined}
          className={`mt-1.5 ${error ? "text-alert text-xs leading-snug" : "marginal"}`}
        >
          {error || hint}
        </p>
      )}
    </div>
  );
}
