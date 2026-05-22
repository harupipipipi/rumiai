import { useState } from 'react';
import { COSMOS_BRAND } from './assets';
import { cn } from '@/src/lib/utils';

interface CosmosLogoProps {
  size?: number;
  variant?: 'emblem' | 'logo';
  className?: string;
  /** When true, the gradient fallback letter is wrapped in a halo glow */
  glow?: boolean;
}

/**
 * Renders the Rumi cosmic emblem PNG and falls back to a gold-gradient
 * "R" disc when the asset is missing. The fallback is built from CSS
 * gradients only — no SVG.
 */
export function CosmosLogo({ size = 96, variant = 'emblem', className, glow = true }: CosmosLogoProps) {
  const [broken, setBroken] = useState(false);
  const src = variant === 'logo' ? COSMOS_BRAND.logo : COSMOS_BRAND.emblem;

  if (broken) {
    return (
      <span
        className={cn(
          'cosmos-logo-fallback inline-flex items-center justify-center rounded-full font-display font-bold',
          glow && 'cosmos-halo-gold',
          className,
        )}
        style={{
          width: size,
          height: size,
          fontSize: size * 0.46,
          color: 'var(--accent-fg)',
          background:
            'radial-gradient(circle at 30% 25%, #fff5d8 0%, #f5d27a 35%, #c08c2a 78%, #6a4a14 100%)',
          boxShadow: glow
            ? '0 0 24px 4px var(--cosmos-glow-gold, rgba(245,210,122,0.55)), inset 0 1px 0 rgba(255,255,255,0.5), inset 0 -8px 14px rgba(0,0,0,0.45)'
            : 'inset 0 1px 0 rgba(255,255,255,0.5), inset 0 -8px 14px rgba(0,0,0,0.45)',
          letterSpacing: '-0.05em',
        }}
        aria-hidden
      >
        R
      </span>
    );
  }

  return (
    <img
      src={src}
      alt="Rumi AI"
      width={size}
      height={size}
      onError={() => setBroken(true)}
      className={cn(glow && 'cosmos-halo-gold rounded-full', className)}
      style={{ width: size, height: size, objectFit: 'contain' }}
      loading="eager"
      decoding="async"
    />
  );
}
