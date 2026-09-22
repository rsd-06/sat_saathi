import type { StepStatus } from "@/lib/mock";

const TONE: Record<string, string> = {
  succeeded: "bg-vegetation",
  running: "bg-accent",
  pending: "bg-rule-strong",
  skipped: "bg-rule-strong",
  failed: "bg-alert",
  needs_review: "bg-relief",
};

export function StatusDot({
  status,
  className = "",
}: {
  status: StepStatus | string;
  className?: string;
}) {
  const running = status === "running";
  return (
    <span
      aria-hidden
      className={`relative inline-flex size-1.5 shrink-0 rounded-full ${
        TONE[status] ?? "bg-rule-strong"
      } ${className}`}
    >
      {running && (
        <span className="bg-accent absolute inset-0 animate-ping rounded-full opacity-60" />
      )}
    </span>
  );
}
