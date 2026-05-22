import { useEffect, useState } from 'react';
import { COSMOS_BG, COSMOS_DECOR, hideOnError } from './assets';
import { useAppStore } from '@/src/store';

/**
 * Fixed full-viewport visual stack used when the Cosmos theme is active.
 *
 * Layers (back → front):
 *   1. Deep nebula PNG          — establishes the indigo void
 *   2. Aurora veil PNG          — coloured wash that breathes
 *   3. Far star PNG (slow drift)
 *   4. Near star PNG (faster drift, parallax)
 *   5. CSS-only star fallback   — guarantees stars even before PNGs land
 *   6. Orbit ring PNG (decor)
 *   7. Grain PNG film texture
 *   8. Periodic shooting-star sprite
 *
 * Every <img> uses `hideOnError` so the UI degrades gracefully when art
 * files have not yet been generated/placed by the user.
 */
export function CosmosBackground() {
  const theme = useAppStore((state) => state.theme);
  if (theme !== 'Cosmos') return null;

  return (
    <div
      aria-hidden
      className="cosmos-bg pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      data-cosmos-layer="root"
    >
      {/* Deep nebula */}
      <img
        src={COSMOS_BG.nebulaDeep}
        onError={hideOnError}
        alt=""
        className="absolute inset-0 h-full w-full object-cover opacity-80 cosmos-anim-orbit-reverse will-change-transform"
        style={{ animationDuration: '320s' }}
        loading="eager"
        decoding="async"
      />

      {/* Aurora wash */}
      <img
        src={COSMOS_BG.nebulaAurora}
        onError={hideOnError}
        alt=""
        className="absolute inset-0 h-full w-full object-cover mix-blend-screen opacity-60 cosmos-anim-orbit will-change-transform"
        style={{ animationDuration: '460s' }}
        loading="eager"
        decoding="async"
      />

      {/* Far star sprites */}
      <img
        src={COSMOS_BG.starsFar}
        onError={hideOnError}
        alt=""
        className="absolute inset-[-15%] h-[130%] w-[130%] object-cover opacity-90 cosmos-anim-orbit-reverse will-change-transform"
        style={{ animationDuration: '180s' }}
        loading="eager"
        decoding="async"
      />

      {/* Near star sprites */}
      <img
        src={COSMOS_BG.starsNear}
        onError={hideOnError}
        alt=""
        className="absolute inset-[-10%] h-[120%] w-[120%] object-cover opacity-90 cosmos-anim-orbit will-change-transform"
        style={{ animationDuration: '120s' }}
        loading="eager"
        decoding="async"
      />

      {/* CSS-only stars guarantee depth even before PNGs are placed */}
      <div className="cosmos-stars-css" />

      {/* Decorative orbit ring on the right edge */}
      <img
        src={COSMOS_DECOR.orbitRing}
        onError={hideOnError}
        alt=""
        className="absolute -right-[18vw] top-1/2 w-[80vw] max-w-none -translate-y-1/2 opacity-25 cosmos-anim-orbit will-change-transform"
        style={{ animationDuration: '220s' }}
        loading="lazy"
        decoding="async"
      />

      {/* Grain film texture */}
      <img
        src={COSMOS_BG.grain}
        onError={hideOnError}
        alt=""
        className="absolute inset-0 h-full w-full object-cover opacity-[0.035] mix-blend-overlay"
        loading="lazy"
        decoding="async"
      />

      <ShootingStarLayer />
    </div>
  );
}

/**
 * Spawns a shooting star image at random intervals.
 * Falls back to a plain CSS gradient streak if the PNG is missing.
 */
function ShootingStarLayer() {
  const [trail, setTrail] = useState<{ id: number; top: number; delay: number; duration: number }[]>([]);

  useEffect(() => {
    let alive = true;
    let counter = 0;

    const spawn = () => {
      if (!alive) return;
      counter += 1;
      const id = counter;
      const top = Math.random() * 60; // upper 60%
      const delay = Math.random() * 0.4;
      const duration = 1.6 + Math.random() * 1.2;
      setTrail((prev) => [...prev, { id, top, delay, duration }]);
      window.setTimeout(() => {
        if (!alive) return;
        setTrail((prev) => prev.filter((s) => s.id !== id));
      }, (duration + delay + 0.4) * 1000);

      const nextIn = 4500 + Math.random() * 7000;
      window.setTimeout(spawn, nextIn);
    };

    const start = window.setTimeout(spawn, 2200);
    return () => {
      alive = false;
      window.clearTimeout(start);
    };
  }, []);

  return (
    <div className="absolute inset-0">
      {trail.map((star) => (
        <div
          key={star.id}
          className="absolute"
          style={{
            top: `${star.top}%`,
            left: 0,
            width: '40%',
            height: '2px',
            transform: 'translateX(-20%)',
            animation: `cosmos-comet ${star.duration}s ease-in-out ${star.delay}s 1`,
            background: 'linear-gradient(90deg, transparent, var(--cosmos-gold, #f5d27a), transparent)',
            filter: 'drop-shadow(0 0 6px var(--cosmos-glow-gold, rgba(245,210,122,0.6)))',
          }}
        >
          <img
            src={COSMOS_DECOR.shootingStar}
            onError={hideOnError}
            alt=""
            className="absolute right-0 top-1/2 h-6 -translate-y-1/2"
            loading="lazy"
            decoding="async"
          />
        </div>
      ))}
    </div>
  );
}
