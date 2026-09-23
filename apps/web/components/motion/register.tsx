"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useReducedMotion } from "./use-reduced-motion";

/** Reveal once the element's top has risen above this fraction of the viewport. */
const TRIGGER = 0.92;

/**
 * How long a section may stay hidden before it is shown regardless.
 *
 * Nothing should be able to leave content permanently invisible — not a
 * missed frame, not a throttled background tab, not a mistake in this file.
 * It is insurance rather than a timer: long enough that anyone actually
 * reading the page has scrolled and seen the section draw properly, short
 * enough that a broken reveal repairs itself while they are still here.
 */
const FAILSAFE_MS = 30_000;

/**
 * Content arriving the way a plotter draws it: the rule crosses first, then
 * the content resolves behind it.
 *
 * Deliberately not a fade-and-rise. Every section sliding up is the default
 * every site has, and it says nothing about what this one is. A sheet is
 * drawn, so this draws.
 *
 * The trigger is a scroll-linked position check rather than an
 * IntersectionObserver. The observer coalesces callbacks, and under a fast or
 * programmatic scroll it can skip an element entirely — which left one
 * section on the landing page invisible while its neighbours drew correctly.
 * A position read on an animation frame has no such gap, and it is the same
 * mechanism the parallax already uses.
 *
 * It draws once. Re-animating on the way back up is a distraction.
 */
export function Register({
  children,
  delay = 0,
  rule = true,
  className = "",
}: {
  children: ReactNode;
  /** Milliseconds after the element appears. Use sparingly; this is not a queue. */
  delay?: number;
  /** Draw the hairline. Off for content that already sits under one. */
  rule?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || reduced || seen) return;

    let frame = 0;
    let revealTimer = 0;

    const reveal = () => {
      if (revealTimer) return;
      revealTimer = window.setTimeout(() => setSeen(true), delay);
    };

    const check = () => {
      frame = 0;
      if (node.getBoundingClientRect().top < window.innerHeight * TRIGGER) reveal();
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(check);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    // Anything already on screen at mount draws immediately.
    check();

    const failsafe = window.setTimeout(() => setSeen(true), FAILSAFE_MS);

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
      window.clearTimeout(revealTimer);
      window.clearTimeout(failsafe);
    };
  }, [delay, reduced, seen]);

  // Reduced motion means the content is simply there, never mid-draw.
  const drawn = reduced || seen;

  return (
    <div ref={ref} data-drawn={drawn} className={`register ${className}`}>
      {rule && <span aria-hidden className="register-rule" />}
      <div className="register-body">{children}</div>
    </div>
  );
}
