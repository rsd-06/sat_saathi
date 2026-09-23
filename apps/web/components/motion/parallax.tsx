"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { useReducedMotion } from "./use-reduced-motion";

/**
 * Scroll-linked depth, used literally: a map is layers, so the layers move at
 * different rates.
 *
 * Transform only, written on an animation frame, so this never triggers
 * layout. `speed` is a fraction of the scroll distance — 0 is pinned to the
 * page, 0.2 drifts a fifth as far as the scroll. Keep it small; anything past
 * about 0.3 stops reading as depth and starts reading as a bug.
 */
export function Parallax({
  children,
  speed = 0.12,
  className = "",
}: {
  children: ReactNode;
  speed?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node || reduced) return;

    let frame = 0;
    let visible = false;

    const update = () => {
      frame = 0;
      if (!visible) return;
      const rect = node.getBoundingClientRect();
      // Distance from the viewport's centre, so the offset is zero when the
      // element is centred and symmetric either side of it.
      const fromCentre = rect.top + rect.height / 2 - window.innerHeight / 2;
      node.style.transform = `translate3d(0, ${(-fromCentre * speed).toFixed(2)}px, 0)`;
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(update);
    };

    // Only pay for the work while the element is actually on screen.
    const observer = new IntersectionObserver(([entry]) => {
      visible = Boolean(entry?.isIntersecting);
      if (visible) onScroll();
    });
    observer.observe(node);

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();

    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
      node.style.transform = "";
    };
  }, [speed, reduced]);

  return (
    <div ref={ref} className={`will-change-transform ${className}`}>
      {children}
    </div>
  );
}
