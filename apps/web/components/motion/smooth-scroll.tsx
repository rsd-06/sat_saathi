"use client";

import { useEffect } from "react";
import Lenis from "lenis";

import { useReducedMotion } from "./use-reduced-motion";

/**
 * Smooth scrolling, with one condition: it is skipped entirely when the
 * person has asked for reduced motion, rather than merely shortened. Taking
 * over the scroll wheel is the most intrusive thing on the page, so it is the
 * first thing that goes.
 *
 * Also skipped on touch, where the platform's own inertia is better than
 * anything reimplemented in JavaScript, and where hijacking it costs a frame
 * budget phones do not have.
 */
export function SmoothScroll() {
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) return;

    const lenis = new Lenis({
      duration: 1.05,
      // Long, shallow ease-out: paper settling, not a spring.
      easing: (t) => 1 - Math.pow(1 - t, 3),
      smoothWheel: true,
      syncTouch: false,
    });

    let frame = 0;
    const raf = (time: number) => {
      lenis.raf(time);
      frame = requestAnimationFrame(raf);
    };
    frame = requestAnimationFrame(raf);

    // A hash link has to keep working; Lenis owns the scroll now.
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as HTMLElement)?.closest?.('a[href^="#"]');
      const href = anchor?.getAttribute("href");
      if (!href || href === "#") return;
      const target = document.querySelector(href);
      if (!target) return;
      event.preventDefault();
      lenis.scrollTo(target as HTMLElement, { offset: -72 });
    };
    document.addEventListener("click", onClick);

    return () => {
      document.removeEventListener("click", onClick);
      cancelAnimationFrame(frame);
      lenis.destroy();
    };
  }, [reduced]);

  return null;
}
