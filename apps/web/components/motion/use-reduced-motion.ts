"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/**
 * Whether the person has asked for less movement.
 *
 * Read during render rather than in an effect, so a component can start in
 * its final state instead of animating once and then correcting itself. On
 * the server it answers false, which matches the CSS: the stylesheet disables
 * the animations anyway, so the first client render agrees with the markup.
 *
 * It also tracks changes, because this is a setting people turn on mid-session
 * precisely when something on screen is bothering them.
 */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}
