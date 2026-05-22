# /cosmos — runtime asset directory

The Cosmos theme of the Rumi panel reads images and sounds from this
directory at runtime. The full list (file names, sizes, dimensions, prompt
seeds for image generation, sound length / loudness specs) lives in:

- `rumi_viewer/COSMOS_ASSETS.md`

You can ship the UI with this directory empty — every consumer hides
gracefully when an asset 404s — and add files incrementally.

## Quick map

```
bg/      ⟶ deep-space backdrops (PNG, transparent edges)
decor/   ⟶ comet, orbit ring, planets, dust streak
brand/   ⟶ Rumi emblem, logo, wordmark, mascot
icons/   ⟶ small star/planet/comet sprites
avatars/ ⟶ 5 cosmic profile avatars
sfx/     ⟶ boot, click, nav, success, error, launch, ambient (.mp3)
```

Generate the PNGs with any image model that supports transparent output;
copy MP3s in directly. The kernel re-serves whatever is in here after the
next `npm run build` (or live during `npm run dev`).
