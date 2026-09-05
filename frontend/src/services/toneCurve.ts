// Tone curve math shared by the ToneCurveEditor's SVG preview. Mirrors
// backend/app/utils/math_utils.py's curve_points_to_lut exactly (same
// monotone cubic Hermite / Fritsch-Carlson spline) so the drawn curve matches
// what the backend actually applies to the image.

import type { CurvePoint } from '@/types';

const MONOTONE_MAGNITUDE_LIMIT = 9;

/** Per-point tangents for a monotone cubic Hermite spline through `points`. */
function fritschCarlsonTangents(points: CurvePoint[]): number[] {
  const n = points.length;
  const deltas: number[] = [];
  for (let i = 0; i < n - 1; i += 1) {
    deltas.push((points[i + 1].y - points[i].y) / (points[i + 1].x - points[i].x));
  }

  const tangents = new Array<number>(n).fill(0);
  tangents[0] = deltas[0];
  tangents[n - 1] = deltas[n - 2];
  for (let i = 1; i < n - 1; i += 1) {
    tangents[i] = (deltas[i - 1] + deltas[i]) / 2;
  }

  for (let i = 0; i < n - 1; i += 1) {
    if (deltas[i] === 0) {
      tangents[i] = 0;
      tangents[i + 1] = 0;
      continue;
    }
    let alpha = Math.max(tangents[i] / deltas[i], 0);
    let beta = Math.max(tangents[i + 1] / deltas[i], 0);
    tangents[i] = alpha * deltas[i];
    tangents[i + 1] = beta * deltas[i];
    const magnitude = alpha * alpha + beta * beta;
    if (magnitude > MONOTONE_MAGNITUDE_LIMIT) {
      const scale = 3 / Math.sqrt(magnitude);
      alpha *= scale;
      beta *= scale;
      tangents[i] = alpha * deltas[i];
      tangents[i + 1] = beta * deltas[i];
    }
  }

  return tangents;
}

/**
 * SVG cubic-Bezier `d` path data tracing the same spline the backend applies,
 * one segment per pair of adjacent points. Hermite-to-Bezier conversion: for
 * a segment from (x0,y0,m0) to (x1,y1,m1), the Bezier control points sit a
 * third of the way along each tangent.
 */
export function curveToSvgPath(points: CurvePoint[]): string {
  if (points.length < 2) {
    return '';
  }
  const tangents = fritschCarlsonTangents(points);
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const { x: x0, y: y0 } = points[i];
    const { x: x1, y: y1 } = points[i + 1];
    const h = x1 - x0;
    const c1x = x0 + h / 3;
    const c1y = y0 + (tangents[i] * h) / 3;
    const c2x = x1 - h / 3;
    const c2y = y1 - (tangents[i + 1] * h) / 3;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${x1} ${y1}`;
  }
  return d;
}
