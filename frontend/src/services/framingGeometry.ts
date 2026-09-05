// Pure geometry helpers for the framing (crop / straighten / rotate / flip)
// tool. Kept free of React so both the on-image handle layer (`FramingLayer`)
// and the inspector panel (`FramingControls`) can share the same maths.

import type { Dimensions } from '@/types';

export type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const CORNERS: HandleId[] = ['nw', 'ne', 'se', 'sw'];
export const EDGES: HandleId[] = ['n', 'e', 's', 'w'];

/** Smallest crop rectangle, as a fraction of the framed image. */
export const MIN_FRAC = 0.08;

export function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/** Aspect ratio (w/h) of the image after its 90deg turns, before cropping. */
export function baseAspectRatio(dimensions: Dimensions, rotateQuarters: number): number {
  const odd = rotateQuarters % 2 === 1;
  const w = odd ? dimensions.height : dimensions.width;
  const h = odd ? dimensions.width : dimensions.height;
  return w / h;
}

/**
 * Scale factor that keeps a straightened image covering the frame with no empty
 * corners. `baseW`/`baseH` are the post-quarter-turn pixel dimensions.
 */
export function coverScale(straightenDeg: number, baseW: number, baseH: number): number {
  const rad = (Math.abs(straightenDeg) * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  return Math.max((baseW * c + baseH * s) / baseW, (baseW * s + baseH * c) / baseH);
}

/** Displayed-aspect crop presets. `null` = free, `0` = the image's own ratio. */
export const RATIOS: { label: string; translationKey?: string; value: number | null }[] = [
  { label: 'Free', translationKey: 'crop_tool.free', value: null },
  { label: 'Original', translationKey: 'crop_tool.original', value: 0 },
  { label: '1:1', value: 1 },
  { label: '16:9', value: 16 / 9 },
  { label: '3:2', value: 3 / 2 },
  { label: '4:5', value: 4 / 5 },
  { label: '5:4', value: 5 / 4 },
];

/**
 * The crop rectangle (and the ratio fraction to lock resize to) for a chosen
 * displayed aspect ratio. `displayRatio === null` clears the lock and leaves the
 * rectangle alone.
 */
export function rectForRatio(
  displayRatio: number | null,
  baseAspect: number,
): { ratioFrac: number | null; rect: Rect | null } {
  if (displayRatio === null) {
    return { ratioFrac: null, rect: null };
  }
  const ratioFrac = (displayRatio || baseAspect) / baseAspect;
  let w = ratioFrac >= 1 ? 1 : ratioFrac;
  let h = w / ratioFrac;
  if (h > 1) {
    h = 1;
    w = ratioFrac;
  }
  return { ratioFrac, rect: { x: (1 - w) / 2, y: (1 - h) / 2, w, h } };
}

/** Resize (or move) a crop rectangle from a handle drag, in frame fractions. */
export function resizeRect(
  handle: HandleId | 'move',
  start: Rect,
  dx: number,
  dy: number,
  ratioFrac: number | null,
): Rect {
  if (handle === 'move') {
    return {
      ...start,
      x: clamp(start.x + dx, 0, 1 - start.w),
      y: clamp(start.y + dy, 0, 1 - start.h),
    };
  }

  let { x, y, w, h } = start;
  const east = handle.includes('e');
  const west = handle.includes('w');
  const north = handle.includes('n');
  const south = handle.includes('s');

  if (east) {
    w = clamp(start.w + dx, MIN_FRAC, 1 - start.x);
  }
  if (west) {
    const nx = clamp(start.x + dx, 0, start.x + start.w - MIN_FRAC);
    w = start.x + start.w - nx;
    x = nx;
  }
  if (south) {
    h = clamp(start.h + dy, MIN_FRAC, 1 - start.y);
  }
  if (north) {
    const ny = clamp(start.y + dy, 0, start.y + start.h - MIN_FRAC);
    h = start.y + start.h - ny;
    y = ny;
  }

  if (ratioFrac !== null && (east || west) && (north || south)) {
    // corner drag with a locked ratio: derive height from the new width
    const targetH = w / ratioFrac;
    if (north) {
      y = start.y + start.h - targetH;
    }
    h = targetH;
    if (y < 0 || y + h > 1) {
      const capped = clamp(h, MIN_FRAC, north ? start.y + start.h : 1 - start.y);
      w = capped * ratioFrac;
      h = capped;
      if (north) {
        y = start.y + start.h - h;
      }
      if (west) {
        x = start.x + start.w - w;
      }
    }
  }

  return { x, y, w, h };
}
