# Design system

## Contents

- [Principles](#principles)
- [Tokens](#tokens)
- [Component classes](#component-classes)
- [Rules of thumb](#rules-of-thumb)

MyAstroShine shares its visual charter with **MyAstroBoard** - the two apps
should feel like one product family. The language:

- a **teal primary accent** (`--color-accent`) and an **amber ecosystem accent**
  (`--color-amber`, `#f59e0b`, reserved for Astrodex) - deep teal `#0e7490` in
  light, sky `#38bdf8` in dark;
- **surfaces in four elevation steps** - frosted white in light, deep navy-teal
  in dark;
- a **fixed background gradient** with two soft ambient halos (amber top-right,
  teal bottom-left);
- **glass panels** - translucent surface, hairline border, soft depth shadow.

**Light is the default; dark is a footer toggle away.** Both are driven by the
same semantic tokens - see principle 7.

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
   amber for anything Astrodex (the "Send to Astrodex" button, the integration
   banner). Exactly one filled/primary action is visible in any view; everything
   else is `outline` or `ghost`.
4. **Text is cool off-white, never `#fff`.** Three weights of foreground:
   `ink` (primary), `muted` (secondary), `faint` (tertiary), plus `ghost` for
   disabled.
5. **Focus is always visible.** Every interactive element has a `focus-visible`
   ring; never remove an outline without replacing it.
6. **Motion is small and fast.** 130-200 ms, `--ease-premium`. Respect
   `prefers-reduced-motion` (handled globally in `index.css`).
7. **Two themes, one token set.** `:root` in `frontend/src/styles/index.css`
   holds the **light** palette (the default); the `.dark` class - set on `<html>`
   before first paint, from the footer **Theme** control (System / Light / Dark)
   or the OS setting - overrides the same `--color-*` / `--shadow-*` tokens with
   the dark palette. Components never branch on theme. The MyAstroBoard "red
   night" mode (`[data-theme="red"]`) can be added the same way later without
   touching component code. **Exception:** chrome layered *on top of an image*
   (the split-view divider, framing handles, the zoom toolbar, the Depth Shift
   HUD) stays dark-on-image in both themes.

## Tokens

Defined in `@theme` in `frontend/src/styles/index.css`; Tailwind generates the
matching utilities (`bg-surface`, `text-muted`, `border-line`, `btn-amber`, ...).
Every `--color-*` and `--shadow-*` plus the raw gradient/halo vars are **theme
values** - `@theme` / `:root` carries the light set, and the `.dark {}` block
redeclares them. Radius, motion, and type never change with theme.

| Group | Tokens |
|-------|--------|
| Surfaces | `canvas` `surface` `raised` `overlay` |
| Lines | `hairline` `line` `line-strong` |
| Text | `ink` `muted` `faint` `ghost` |
| Primary accent | `accent` `accent-strong` `accent-deep` `accent-wash` `on-accent` |
| Amber accent | `amber` `amber-strong` `amber-wash` `on-amber` |
| Status | `danger` `danger-wash` `success` `warning` |
| Chrome hover | `hover` (theme-flipped wash for `hover:bg-hover` on rails, tabs, ghost buttons) |
| Channels | `channel-red` `channel-green` `channel-blue` (tone curve + histogram) |
| Slider tracks | `track-warm` `track-neutral` `track-cool` `track-green` `track-magenta` `track-dark` `track-bright` `track-muted` (the `.slider-track-*` gradients - illustrative hues, not status) |
| Starfield | `star` (the landing screen's `.starfield` pin-points) |
| Radius | `--radius-sm|md|lg|xl` (6 / 8 / 12 / 16 px) |
| Elevation | `--shadow-panel` `--shadow-pop` `--shadow-glass` `--shadow-premium` |
| Gradients / halos | `--bg-gradient` `--gradient-accent` `--halo-accent` `--halo-amber` (raw CSS, not utilities) |
| Motion | `--ease-premium` |
| Type | `--font-sans` (Inter if present, else the Avenir Next / Segoe UI Variable system stack) `--font-mono` |

## Component classes

Compose these; do not re-implement them per component.

| Class | Use |
|-------|-----|
| `.panel` | Frames a region - a grid column, a settings pane, a result block. Glass, hairline border, soft shadow. |
| `.panel-inset` | A block nested *inside* a `.panel` - a stat list, the histogram, an image mat. Recessed (`bg-raised`), no shadow. |
| `.eyebrow` | Uppercase section label |
| `.btn` + `.btn-primary\|-amber\|-outline\|-ghost\|-danger` | Buttons (`.btn-sm` for compact). `-primary` is the teal gradient, `-amber` is the Astrodex gradient |
| `.field` | Text input / select / textarea |
| `.label` | Form field label |
| `.slider` | Range input. The track fills in the accent from the neutral value to the thumb (`--fill-from` / `--fill-to`, 0-1, set per instance by `SliderGroup`); the thumb is an accent ring |
| `.slider-track-temperature\|-tint\|-exposure\|-colour` | A gradient track that shows what the slider does (warm -> cool, green -> magenta, dark -> bright, muted -> vivid), in place of the fill |
| `.segmented` + `.segmented-item` / `.segmented-item-active` | Tab-style switch |
| `.chip` / `.chip-active` | Toggle pill (engines, stretch mode, go-back points) |
| `.option-card` / `.option-card-active` | Selectable card: icon + name + one-line description (presets). Chip states, block-shaped |
| `.dropzone` / `.dropzone-active` | Drag-and-drop target |
| `.starfield` | Decorative pin-point starfield behind the landing screen only |

## Icons

One family, in `components/icons.tsx`: 24px grid, 1.6 round stroke,
`currentColor`, sized and coloured by the caller's classes - the same drawing
rules as MyAstroBoard's own icons (`static/img/icons`; `GalaxyIcon` is a port of
its `galaxy.svg`). **Never emoji** in the UI: every platform draws them
differently. A missing icon gets drawn in this family and added there.

## Rules of thumb

- **Two surface levels, nothing else.** `.panel` for a region, `.panel-inset`
  for a block nested in one. Never hand-roll `rounded border bg-surface` - if a
  surface isn't one of those two, it shouldn't be a surface.
- Section spacing: `gap-5`/`gap-6`; inside a panel `gap-4`; tight groups `gap-2`.
- Panel padding: `p-4 sm:p-5` (that is what `.panel` does).
- Numbers (percentages, counts, versions): add `tabular-nums`.
- Editor layout: three `.panel` columns,
  `lg:grid-cols-[14rem_19rem_minmax(0,1fr)]` - the **workflow rail**
  (`EditorRail`: steps grouped by `phase` under Prepare / Enhance / Finish
  headings, an icon and a plain-language subtitle each), the active step's
  **inspector** (`EditorInspector`), then the **preview** (the image matted in a
  `bg-black` inset, the go-back points and the folded histogram below it, one
  card). The preview column is sticky so it stays visible while the inspector
  scrolls. The workflow order lives in one place - `EDITOR_STEPS` in
  `types/index.ts` - and mirrors the backend pipeline order.
- Below `lg` the editor reflows for a phone: the rail panel dissolves
  (`contents`) and its nav becomes a **fixed bottom tab bar** (icon over label),
  and the preview is **pinned on top** (`sticky top-14`, image capped at 42vh) so
  a slider's effect stays in view. Keep anything `fixed` out of a `.panel` - its
  `backdrop-filter` would become the containing block.
- Full-screen modals (the Depth Shift viewer, confirm dialogs) render at the
  editor root, never inside the sticky preview column: a sticky box is its own
  stacking context, and the inspector (`z-10`) would paint over the modal.
- Inspector: the step title with its icon, **one** short help sentence, the
  longer explanation behind a native `<details>` "Learn more". It ends on the
  **Next step** footer - below a hairline, on the accent wash, with the next
  step's icon - so workflow navigation never reads as one more setting.
- Plain language first: labels say what a control does for the picture
  ("Remove haze", "Catch fainter stars"), not the algorithm; the jargon stays in
  the hint and "Learn more".
- Settings: the section nav and the section content are each a `.panel`
  (`lg:grid-cols-[210px_minmax(0,1fr)]`). Rows inside: label + one-line
  description on the left, control on the right, hairline divider between rows.
- Footer: app name + version on the left; the **Theme** icon toggle
  (`ThemeSwitcher`, a compact `.segmented` radio group: system / light / dark)
  and the **Language** select (`LanguageSwitcher`) plus the GitHub link on the
  right. The update notice folds in as a second line.
- Overlays on top of an image: `bg-black/55` + `backdrop-blur-sm` + `border-white/10` -
  this is the one place a fixed dark treatment is correct in both themes.
- Never introduce a raw hex colour, a theme-specific colour (`bg-white/10`,
  `text-white`), or a new font in a component - add / reuse a token, and give a
  new token a `.dark` override.
- No static inline styles (`AGENTS.md` section 5); dynamic values only
  (`transform: scale(zoom)`, progress-bar `width`, a slider's `--fill-*`).
- Verify every new surface in **both** themes (footer Theme -> Light / Dark).
