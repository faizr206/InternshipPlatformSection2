import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { resetMockState } from "@/mocks/handlers";

// jsdom gaps that Radix primitives rely on.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}
// Chrome now returns a Promise here; mimic it so effects that leak the value fail in tests.
Element.prototype.scrollIntoView = (() => Promise.resolve()) as unknown as Element["scrollIntoView"];
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

beforeEach(() => {
  localStorage.clear();
  resetMockState();
});
afterEach(() => cleanup());
