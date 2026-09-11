import { useTranslation } from '@/hooks/useTranslation';
import type { CaptureInfo } from '@/types';

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.round((totalSeconds % 3600) / 60);
  if (hours > 0) {
    return minutes > 0 ? `${hours}h ${minutes}min` : `${hours}h`;
  }
  return `${minutes}min`;
}

export interface CaptureInfoPanelProps {
  info: CaptureInfo;
}

/** A small read-only summary of the source FITS header(s) - object, telescope,
 * filter, frame count / exposure - shown alongside the workflow rail for a
 * stacked composite session (in-app multi-frame stack or a single already-
 * stacked upload). Renders nothing once every field turns out to be absent. */
export function CaptureInfoPanel({ info }: CaptureInfoPanelProps) {
  const { t } = useTranslation();
  const rows: Array<[string, string]> = [];

  if (info.objectName) {
    rows.push([t('editor.capture_info.object'), info.objectName]);
  }
  if (info.telescope) {
    rows.push([t('editor.capture_info.telescope'), info.telescope]);
  }
  if (info.filter) {
    rows.push([t('editor.capture_info.filter'), info.filter]);
  }
  if (info.frameCount) {
    rows.push([
      t('editor.capture_info.frames'),
      info.exposureS ? `${info.frameCount} × ${info.exposureS}s` : String(info.frameCount),
    ]);
  }
  if (info.totalExposureS) {
    rows.push([t('editor.capture_info.total_exposure'), formatDuration(info.totalExposureS)]);
  }
  if (info.dateObs) {
    const parsed = new Date(info.dateObs);
    if (!Number.isNaN(parsed.getTime())) {
      rows.push([t('editor.capture_info.date'), parsed.toLocaleDateString()]);
    }
  }
  if (info.gain !== undefined) {
    rows.push([t('editor.capture_info.gain'), String(info.gain)]);
  }
  if (info.sensorTempC !== undefined) {
    rows.push([t('editor.capture_info.sensor_temp'), `${info.sensorTempC.toFixed(1)}°C`]);
  }

  if (rows.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5 border-t border-hairline pt-3">
      <h3 className="eyebrow">{t('editor.capture_info.title')}</h3>
      <dl className="flex flex-col gap-1 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3">
            <dt className="shrink-0 text-muted">{label}</dt>
            <dd className="truncate text-right text-ink" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
