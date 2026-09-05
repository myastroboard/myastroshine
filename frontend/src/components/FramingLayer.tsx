import { useMemo, useRef, type PointerEvent } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import {
  CORNERS,
  EDGES,
  coverScale,
  resizeRect,
  type HandleId,
  type Rect,
} from '@/services/framingGeometry';
import type { Dimensions, GeometryParameters } from '@/types';

export interface FramingLayerProps {
  imageUrl: string;
  /** Original (unrotated) image dimensions. */
  dimensions: Dimensions;
  geometry: GeometryParameters;
  /** Non-null locks corner resizes to this width/height fraction ratio. */
  ratioFrac: number | null;
  onGeometryChange: (next: GeometryParameters) => void;
}

interface DragState {
  handle: HandleId | 'move';
  startX: number;
  startY: number;
  rect: Rect;
}

/**
 * The crop frame + handles drawn over the main preview while the Framing step
 * is active. The straighten / flip / quarter-turn transform matches
 * `FramingControls`; geometry changes are pushed straight up to the editor.
 */
export function FramingLayer({
  imageUrl,
  dimensions,
  geometry,
  ratioFrac,
  onGeometryChange,
}: FramingLayerProps) {
  const { t } = useTranslation();
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  const odd = geometry.rotateQuarters % 2 === 1;
  const baseW = odd ? dimensions.height : dimensions.width;
  const baseH = odd ? dimensions.width : dimensions.height;

  const cover = useMemo(
    () => coverScale(geometry.straighten, baseW, baseH),
    [geometry.straighten, baseW, baseH],
  );

  const imgBox = odd
    ? { w: `${(baseH / baseW) * 100}%`, h: `${(baseW / baseH) * 100}%` }
    : { w: '100%', h: '100%' };
  const transform =
    `translate(-50%, -50%) scale(${cover}) rotate(${geometry.straighten}deg) ` +
    `scaleX(${geometry.flipHorizontal ? -1 : 1}) scaleY(${geometry.flipVertical ? -1 : 1}) ` +
    `rotate(${geometry.rotateQuarters * 90}deg)`;

  function beginDrag(handle: HandleId | 'move') {
    return (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = {
        handle,
        startX: event.clientX,
        startY: event.clientY,
        rect: { x: geometry.cropX, y: geometry.cropY, w: geometry.cropW, h: geometry.cropH },
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
    onGeometryChange({ ...geometry, cropX: next.x, cropY: next.y, cropW: next.w, cropH: next.h });
  }

  function endDrag(): void {
    dragRef.current = null;
  }

  return (
    <div
      ref={stageRef}
      className="absolute inset-0 touch-none overflow-hidden bg-black"
      onPointerMove={onDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <img
        src={imageUrl}
        alt={t('crop_tool.crop_source_alt')}
        draggable={false}
        className="pointer-events-none absolute left-1/2 top-1/2"
        style={{ width: imgBox.w, height: imgBox.h, objectFit: 'fill', transform }}
      />

      {/* dark mask outside the crop rect */}
      <div
        className="pointer-events-none absolute shadow-[0_0_0_9999px_rgb(0_0_0/0.6)]"
        style={{
          left: `${geometry.cropX * 100}%`,
          top: `${geometry.cropY * 100}%`,
          width: `${geometry.cropW * 100}%`,
          height: `${geometry.cropH * 100}%`,
        }}
      />

      {/* crop frame: draggable body + handles */}
      <div
        className="absolute cursor-move border border-white/80"
        style={{
          left: `${geometry.cropX * 100}%`,
          top: `${geometry.cropY * 100}%`,
          width: `${geometry.cropW * 100}%`,
          height: `${geometry.cropH * 100}%`,
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
  );
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
