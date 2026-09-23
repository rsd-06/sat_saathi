"use client";

import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { Field } from "./field";

const MIN_PASSWORD = 12;

type Mode = "sign-in" | "sign-up";

type Errors = Partial<Record<"email" | "password" | "full_name" | "form", string>>;

/**
 * The one form behind both auth screens.
 *
 * Validation happens here before anything is sent, so a missing field is
 * answered instantly rather than after a round trip, and again on the server,
 * which is the only check that counts. Field errors sit under their field;
 * only a failure that belongs to no single field goes to the top.
 */
export function AuthForm({
  mode,
  locale,
  next,
}: {
  mode: Mode;
  locale: string;
  next?: string;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [navigating, startNavigating] = useTransition();

  const busy = submitting || navigating;
  const signingUp = mode === "sign-up";

  function validate(data: FormData): Errors {
    const found: Errors = {};
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");

    // Deliberately loose: an address is valid if a mail server says so, and
    // no regular expression is a better judge than that.
    if (!email.includes("@") || email.startsWith("@") || email.endsWith("@")) {
      found.email = t("auth.error.emailInvalid");
    }
    if (signingUp) {
      if (!String(data.get("full_name") ?? "").trim()) {
        found.full_name = t("auth.error.nameRequired");
      }
      if (password.length < MIN_PASSWORD) {
        found.password = t("auth.error.passwordShort", { min: MIN_PASSWORD });
      }
    } else if (!password) {
      found.password = t("auth.error.passwordShort", { min: MIN_PASSWORD });
    }
    return found;
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);

    const found = validate(data);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      // Focus by field order, not by querying for [aria-invalid]: React has
      // not re-rendered yet, so that attribute is not on the page to find.
      const first = (["full_name", "email", "password"] as const).find(
        (name) => found[name],
      );
      if (first) form.querySelector<HTMLInputElement>(`#${first}`)?.focus();
      return;
    }

    setSubmitting(true);
    const body: Record<string, unknown> = {
      email: String(data.get("email") ?? "").trim(),
      password: String(data.get("password") ?? ""),
    };
    if (signingUp) {
      body.full_name = String(data.get("full_name") ?? "").trim();
      body.department = String(data.get("department") ?? "").trim() || null;
      body.district = String(data.get("district") ?? "").trim() || null;
      body.preferred_locale = String(data.get("preferred_locale") ?? locale);
    }

    try {
      const response = await fetch(`/api/auth/${signingUp ? "register" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const key: string = payload?.error?.key ?? "http.error";
        // A taken address is about the email box; everything else is not.
        setErrors(
          key === "auth.error.emailTaken"
            ? { email: t(key) }
            : { form: safeMessage(t, key, response.status) },
        );
        setSubmitting(false);
        return;
      }

      const target = next && next.startsWith("/") ? next : `/${locale}/dashboard`;
      startNavigating(() => {
        router.replace(target);
        router.refresh();
      });
    } catch {
      setErrors({ form: t("error.apiUnreachable.title") });
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="mt-7 space-y-4">
      {errors.form && (
        <p
          role="alert"
          className="border-alert bg-alert-wash/60 text-ink rounded-xs border-l-2 px-3 py-2 text-sm leading-snug"
        >
          {errors.form}
        </p>
      )}

      {signingUp && (
        <Field
          id="full_name"
          name="full_name"
          autoComplete="name"
          label={t("auth.field.name")}
          error={errors.full_name}
          disabled={busy}
        />
      )}

      <Field
        id="email"
        name="email"
        type="email"
        autoComplete="email"
        label={t("auth.field.email")}
        hint={t("auth.field.emailHint")}
        error={errors.email}
        placeholder="name@nic.in"
        disabled={busy}
      />

      {signingUp && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="department"
              name="department"
              label={t("auth.field.department")}
              hint={t("auth.field.departmentHint")}
              disabled={busy}
            />
            <Field
              id="district"
              name="district"
              label={t("auth.field.district")}
              disabled={busy}
            />
          </div>
          <LocaleChoice locale={locale} disabled={busy} label={t("auth.signUp.localeLabel")} />
        </>
      )}

      <Field
        id="password"
        name="password"
        type="password"
        autoComplete={signingUp ? "new-password" : "current-password"}
        label={t("auth.field.password")}
        hint={signingUp ? t("auth.field.passwordHint") : undefined}
        error={errors.password}
        disabled={busy}
      />

      <div className="flex items-center justify-between gap-4 pt-1">
        <button
          type="submit"
          disabled={busy}
          className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-60"
        >
          {busy
            ? t(signingUp ? "auth.action.creating" : "auth.action.signingIn")
            : t(signingUp ? "auth.action.signUp" : "auth.action.signIn")}
        </button>
        {!signingUp && (
          <span className="text-ink-faint text-sm">{t("auth.action.forgot")}</span>
        )}
      </div>
    </form>
  );
}

function LocaleChoice({
  locale,
  label,
  disabled,
}: {
  locale: string;
  label: string;
  disabled: boolean;
}) {
  const names: Record<string, string> = {
    en: "English",
    hi: "हिन्दी",
    ta: "தமிழ்",
    bn: "বাংলা",
  };
  return (
    <div>
      <label htmlFor="preferred_locale" className="text-ink block text-sm font-medium">
        {label}
      </label>
      <select
        id="preferred_locale"
        name="preferred_locale"
        defaultValue={locale}
        disabled={disabled}
        className="border-rule-strong bg-paper-raised text-ink focus:border-accent mt-1.5 block w-full rounded-xs border px-3 py-2 text-sm outline-none transition-colors"
      >
        {Object.entries(names).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Show the API's own message when we have a translation for it, and a generic
 * one otherwise. A raw key on screen is worse than a vague sentence.
 */
function safeMessage(
  t: ReturnType<typeof useTranslations>,
  key: string,
  status: number,
): string {
  try {
    const message = t(key as never);
    return message === key ? t("http.error", { status }) : message;
  } catch {
    return t("http.error", { status });
  }
}
