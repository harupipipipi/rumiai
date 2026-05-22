/**
 * Cosmos asset path helper.
 *
 * All Cosmos PNG/audio assets live under `frontend/public/cosmos/...` and
 * are served at `${BASE_URL}cosmos/...` (i.e. `/panel/cosmos/...` in the
 * production build, `/cosmos/...` in dev).
 *
 * If an asset is missing the browser silently fails for `background-image`
 * URLs, and `<img>` consumers should attach an `onError` handler that hides
 * the element. This means it's safe to ship the UI before all art assets
 * are placed.
 */

const BASE = (import.meta as ImportMeta & { env?: Record<string, string> }).env?.BASE_URL ?? '/';

export function cosmosAsset(relative: string): string {
  const trimmed = relative.replace(/^\/+/, '');
  return `${BASE.replace(/\/$/, '')}/cosmos/${trimmed}`;
}

export const COSMOS_BG = {
  nebulaDeep: cosmosAsset('bg/nebula-deep.png'),
  nebulaAurora: cosmosAsset('bg/nebula-aurora.png'),
  starsFar: cosmosAsset('bg/stars-far.png'),
  starsNear: cosmosAsset('bg/stars-near.png'),
  grain: cosmosAsset('bg/grain.png'),
};

export const COSMOS_DECOR = {
  shootingStar: cosmosAsset('decor/shooting-star.png'),
  orbitRing: cosmosAsset('decor/orbit-ring.png'),
  dustStreak: cosmosAsset('decor/dust-streak.png'),
  planetSmall: cosmosAsset('decor/planet-small.png'),
  planetLarge: cosmosAsset('decor/planet-large.png'),
};

export const COSMOS_BRAND = {
  emblem: cosmosAsset('brand/rumi-emblem.png'),
  logo: cosmosAsset('brand/rumi-logo.png'),
  wordmark: cosmosAsset('brand/rumi-wordmark.png'),
  companion: cosmosAsset('brand/rumi-companion.png'),
};

export const COSMOS_ICONS = {
  starGold: cosmosAsset('icons/star-gold.png'),
  starBlue: cosmosAsset('icons/star-blue.png'),
  starMagenta: cosmosAsset('icons/star-magenta.png'),
  packPlanet: cosmosAsset('icons/pack-planet.png'),
  flowComet: cosmosAsset('icons/flow-comet.png'),
  nodeStar: cosmosAsset('icons/node-star.png'),
  kernelCore: cosmosAsset('icons/kernel-core.png'),
};

export const COSMOS_AVATARS = [
  cosmosAsset('avatars/cosmonaut-1.png'),
  cosmosAsset('avatars/cosmonaut-2.png'),
  cosmosAsset('avatars/cosmonaut-3.png'),
  cosmosAsset('avatars/cosmonaut-4.png'),
  cosmosAsset('avatars/cosmonaut-5.png'),
];

export const COSMOS_SFX = {
  boot: cosmosAsset('sfx/boot.mp3'),
  click: cosmosAsset('sfx/click.mp3'),
  nav: cosmosAsset('sfx/nav.mp3'),
  success: cosmosAsset('sfx/success.mp3'),
  error: cosmosAsset('sfx/error.mp3'),
  launch: cosmosAsset('sfx/launch.mp3'),
  ambient: cosmosAsset('sfx/ambient.mp3'),
};

export type CosmosSfxKey = keyof typeof COSMOS_SFX;

/**
 * Hide an <img> element when its source 404s. Safe to attach to every
 * decorative cosmos image so the UI never shows broken-image icons before
 * the user runs their image generator.
 */
export const hideOnError: React.ReactEventHandler<HTMLImageElement> = (event) => {
  const target = event.currentTarget;
  target.style.display = 'none';
  // Mark the parent so callers can swap to a fallback when desired.
  target.dataset.cosmosBroken = 'true';
};

import type * as React from 'react';
