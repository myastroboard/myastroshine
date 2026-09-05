import '@testing-library/jest-dom/vitest';

// jsdom doesn't implement the Pointer Capture API; components that call it
// during a drag (FramingLayer, ToneCurveEditor, ImagePreview) would otherwise
// throw in tests. Real browsers support it on any Element.
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
