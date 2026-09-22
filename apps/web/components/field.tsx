import type { ComponentProps, ReactNode } from "react";

type Props = ComponentProps<"input"> & {
  label: string;
  hint?: ReactNode;
};

export function Field({ label, hint, id, ...input }: Props) {
  const hintId = hint ? `${id}-hint` : undefined;

  return (
    <div>
      <label htmlFor={id} className="text-ink block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={hintId}
        {...input}
        className="border-rule-strong bg-paper-raised text-ink placeholder:text-ink-faint focus:border-accent mt-1.5 block w-full rounded-xs border px-3 py-2 text-sm transition-colors outline-none"
      />
      {hint && (
        <p id={hintId} className="marginal mt-1.5">
          {hint}
        </p>
      )}
    </div>
  );
}
