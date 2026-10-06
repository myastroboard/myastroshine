import type { ReactNode } from 'react';

/**
 * The app's own line icons - one family, drawn on a 24px grid with a 1.6
 * round stroke in `currentColor`, matching MyAstroBoard's custom icons
 * (`static/img/icons`). No emoji anywhere in the UI: they render differently on
 * every platform. Size and colour come from the caller's classes.
 */
export interface IconProps {
  className?: string;
}

function Icon({ className = 'h-4 w-4', children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  );
}

// -- Workflow steps -----------------------------------------------------------

export function SparkleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9-1.9 5.1-1.9-5.1-5.1-1.9 5.1-1.9z" />
      <path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
    </Icon>
  );
}

export function LayersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5 3.5 8 12 12.5 20.5 8z" />
      <path d="M3.5 12 12 16.5 20.5 12" />
      <path d="M3.5 16 12 20.5 20.5 16" />
    </Icon>
  );
}

export function CropIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6.5 2.5v13.5a1.5 1.5 0 0 0 1.5 1.5h13.5" />
      <path d="M2.5 6.5h13.5a1.5 1.5 0 0 1 1.5 1.5v13.5" />
    </Icon>
  );
}

/** Sky cleanup: a clear night sky over the horizon. */
export function SkyIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 19.5h19" />
      <path d="M4.5 16c2.5-1.5 5-1.5 7.5 0s5 1.5 7.5 0" />
      <path d="M15.5 4.5a4 4 0 1 0 4 5.5 3.2 3.2 0 0 1-4-5.5z" />
      <path d="M6 6.5h.01M9.5 9.5h.01M5 11h.01" strokeWidth={2.2} />
    </Icon>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
    </Icon>
  );
}

export function CurveIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
      <path d="M6.5 17.5c4.5 0 4-11 11-11" />
    </Icon>
  );
}

export function PaletteIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.8-1.7 0-1.4-1.3-1.8-1.3-3 0-1 .8-1.6 1.8-1.6h2.2a4 4 0 0 0 4-4c0-3.7-3.8-6.7-8.5-6.7z" />
      <path d="M7.5 12h.01M9.5 8h.01M14.5 7.5h.01" strokeWidth={2.4} />
    </Icon>
  );
}

export function FocusIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20.5 20.5 15.7 15.7" />
      <path d="M11 8.5v5M8.5 11h5" />
    </Icon>
  );
}

export function StarIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5l2.5 5.3 5.8.7-4.3 4 1.1 5.7L12 16.4l-5.1 2.8 1.1-5.7-4.3-4 5.8-.7z" />
    </Icon>
  );
}

/** Depth Shift: two offset planes, a parallax hint. */
export function DepthIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="7.5" width="11" height="11" rx="2" />
      <path d="M8.5 5.5V5a1.5 1.5 0 0 1 1.5-1.5h8.5A1.5 1.5 0 0 1 20 5v8.5a1.5 1.5 0 0 1-1.5 1.5H18" />
    </Icon>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5v11M7.5 10l4.5 4.5 4.5-4.5" />
      <path d="M4.5 16.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2" />
    </Icon>
  );
}

// -- Preset subjects ----------------------------------------------------------

/** The "Style" step: a wand with a spark - a finishing touch. */
export function WandIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 20 14.5 9.5" />
      <path d="M12.5 7.5l4 4" />
      <path d="M18 2.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
      <path d="M7 4v2M6 5h2" />
    </Icon>
  );
}

export function NebulaIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 17.5a4 4 0 0 1-.6-8A5.5 5.5 0 0 1 17 8a4.8 4.8 0 0 1 .5 9.5z" />
      <path d="M9.5 13.5c1.5-1.8 3.5-1.8 5 0" opacity={0.6} />
    </Icon>
  );
}

/** After MyAstroBoard's `galaxy.svg`: a bright core with six curled arms. */
export function GalaxyIcon(props: IconProps) {
  const arm = 'M14 9.5c2-2 5.5-1 6.5 4.5';
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none" />
      {[0, 60, 120, 180, 240, 300].map((angle) => (
        <path key={angle} d={arm} strokeWidth={1.4} transform={`rotate(${angle} 12 12)`} />
      ))}
    </Icon>
  );
}

export function DeepFieldIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <ellipse cx="8" cy="8" rx="2.5" ry="1.2" transform="rotate(-25 8 8)" />
      <ellipse cx="16.5" cy="15.5" rx="3" ry="1.4" transform="rotate(30 16.5 15.5)" />
      <path d="M17 6h.01M6 17h.01M12 12h.01M19.5 10h.01M10 19.5h.01" strokeWidth={2.4} />
    </Icon>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.3 6.3 0 0 0 10 10z" />
    </Icon>
  );
}

export function ClusterIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path
        d="M12 12h.01M9 9.5h.01M15 10h.01M10 15h.01M14.5 14.5h.01M12 6.5h.01M6.5 13h.01M17.5 13.5h.01M12 17.5h.01"
        strokeWidth={2.6}
      />
    </Icon>
  );
}

export function SlidersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4.5 7h9M17.5 7h2M4.5 17h3M11.5 17h8" />
      <circle cx="15.5" cy="7" r="2" />
      <circle cx="9.5" cy="17" r="2" />
    </Icon>
  );
}

// -- Chrome -------------------------------------------------------------------

export function GearIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="2.8" />
      <circle cx="12" cy="12" r="6.5" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <path key={angle} d="M12 2.8v2.7" strokeWidth={2.4} transform={`rotate(${angle} 12 12)`} />
      ))}
    </Icon>
  );
}

export function MonitorIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="4.5" width="18" height="12" rx="2" />
      <path d="M9 20.5h6M12 16.5v4" />
    </Icon>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.5 12.2l2.4 2.4 4.6-5.1" />
    </Icon>
  );
}

/** A single photo - the one-image upload zone. */
export function PhotoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="5" width="17" height="14" rx="2" />
      <path d="M3.5 16l4.5-4.5 3.5 3.5 2.5-2.5 6.5 6.5" />
      <path d="M15.5 9h.01" strokeWidth={2.4} />
    </Icon>
  );
}

/** A pile of exposures - the multi-frame stacking upload zone. */
export function PhotoStackIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="8" width="13" height="12" rx="2" />
      <path d="M6.5 5.5V5a1.5 1.5 0 0 1 1.5-1.5h10A1.5 1.5 0 0 1 19.5 5v9.5A1.5 1.5 0 0 1 18 16h-1.5" />
      <path d="M3.5 17.5l3.5-3.5 3 3 2-2 4.5 4.5" />
    </Icon>
  );
}

/** Go-back points: a clock with a counter-clockwise arrow. */
export function HistoryIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" />
      <path d="M3.5 4v4h4" />
      <path d="M12 8v4l2.8 1.8" />
    </Icon>
  );
}

export function BookmarkIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6.5 4.5A1.5 1.5 0 0 1 8 3h8a1.5 1.5 0 0 1 1.5 1.5V21L12 17l-5.5 4z" />
    </Icon>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 5.5 15.5 12 9 18.5" />
    </Icon>
  );
}
