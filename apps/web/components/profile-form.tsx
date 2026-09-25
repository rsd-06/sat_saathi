"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getProfile, updateProfile, type Profile } from "@/lib/api";

const FIELDS = [
  ["full_name", "Full name", "As it should appear on reports"],
  ["designation", "Post / designation", "e.g. District Collector, Hydrologist"],
  ["department", "Department", "e.g. Disaster Management, Agriculture"],
  ["district", "District / area", "The area you usually work on"],
  ["state", "State", "e.g. West Bengal"],
] as const;

type Key = (typeof FIELDS)[number][0];

/** The signed-in officer's own details, saved to their account. */
export function ProfileForm() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [draft, setDraft] = useState<Record<Key, string>>({
    full_name: "",
    designation: "",
    department: "",
    district: "",
    state: "",
  });
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "failed">("idle");

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p);
        setDraft({
          full_name: p.full_name,
          designation: p.designation ?? "",
          department: p.department ?? "",
          district: p.district ?? "",
          state: p.state ?? "",
        });
      })
      .catch(() => setStatus("failed"));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setStatus("saving");
    try {
      setProfile(await updateProfile(draft));
      setStatus("saved");
      // The header reads the account on the server; refresh so it shows the change.
      router.refresh();
    } catch {
      setStatus("failed");
    }
  }

  return (
    <section id="profile" className="scroll-mt-24">
      <h2 className="font-serif text-ink text-2xl tracking-tight">Profile</h2>
      <p className="text-ink-muted mt-1 text-base">
        {profile ? profile.email : "Loading your account…"}
        {profile && (
          <span className="text-ink-faint">
            {" "}
            · member since {new Date(profile.created_at).toLocaleDateString()}
          </span>
        )}
      </p>

      <form onSubmit={save} className="mt-4 grid gap-4 sm:grid-cols-2">
        {FIELDS.map(([key, label, hint]) => (
          <label key={key} className={key === "full_name" ? "sm:col-span-2" : ""}>
            <span className="text-ink block text-base font-medium">{label}</span>
            <input
              value={draft[key]}
              required={key === "full_name"}
              maxLength={key === "state" ? 100 : 200}
              placeholder={hint}
              onChange={(e) => {
                setDraft({ ...draft, [key]: e.target.value });
                setStatus("idle");
              }}
              className="border-rule-strong bg-paper-raised text-ink placeholder:text-ink-faint focus:border-accent mt-1.5 block w-full rounded-xs border px-3 py-2.5 text-base outline-none transition-colors"
            />
          </label>
        ))}
        <div className="flex items-center gap-4 sm:col-span-2">
          <button
            type="submit"
            disabled={!profile || status === "saving"}
            className="bg-accent hover:bg-accent-hover rounded-xs px-6 py-2.5 text-base font-medium text-white transition-colors disabled:opacity-50"
          >
            {status === "saving" ? "Saving…" : "Save profile"}
          </button>
          <span className="text-base" role="status">
            {status === "saved" && <span className="text-vegetation">Saved.</span>}
            {status === "failed" && (
              <span className="text-alert">Could not reach the server. Try again.</span>
            )}
          </span>
        </div>
      </form>
    </section>
  );
}
