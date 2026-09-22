import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the SatSaathi heading", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "SatSaathi" })).toBeDefined();
  });
});
