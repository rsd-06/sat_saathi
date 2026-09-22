import type { ReactNode } from "react";

import "./globals.css";

/** The locale layout owns <html>; this root only carries global styles. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
