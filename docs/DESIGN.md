# Design system

MyAstroShine uses one visual language across the whole app: **"darkroom / neutre
pro"** - a warm-neutral near-black surface, a single restrained accent, hairline
separation, generous whitespace, and crisp typography. It is deliberately quiet
so the astronomical images stay the loudest thing on screen.

Every new screen and component follows this. If a design need is not covered
here, extend the token layer or the component classes in
`frontend/src/styles/index.css` rather than one-off styling in a component.

## Principles

1. **The image wins.** Chrome is muted; colour is rare. No gradients, no glow, no
   decorative imagery.
2. **Hierarchy from surface + line, not shadow.** Four elevation steps
   (`canvas` -> `surface` -> `raised` -> `overlay`); hairline borders. Shadows
   only for things that truly float (popovers, modals).
3. **One accent.** A desaturated blue (`--color-accent`, `#5b8fb9`). Exactly one
   filled/primary action is visible in any view; everything else is `outline` or
   `ghost`.
4. **Text is warm off-white, never `#fff`.** Three weights of foreground:
   `ink` (primary), `muted` (secondary), `faint` (tertiary), plus `ghost` for
   disabled.
5. **Focus is always visible.** Every interactive element has a `focus-visible`
   ring; never remove an outline without replacing it.
6. **Motion is small and fast.** 130-200 ms, `--ease-premium`. Respect
   `prefers-reduced-motion` (handled globally in `index.css`).
7. **Dark-only for now.** Tokens are semantic, so a light palette can be added
   later as `:root:not(.dark)` overrides without touching component code.

## Tokens

Defined in `@theme` in `frontend/src/styles/index.css`; Tailwind generates the
matching utilities (`bg-surface`, `text-muted`, `border-hairline`, ...).

| Group | Tokens |
|-------|--------|
| Surfaces | `canvas` `surface` `raised` `overlay` |
| Lines | `hairline` `line` `line-strong` |
| Text | `ink` `muted` `faint` `ghost` |
| Accent | `accent` `accent-strong` `accent-deep` `accent-wash` `on-accent` |
| Status | `danger` `danger-wash` `success` `warning` |
| Radius | `--radius-sm|md|lg|xl` (6 / 8 / 12 / 16 px) |
| Elevation | `--shadow-panel` `--shadow-pop` |
| Motion | `--ease-premium` |
| Type | `--font-sans` (Inter if present, else system) `--font-mono` |

## Component classes

Compose these; do not re-implement them per component.

| Class | Use |
|-------|-----|
| `.panel` / `.panel-inset` | Card surface (section / nested) |
| `.eyebrow` | Uppercase section label |
| `.btn` + `.btn-primary\|-outline\|-ghost\|-danger` | Buttons (`.btn-sm` for compact) |
| `.field` | Text input / select |
| `.label` | Form field label |
| `.slider` | Range input (custom track + thumb) |
| `.segmented` + `.segmented-item` / `.segmented-item-active` | Tab-style switch |
| `.chip` / `.chip-active` | Toggle pill (presets, filters) |
| `.dropzone` / `.dropzone-active` | Drag-and-drop target |

## Rules of thumb

- Section spacing: `gap-5`/`gap-6`; inside a panel `gap-4`; tight groups `gap-2`.
- Panel padding: `p-4 sm:p-5` (that is what `.panel` does).
- Numbers (percentages, counts, versions): add `tabular-nums`.
- Two-column editor layout: `lg:grid-cols-[minmax(0,1fr)_340px]`.
- Overlays on top of an image: `bg-black/55` + `backdrop-blur-sm` + `border-white/10`.
- Never introduce a raw hex colour or a new font in a component - add a token.
- No static inline styles (`AGENTS.md` section 5); dynamic values only
  (`transform: scale(zoom)`, progress-bar `width`).
