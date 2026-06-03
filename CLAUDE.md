# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mandatory behaviours

1. **Commit and push after every meaningful unit of work.** As work progresses, stage and push changes to GitHub regularly — never leave a session without committing completed work. Use clean, descriptive commit messages that explain *what changed and why*. The remote is `https://github.com/ibon-code/Claude-landing-page.git` (branch `main`).

2. **Always ask before applying the Plug and Play design system to a new project.** When starting any new design or front-end task, explicitly ask the user whether they want to use the PnP design system in this repo. Do not assume it applies — the user may want a different brand or a blank canvas.

## What this repo is

A **Plug and Play (PnP) design system** plus HTML landing pages and slide decks built on top of it. There is no build step, bundler, or test suite — all artifacts are plain HTML/CSS/JS that open directly in a browser. The published output is `index.html` on GitHub Pages.

## Previewing files

Open any HTML file directly in a browser — there is no dev server. For the landing page:

```bash
open index.html
```

For the marketing-site UI kit (React + Babel via CDN — must be served, not opened as `file://`):

```bash
cd "Plug and Play Design System (1)/ui_kits/marketing-site"
python3 -m http.server 8080
# then open http://localhost:8080
```

The slides and all other HTML files open as plain `file://` without a server.

## Publishing a shareable page

`index.html` is the file deployed to GitHub Pages (`https://ibon-code.github.io/Claude-landing-page/`). When changes are made to the landing page, the shareable file must be regenerated — the workflow is:

1. Edit `lleida-landing.html` (the working source file — **not** committed to git).
2. Regenerate `index.html` by inlining the design-system CSS and base64-encoding the logo PNGs into data URIs (removes all local path dependencies). A Python script does this:

```python
import base64, re

def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(open(path,'rb').read()).decode()

base = "Plug and Play Design System (1)"
with open("lleida-landing.html") as f:
    html = f.read()
css = open(f"{base}/colors_and_type.css").read()
html = html.replace('<link rel="stylesheet" href="./Plug and Play Design System (1)/colors_and_type.css">',
                    f'<style>\n{css}\n</style>')
html = html.replace('src="./Plug and Play Design System (1)/assets/logos/pnp-wordmark-dark.png"',
                    f'src="{b64(f"{base}/assets/logos/pnp-wordmark-dark.png", "image/png")}"')
html = html.replace('src="./Plug and Play Design System (1)/assets/logos/pnp-wordmark-white.png"',
                    f'src="{b64(f"{base}/assets/logos/pnp-wordmark-white.png", "image/png")}"')
open("index.html","w").write(html)
```

3. Commit and push `index.html`. GitHub Pages auto-deploys from the `main` branch root.

## Design system — non-negotiables

All brand rules live in `Plug and Play Design System (1)/README.md`. The hard constraints:

- **Token file**: always `<link rel="stylesheet" href=".../colors_and_type.css">` (or inline it). Never hard-code hex values that duplicate a token.
- **Primary color**: `--pnp-dark-blue: #253849`. Body text: `--pnp-body: #313C51` — never pure black.
- **Typeface**: `Protipo` for all copy (loaded via `@font-face` in the token file). `Bebas Neue` for the wordmark lockup only. `MonoRGO Pro` only if explicitly requested.
- **Corner radius**: `--radius: 12px` on all boxes, buttons, and frames.
- **Signature device**: thick yellow (`--pnp-yellow: #E9A53A`) rounded underline under key `h2` headings — applied via `::after` pseudo-element, `height: 6px`, `width: 52px`, `border-radius: 999px`, `bottom: -14px`.
- **Periwinkle blobs**: `--pnp-periwinkle: #C9D6F5` soft shapes behind hero/CTA content — low opacity, blurred, never the focal point.
- **Shadows**: `--shadow-card` (resting) → `--shadow-card-hover` (lifted) on interactive elements.
- **No emoji** anywhere in brand materials.

### Vertical accent colors (quick reference)

| Vertical | Token | Hex |
|---|---|---|
| Supply Chain | `--v-supply-chain` | `#32749A` |
| Sustainability/Energy | `--v-sustainability` | `#60BA46` |
| Fintech | `--v-fintech` | `#4F6FDC` |
| Mobility & Physical AI | `--v-mobility` | `#1B8C8C` |
| Advanced Manufacturing | `--v-advanced-mfg` | `#B5532E` |
| New Materials | `--v-new-materials` | `#8A6CC9` |
| Real Estate | `--v-real-estate` | `#C98A2E` |
| Smart Cities | `--v-smart-cities` | `#2E9BC9` |

## Key files

| File | Purpose |
|---|---|
| `index.html` | **Deployed artifact** — self-contained (inlined CSS + base64 logos), published to GitHub Pages. Edit `lleida-landing.html` instead. |
| `lleida-landing.html` | Working source for the Lleida landing page. References design-system CSS/assets by local path — not shareable as-is. |
| `Plug and Play Design System (1)/colors_and_type.css` | Single source of truth for all design tokens (`@font-face`, colors, type scale, spacing, radius, shadows). Link this in every artifact. |
| `Plug and Play Design System (1)/README.md` | Full brand context, voice & copy guidelines, visual foundations, iconography. Read before creating any new artifact. |
| `Plug and Play Design System (1)/ui_kits/marketing-site/` | React 18 + Babel (CDN) component kit. Components export to `window` and accept `onToast(msg)`. Requires a local server. |
| `Plug and Play Design System (1)/slides/` | HTML slide deck templates using the `<deck-stage>` web component (`deck-stage.js`). Keyboard nav, PDF print, thumbnail rail built in. |

## UI kit pattern (marketing site)

The marketing-site kit uses **React 18 via UMD CDN + Babel standalone** — no npm, no bundler. Components are loaded as `<script type="text/babel" src="Component.jsx">` and mounted with `ReactDOM.createRoot`. Each component registers itself on `window` (e.g. `window.Hero = Hero`) so the main `<script>` can compose them. Lucide icons are initialised with `window.lucide.createIcons()` after each render.

## Slide deck pattern

Slides are authored at **1280×720** inside `<deck-stage>` (1920×1080 for full-bleed decks). The component auto-scales to viewport, supports keyboard/touch navigation, speaker notes via `<script type="application/json" id="speaker-notes">`, and prints one-slide-per-page to PDF. Add a new slide by appending a `<div class="slide ...">` inside the `<deck-stage>` element.
