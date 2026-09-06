import '@testing-library/jest-dom/vitest';

// jsdom doesn't implement the Pointer Capture API; components that call it
// during a drag (FramingLayer, ToneCurveEditor, ImagePreview) would otherwise
// throw in tests. Real browsers support it on any Element.
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;

// jsdom has no matchMedia; ThemeProvider queries `(prefers-color-scheme: dark)`.
// Default to "light" (matches: false); individual tests can override.
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia;
