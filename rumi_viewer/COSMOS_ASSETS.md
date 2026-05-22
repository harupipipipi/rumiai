# Rumi Cosmos — Asset Placement Guide

This document lists every image and sound the Cosmos theme of `rumi_viewer`
expects to find, where each file goes, the exact dimensions / format, what
it should look like, and a ready-to-use prompt for an image generation
model (any "anything you ask for" model works — the prompts are optimised
for transparent PNG output).

> **TL;DR** — drop matching files at the listed path and the UI picks them
> up automatically. Every consumer attaches an `onError` handler that hides
> the element if the file is missing, so the panel never shows broken-image
> icons. You can ship art incrementally.

## Where Cosmos looks for assets

The frontend serves anything inside `rumi_viewer/frontend/public/cosmos/...`
at runtime. In dev that maps to `http://localhost:3000/cosmos/...`; in the
production panel build it maps to `/panel/cosmos/...`. The path helper
`src/cosmos/assets.ts` already produces the correct URLs through
`import.meta.env.BASE_URL`.

```
rumi_viewer/frontend/public/cosmos/
├── bg/
│   ├── nebula-deep.png
│   ├── nebula-aurora.png
│   ├── stars-far.png
│   ├── stars-near.png
│   └── grain.png
├── decor/
│   ├── shooting-star.png
│   ├── orbit-ring.png
│   ├── dust-streak.png
│   ├── planet-small.png
│   └── planet-large.png
├── brand/
│   ├── rumi-emblem.png
│   ├── rumi-logo.png
│   ├── rumi-wordmark.png
│   └── rumi-companion.png
├── icons/
│   ├── star-gold.png
│   ├── star-blue.png
│   ├── star-magenta.png
│   ├── pack-planet.png
│   ├── flow-comet.png
│   ├── node-star.png
│   └── kernel-core.png
├── avatars/
│   ├── cosmonaut-1.png
│   ├── cosmonaut-2.png
│   ├── cosmonaut-3.png
│   ├── cosmonaut-4.png
│   └── cosmonaut-5.png
└── sfx/
    ├── boot.mp3
    ├── click.mp3
    ├── nav.mp3
    ├── success.mp3
    ├── error.mp3
    ├── launch.mp3
    └── ambient.mp3
```

## Visual language

- **Palette** — deep indigo `#04060f`, royal navy `#0c1230`, starlight blue
  `#7c93ff`, magenta `#c66bff`, ember gold `#f5d27a`, mint accent `#5be7c4`.
- **Mood** — vast, calm, slightly mystical. Think NASA + Studio Ghibli +
  art-deco constellation charts. Avoid sci-fi clichés (no spaceships, no
  cyberpunk neon).
- **Format** — every image is **transparent PNG**. No outer borders, no
  drop-shadows baked into the file (the UI applies its own glow).
- **Motion** — most decorative images are rotated/parallaxed by CSS, so
  generated stills should feel "complete on their own" rather than
  trail-leading.

## Background layer (`public/cosmos/bg/`)

| File              | Size      | Description                                            | Prompt seed                                                                                                                                                                                                                                                                                                                            |
| ----------------- | --------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nebula-deep.png` | 3840×2160 | Deep void with subtle indigo nebula, almost matte.     | `Ultra-wide cosmic nebula photograph, deep indigo and navy core with hints of magenta and gold dust at the edges, very soft and painterly, almost matte, no foreground objects, transparent edges fading to pure black, 3840x2160, transparent PNG.`                                                                                   |
| `nebula-aurora.png` | 3840×2160 | Coloured aurora wash that blends in screen mode.    | `Diffuse cosmic aurora veil, wide horizontal sweep of starlight blue and orchid magenta with a thin gold ribbon, painterly soft edges, fully transparent background, intended to be multiplied/screened over a dark scene, 3840x2160 PNG.`                                                                                              |
| `stars-far.png`   | 2048×2048 | Tile of distant pin-prick stars, transparent.        | `Seamless 2048x2048 tile of tiny distant stars on transparent background, mix of warm white, cool blue, and faint gold pin-pricks, varying sizes from 1px to 3px, randomly distributed but balanced, no nebula, no large stars, fully transparent PNG.`                                                                              |
| `stars-near.png`  | 2048×2048 | Tile of nearer, larger sparkling stars.              | `Seamless 2048x2048 tile of nearby stars on transparent background, including a few diamond-cross sparkle stars, sizes 1-6px, gentle bloom on the brightest, palette of ivory, starlight blue, ember gold, and soft magenta, transparent PNG.`                                                                                       |
| `grain.png`       | 512×512   | Film grain noise tile.                               | `Seamless 512x512 monochrome film grain noise, very subtle, designed to overlay at low opacity, transparent PNG.`                                                                                                                                                                                                                       |

If you only have time for one bg asset, do `stars-near.png` — the rest of
the layout already paints a soft gradient for depth.

## Decor (`public/cosmos/decor/`)

| File                | Size      | Description                                                            | Prompt seed                                                                                                                                                                                                  |
| ------------------- | --------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `shooting-star.png` | 256×64    | Comet head + short trail, used by the random meteor spawner.           | `Stylised comet rendered horizontally, bright ember-gold head on the right, fading streak to the left, soft sparkle, transparent PNG, 256x64.`                                                              |
| `orbit-ring.png`    | 1024×1024 | Soft elliptical ring with faint dust, used as decorative orbiter.       | `Concentric elliptical orbit ring, very thin gold and starlight-blue lines with subtle dust particles, slight tilt, transparent background, 1024x1024 PNG, suitable for slow rotation.`                       |
| `dust-streak.png`   | 1024×128  | Horizontal sparkle streak, optional accent.                            | `Long horizontal ribbon of golden cosmic dust with scattered tiny stars, fades at both ends, transparent PNG, 1024x128.`                                                                                       |
| `planet-small.png`  | 256×256   | Optional small gas-giant for empty cards.                              | `Stylised small gas planet, cool blue with a thin gold ring, transparent background, soft rim light, painterly, 256x256 PNG.`                                                                                  |
| `planet-large.png`  | 768×768   | Hero planet for splash / Setup page.                                   | `Stylised large gas planet, deep magenta to indigo gradient with a tilted gold ring, soft cloud bands, gentle starlight bloom, transparent background, 768x768 PNG.`                                            |

## Brand (`public/cosmos/brand/`)

| File                  | Size      | Description                                                          | Prompt seed                                                                                                                                                                                                                              |
| --------------------- | --------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rumi-emblem.png`     | 1024×1024 | The "R" emblem used at boot, sidebar, Setup. Round, glowing.          | `Round metallic emblem of the letter R, polished ember gold with a deep indigo recess, faint magenta and starlight glow around the rim, art-deco geometry, slight bevel, transparent background, 1024x1024 PNG.`                          |
| `rumi-logo.png`       | 512×512   | Smaller emblem variant for the sidebar.                              | `Same emblem as rumi-emblem, simplified for small sizes, crisp 512x512 transparent PNG, no glow.`                                                                                                                                          |
| `rumi-wordmark.png`   | 1024×256  | "Rumi AI" wordmark in metallic gold, transparent.                    | `Wordmark "Rumi AI" in a refined modern serif (Cormorant Garamond style), brushed ember gold with subtle highlight, fine letter-spacing, transparent background, 1024x256 PNG.`                                                            |
| `rumi-companion.png`  | 1024×1536 | Friendly cosmic guide / mascot for the Setup page.                   | `Stylised cosmic guide character, ethereal woman in flowing star-cloth robes holding a glowing constellation lantern, painterly anime / Mucha hybrid style, ember-gold and starlight-blue palette, transparent background, 1024x1536 PNG.` |

## Icons (`public/cosmos/icons/`)

Every icon below is **decorative** and shown as a small image (24–48 px).
Generate at 256×256 then export as transparent PNG.

| File                | Description                                          | Prompt seed                                                                                                                                                                                                  |
| ------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `star-gold.png`     | Solid 4-point star, ember gold.                      | `Stylised four-point star, polished ember gold with subtle inner highlight, faint outer glow, transparent background, 256x256 PNG.`                                                                          |
| `star-blue.png`     | Same form, starlight blue.                           | `Stylised four-point star in cool starlight blue, same geometry as star-gold, transparent background, 256x256 PNG.`                                                                                          |
| `star-magenta.png`  | Same form, magenta.                                  | `Stylised four-point star in soft magenta-violet, same geometry as star-gold, transparent background, 256x256 PNG.`                                                                                          |
| `pack-planet.png`   | Small ringed planet — represents a pack.             | `Tiny stylised ringed planet icon, deep indigo body with thin gold ring, transparent background, 256x256 PNG.`                                                                                                |
| `flow-comet.png`    | Mini comet icon — represents a flow.                 | `Compact comet icon in profile view, ember gold head with a short magenta-blue trail, transparent background, 256x256 PNG.`                                                                                  |
| `node-star.png`     | Generic node star, smallest icon.                    | `Tiny radiant star, mostly white-gold with a thin starlight halo, transparent background, 256x256 PNG.`                                                                                                       |
| `kernel-core.png`   | The "core" star at the centre of the constellation. | `Bright spherical star with a soft corona, gold-white core fading to magenta then transparent, transparent background, 256x256 PNG.`                                                                          |

## Avatars (`public/cosmos/avatars/`)

Five interchangeable round avatars (the existing five-slot avatar picker
will reach for these when the Cosmos theme is active in a future iteration;
for now they're optional). 512×512 PNGs, transparent or filled circles.

Suggested prompts:

1. `Portrait of a cosmonaut woman, golden visor reflecting nebula colours, painterly, transparent background, 512x512 PNG.`
2. `Portrait of a stargazing fox-spirit with constellations woven into its fur, transparent background, 512x512 PNG.`
3. `Portrait of an elder sage holding a star compass, soft warm lighting, transparent background, 512x512 PNG.`
4. `Portrait of a celestial cat-like guardian with glowing eyes, transparent background, 512x512 PNG.`
5. `Portrait of a smiling young navigator wearing a star-blue cape, transparent background, 512x512 PNG.`

## Sounds (`public/cosmos/sfx/`)

All sounds default to OFF. The user enables them in **Settings → Cosmic
Sounds**, after which the panel triggers them on actions (boot, nav, toast,
launch). Missing files fail silently — there's no need to ship every clip
day-one.

| Key      | Suggested length | Volume target | Description                                                                              |
| -------- | ---------------- | ------------- | ---------------------------------------------------------------------------------------- |
| `boot.mp3`     | 3.5–5 s          | -14 LUFS      | Slow ambient swell + a subtle bell-like chime at the end. Plays during BootSequence.    |
| `click.mp3`    | 80–140 ms        | -22 LUFS      | Soft tick / glass-tap. Generic UI tap.                                                  |
| `nav.mp3`      | 200–300 ms       | -20 LUFS      | Gentle whoosh as the user moves between sections.                                       |
| `success.mp3`  | 350–600 ms       | -16 LUFS      | Bright bell pair, warm and bright. Used by success toasts.                              |
| `error.mp3`    | 250–400 ms       | -16 LUFS      | Soft thud + faint downward bell. Used by error toasts.                                  |
| `launch.mp3`   | 700 ms–1.2 s     | -16 LUFS      | Rocket-like whoosh with a small chime tail. Used when the user launches a profile.      |
| `ambient.mp3`  | Loop, 30–90 s    | -28 LUFS      | Optional looped ambient pad. Reserved — currently disabled by default in Settings.       |

### Recording / generation tips

- Every sound should be sub -3 dBFS peak so the JS volume layer (`0.18` to
  `0.55`) doesn't clip on louder hardware.
- MP3 192 kbps is fine; the panel doesn't stream large files.
- Stereo, 44.1 kHz.

## How the assets wire up in code

- `src/cosmos/assets.ts` — single source of truth for paths.
- `src/cosmos/CosmosBackground.tsx` — uses `bg/*` and `decor/orbit-ring`,
  `decor/shooting-star`.
- `src/cosmos/CosmosLogo.tsx` — uses `brand/rumi-emblem` and
  `brand/rumi-logo` with a CSS-gradient fallback "R".
- `src/cosmos/BootSequence.tsx` — uses CosmosLogo + plays `sfx/boot.mp3`.
- `src/cosmos/SoundProvider.tsx` — pre-loads the seven SFX, gates on a
  `localStorage` flag set from Settings.
- `src/pages/Setup.tsx` — uses `brand/rumi-companion`.
- `src/pages/Dashboard.tsx` — uses `decor/orbit-ring` for the hero, plus
  the Canvas2D constellation map.

## Replacing assets later

Just overwrite the file in `public/cosmos/...` and rebuild. The viewer's
`npm run build` step copies `dist/` into the panel artefact directory
(`rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`) so the
runtime serves the new files immediately on the next launch.

## Reduced motion / accessibility

- The CSS respects `prefers-reduced-motion: reduce` and disables orbit and
  twinkle animations automatically — there's no extra work to do.
- The Cosmos colour palette has an automatic light variant ("Dawn Nebula")
  for users who prefer light mode.
- All decorative images are marked `aria-hidden` or have empty `alt`
  values — they don't pollute screen readers.
