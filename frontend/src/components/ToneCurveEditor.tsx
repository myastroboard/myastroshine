import { useRef, useState, type PointerEvent } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import { curveToSvgPath } from '@/services/toneCurve';
import { DEFAULT_CURVE_POINTS, type CurvePoint } from '@/types';

export interface ToneCurveEditorProps {
  /** Empty means "no curve" (identity) - the graph then shows the default 2-point line. */
  points: CurvePoint[];
  onChange: (points: CurvePoint[]) => void;
}

const LEVEL_MAX = 255;
const MIN_GAP = 4; // minimum x-distance between adjacent points

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/** Interactive tone curve: drag points to reshape, double-click to add or remove one. */
export function ToneCurveEditor({ points, onChange }: ToneCurveEditorProps) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const curve = points.length >= 2 ? points : DEFAULT_CURVE_POINTS;

  function toDataPoint(event: PointerEvent): CurvePoint {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) {
      return { x: 0, y: 0 };
    }
    const x = clamp(Math.round(((event.clientX - rect.left) / rect.width) * LEVEL_MAX), 0, LEVEL_MAX);
    const fromTop = ((event.clientY - rect.top) / rect.height) * LEVEL_MAX;
    const y = clamp(Math.round(LEVEL_MAX - fromTop), 0, LEVEL_MAX);
    return { x, y };
  }

  function handlePointDown(index: number) {
    return (event: PointerEvent<SVGCircleElement>) => {
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragIndex(index);
    };
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>): void {
    if (dragIndex === null) {
      return;
    }
    const isFirst = dragIndex === 0;
    const isLast = dragIndex === curve.length - 1;
    const { x, y } = toDataPoint(event);
    const minX = isFirst ? 0 : curve[dragIndex - 1].x + MIN_GAP;
    const maxX = isLast ? LEVEL_MAX : curve[dragIndex + 1].x - MIN_GAP;
    const next = curve.map((point, index) =>
      index === dragIndex
        ? { x: isFirst ? 0 : isLast ? LEVEL_MAX : clamp(x, minX, maxX), y }
        : point,
    );
    onChange(next);
  }

  function handlePointerUp(): void {
    setDragIndex(null);
  }

  function handleAddPoint(event: PointerEvent<SVGSVGElement>): void {
    const { x, y } = toDataPoint(event);
    if (curve.some((point) => Math.abs(point.x - x) < MIN_GAP)) {
      return; // too close to an existing point/edge - would make a degenerate segment
    }
    onChange([...curve, { x, y }].sort((a, b) => a.x - b.x));
  }

  function handleRemovePoint(index: number) {
    return (event: PointerEvent<SVGCircleElement>) => {
      event.stopPropagation();
      if (index === 0 || index === curve.length - 1) {
        return; // endpoints are permanent - the curve must span the full 0-255 range
      }
      onChange(curve.filter((_, i) => i !== index));
    };
  }

  return (
    <div className="panel flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="eyebrow">{t('tone_curve.title')}</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange([])}>
          {t('common.reset')}
        </button>
      </div>
      <p className="text-xs text-faint">{t('tone_curve.help')}</p>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${LEVEL_MAX} ${LEVEL_MAX}`}
        role="img"
        aria-label={t('tone_curve.title')}
        // overflow-visible: control points sitting exactly at y=0 or y=255 (the
        // graph's edges) would otherwise have half their hit area clipped by
        // the viewBox boundary - hard or impossible to grab precisely.
        className="aspect-square w-full touch-none overflow-visible rounded-md border border-line bg-canvas"
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onDoubleClick={handleAddPoint}
      >
        <g transform={`scale(1, -1) translate(0, -${LEVEL_MAX})`}>
          <line
            x1={0}
            y1={0}
            x2={LEVEL_MAX}
            y2={LEVEL_MAX}
            className="stroke-line"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
          <path d={curveToSvgPath(curve)} fill="none" className="stroke-accent" strokeWidth={2} />
          {curve.map((point, index) => (
            <circle
              key={index}
              cx={point.x}
              cy={point.y}
              r={5}
              className="cursor-pointer fill-canvas stroke-accent"
              strokeWidth={2}
              onPointerDown={handlePointDown(index)}
              onDoubleClick={handleRemovePoint(index)}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
