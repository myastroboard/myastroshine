import { useMemo, useRef, useState, type PointerEvent } from 'react';

import { DEFAULT_GEOMETRY, type Dimensions, type GeometryParameters } from '@/types';

export interface CropToolProps {
  imageUrl: string;
  /** Original (unrotated) image dimensions. */
  dimensions: Dimensions;
  geometry: GeometryParameters;
  onDone: (geometry: GeometryParameters) => void;
  onCancel: () => void;
}

type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}
interface DragState {
  handle: HandleId | 'move';
  startX: number;
  startY: number;
  rect: Rect;
}

const CORNERS: HandleId[] = ['nw', 'ne', 'se', 'sw'];
const EDGES: HandleId[] = ['n', 'e', 's', 'w'];
const MIN_FRAC = 0.08;

/** Displayed-aspect presets. `null` = free. */
const RATIOS: { label: string; value: number | null }[] = [
  { label: 'Free', value: null },
  { label: 'Original', value: 0 }, // 0 => use the image's own ratio
  { label: '1:1', value: 1 },
  { label: '16:9', value: 16 / 9 },
  { label: '3:2', value: 3 / 2 },
  { label: '4:5', value: 4 / 5 },
  { label: '5:4', value: 5 / 4 },
];

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/** iPhone-style crop / straighten / rotate / flip tool. */
export function CropTool({ imageUrl, dimensions, geometry, onDone, onCancel }: CropToolProps) {
  const [geom, setGeom] = useState<GeometryParameters>(geometry);
  const [ratioFrac, setRatioFrac] = useState<number | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  const odd = geom.rotateQuarters % 2 === 1;
  const baseW = odd ? dimensions.height : dimensions.width;
  const baseH = odd ? dimensions.width : dimensions.height;
  const baseAspect = baseW / baseH;

  const cover = useMemo(() => {
    const rad = (Math.abs(geom.straighten) * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    return Math.max((baseW * c + baseH * s) / baseW, (baseW * s + baseH * c) / baseH);
  }, [geom.straighten, baseW, baseH]);

  const imgBox = odd
    ? { w: `${(baseH / baseW) * 100}%`, h: `${(baseW / baseH) * 100}%` }
    : { w: '100%', h: '100%' };
  const transform =
    `translate(-50%, -50%) scale(${cover}) rotate(${geom.straighten}deg) ` +
    `scaleX(${geom.flipHorizontal ? -1 : 1}) scaleY(${geom.flipVertical ? -1 : 1}) ` +
    `rotate(${geom.rotateQuarters * 90}deg)`;

  function fitRatio(displayRatio: number | null): void {
    setRatioFrac(displayRatio === null ? null : (displayRatio || baseAspect) / baseAspect);
    if (displayRatio === null) {
      return;
    }
    const fr = (displayRatio || baseAspect) / baseAspect;
    let w = fr >= 1 ? 1 : fr;
    let h = w / fr;
    if (h > 1) {
      h = 1;
      w = fr;
    }
    setGeom((g) => ({ ...g, cropX: (1 - w) / 2, cropY: (1 - h) / 2, cropW: w, cropH: h }));
  }

  function beginDrag(handle: HandleId | 'move') {
    return (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = {
        handle,
        startX: event.clientX,
        startY: event.clientY,
        rect: { x: geom.cropX, y: geom.cropY, w: geom.cropW, h: geom.cropH },
      };
    };
  }

  function onDrag(event: PointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    const stage = stageRef.current;
    if (!drag || !stage) {
      return;
    }
    const bounds = stage.getBoundingClientRect();
    const dx = (event.clientX - drag.startX) / bounds.width;
    const dy = (event.clientY - drag.startY) / bounds.height;
    const next = resizeRect(drag.handle, drag.rect, dx, dy, ratioFrac);
    setGeom((g) => ({ ...g, cropX: next.x, cropY: next.y, cropW: next.w, cropH: next.h }));
  }

  function endDrag(): void {
    dragRef.current = null;
  }

  function rotate90(): void {
    setRatioFrac(null);
    setGeom((g) => ({
      ...g,
      rotateQuarters: (g.rotateQuarters + 1) % 4,
      cropX: 0,
      cropY: 0,
      cropW: 1,
      cropH: 1,
    }));
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-canvas/95 backdrop-blur-sm">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-3 sm:px-6">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Cancel
        </button>
        <span className="eyebrow">Crop &amp; rotate</span>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => onDone(geom)}>
          Done
        </button>
      </div>

      <div className="grid flex-1 place-items-center overflow-hidden p-4 sm:p-8">
        <div
          ref={stageRef}
          className="relative max-h-full max-w-full touch-none overflow-hidden bg-black"
          style={{ aspectRatio: baseAspect, height: '100%' }}
          onPointerMove={onDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <img
            src={imageUrl}
            alt="Crop source"
            draggable={false}
            className="pointer-events-none absolute left-1/2 top-1/2"
            style={{ width: imgBox.w, height: imgBox.h, objectFit: 'fill', transform }}
          />

          {/* dark mask outside the crop rect */}
          <div
            className="pointer-events-none absolute shadow-[0_0_0_9999px_rgb(0_0_0/0.6)]"
            style={{
              left: `${geom.cropX * 100}%`,
              top: `${geom.cropY * 100}%`,
              width: `${geom.cropW * 100}%`,
              height: `${geom.cropH * 100}%`,
            }}
          />

          {/* crop frame: draggable body + handles */}
          <div
            className="absolute cursor-move border border-white/80"
            style={{
              left: `${geom.cropX * 100}%`,
              top: `${geom.cropY * 100}%`,
              width: `${geom.cropW * 100}%`,
              height: `${geom.cropH * 100}%`,
            }}
            onPointerDown={beginDrag('move')}
          >
            <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="border border-white/15" />
              ))}
            </div>
            {CORNERS.map((id) => (
              <span
                key={id}
                className={`absolute h-8 w-8 ${cornerHit(id)} ${cornerCursor(id)}`}
                onPointerDown={beginDrag(id)}
              >
                <span className={`absolute h-3.5 w-3.5 border-white ${cornerMark(id)}`} />
              </span>
            ))}
            {ratioFrac === null &&
              EDGES.map((id) => (
                <span
                  key={id}
                  className={`absolute grid place-items-center ${edgeHit(id)}`}
                  onPointerDown={beginDrag(id)}
                >
                  <span className={`bg-white/90 ${edgeBar(id)}`} />
                </span>
              ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 border-t border-hairline px-4 py-4 sm:px-6">
        <label className="flex items-center gap-3 text-xs">
          <span className="w-20 uppercase tracking-wide text-faint">Straighten</span>
          <input
            type="range"
            className="slider flex-1"
            min={-45}
            max={45}
            step={0.1}
            value={geom.straighten}
            aria-label="Straighten"
            onChange={(e) => setGeom((g) => ({ ...g, straighten: Number(e.target.value) }))}
          />
          <span className="w-12 text-right tabular-nums">{geom.straighten.toFixed(1)}&deg;</span>
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-outline btn-sm" onClick={rotate90}>
            Rotate 90&deg;
          </button>
          <button
            type="button"
            className={`btn btn-sm ${geom.flipHorizontal ? 'btn-primary' : 'btn-outline'}`}
            aria-pressed={geom.flipHorizontal}
            onClick={() =>
              setGeom((g) => ({
                ...g,
                flipHorizontal: !g.flipHorizontal,
                cropX: 1 - g.cropX - g.cropW,
              }))
            }
          >
            Flip H
          </button>
          <button
            type="button"
            className={`btn btn-sm ${geom.flipVertical ? 'btn-primary' : 'btn-outline'}`}
            aria-pressed={geom.flipVertical}
            onClick={() =>
              setGeom((g) => ({
                ...g,
                flipVertical: !g.flipVertical,
                cropY: 1 - g.cropY - g.cropH,
              }))
            }
          >
            Flip V
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm ml-auto"
            onClick={() => {
              setGeom(DEFAULT_GEOMETRY);
              setRatioFrac(null);
            }}
          >
            Reset
          </button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {RATIOS.map((r) => {
            const fr = r.value === null ? null : (r.value || baseAspect) / baseAspect;
            const active =
              fr === null
                ? ratioFrac === null
                : ratioFrac !== null && Math.abs(ratioFrac - fr) < 0.001;
            return (
              <button
                key={r.label}
                type="button"
                className={`chip ${active ? 'chip-active' : ''}`}
                aria-pressed={active}
                onClick={() => fitRatio(r.value)}
              >
                {r.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function resizeRect(
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

/** 32px hit area anchored just inside each corner. */
function cornerHit(id: HandleId): string {
  const map: Record<string, string> = {
    nw: 'left-0 top-0',
    ne: 'right-0 top-0',
    se: 'right-0 bottom-0',
    sw: 'left-0 bottom-0',
  };
  return map[id];
}

/** L-shaped marker hugging the actual corner. */
function cornerMark(id: HandleId): string {
  const map: Record<string, string> = {
    nw: 'left-0 top-0 border-l-2 border-t-2',
    ne: 'right-0 top-0 border-r-2 border-t-2',
    se: 'right-0 bottom-0 border-r-2 border-b-2',
    sw: 'left-0 bottom-0 border-l-2 border-b-2',
  };
  return map[id];
}

function cornerCursor(id: HandleId): string {
  return id === 'nw' || id === 'se' ? 'cursor-nwse-resize' : 'cursor-nesw-resize';
}

/** Wide/tall hit area straddling each edge, with a short bar inside. */
function edgeHit(id: HandleId): string {
  const map: Record<string, string> = {
    n: 'left-1/2 top-0 h-5 w-12 -translate-x-1/2 cursor-ns-resize',
    s: 'left-1/2 bottom-0 h-5 w-12 -translate-x-1/2 cursor-ns-resize',
    e: 'top-1/2 right-0 h-12 w-5 -translate-y-1/2 cursor-ew-resize',
    w: 'top-1/2 left-0 h-12 w-5 -translate-y-1/2 cursor-ew-resize',
  };
  return map[id];
}

function edgeBar(id: HandleId): string {
  return id === 'n' || id === 's' ? 'h-1 w-7 rounded-full' : 'h-7 w-1 rounded-full';
}
