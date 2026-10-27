import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollTo; several components call it on mount.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {};
}
