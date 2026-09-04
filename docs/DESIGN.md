# Design system

MyAstroShine shares its visual charter with **MyAstroBoard** - the two apps
should feel like one product family. The language:

- a **sky/teal primary accent** (`--color-accent`, `#38bdf8`) and an **amber
  ecosystem accent** (`--color-amber`, `#f59e0b`, reserved for AstroDex);
- **deep navy-teal surfaces** in four elevation steps;
- a **fixed background gradient** with two soft ambient halos (amber top-right,
  teal bottom-left);
- **glass panels** - translucent surface, hairline border, soft depth shadow.

It is still restrained: the astronomical image is the loudest thing on screen,
chrome is quiet, and saturated colour is used sparingly (one primary action per
view).

Every new screen and component follows this. If a design need is not covered
here, extend the token layer or the component classes in
`frontend/src/styles/index.css` rather than one-off styling in a component.

## Principles

1. **The image wins.** Chrome is muted; colour is rare. The background gradient
   and halos sit far behind content and never compete with an image.
2. **Hierarchy from surface, line, then shadow.** Four elevation steps
   (`canvas` -> `surface` -> `raised` -> `overlay`), hairline borders, and glass
   depth on panels.
3. **Two accents, used deliberately.** Teal for the primary action and selection;
   amber for anything AstroDex (the "Send to AstroDex" button, the integration
   banner). Exactly one filled/primary action is visible in any view; everything
   else is `outline` or `ghost`.
4. **Text is cool off-white, never `#fff`.** Three weights of foreground:
   `ink` (primary), `muted` (secondary), `faint` (tertiary), plus `ghost` for
   disabled.
5. **Focus is always visible.** Every interactive element has a `focus-visible`
   ring; never remove an outline without replacing it.
6. **Motion is small and fast.** 130-200 ms, `--ease-premium`. Respect
   `prefers-reduced-motion` (handled globally in `index.css`).
7. **Dark-only for now.** Tokens are semantic, so a light palette
   (`:root:not(.dark)`) and the MyAstroBoard "red night" mode
   (`[data-theme="red"]`) can be added later without touching component code.

## Tokens

Defined in `@theme` in `frontend/src/styles/index.css`; Tailwind generates the
matching utilities (`bg-surface`, `text-muted`, `border-line`, `btn-amber`, ...).

| Group | Tokens |
|-------|--------|
| Surfaces | `canvas` `surface` `raised` `overlay` |
| Lines | `hairline` `line` `line-strong` |
| Text | `ink` `muted` `faint` `ghost` |
| Primary accent | `accent` `accent-strong` `accent-deep` `accent-wash` `on-accent` |
| Amber accent | `amber` `amber-strong` `amber-wash` |
| Status | `danger` `danger-wash` `success` `warning` |
| Radius | `--radius-sm|md|lg|xl` (6 / 8 / 12 / 16 px) |
| Elevation | `--shadow-panel` `--shadow-pop` `--shadow-glass` `--shadow-premium` |
| Gradients / halos | `--bg-gradient` `--gradient-accent` `--halo-accent` `--halo-amber` (raw CSS, not utilities) |
| Motion | `--ease-premium` |
| Type | `--font-sans` (Inter if present, else the Avenir Next / Segoe UI Variable system stack) `--font-mono` |

## Component classes

Compose these; do not re-implement them per component.

| Class | Use |
|-------|-----|
| `.panel` / `.panel-inset` | Glass card surface (section / nested) |
| `.eyebrow` | Uppercase section label |
| `.btn` + `.btn-primary\|-amber\|-outline\|-ghost\|-danger` | Buttons (`.btn-sm` for compact). `-primary` is the teal gradient, `-amber` is the AstroDex gradient |
| `.field` | Text input / select / textarea |
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
- Settings-style rows: label + one-line description on the left, control on the
  right, hairline divider between rows (see `SettingsView`).
- Overlays on top of an image: `bg-black/55` + `backdrop-blur-sm` + `border-white/10`.
- Never introduce a raw hex colour or a new font in a component - add a token.
- No static inline styles (`AGENTS.md` section 5); dynamic values only
  (`transform: scale(zoom)`, progress-bar `width`).
