import { useEffect, useRef } from 'react';
import { useAppStore } from '@/src/store';
import { cn } from '@/src/lib/utils';

export interface ConstellationNode {
  id: string;
  label: string;
  /** core | pack | flow | profile (controls colour + size) */
  kind: 'core' | 'pack' | 'flow' | 'profile';
  /** 0..1 — angular position around the kernel core */
  angle?: number;
  /** distance from centre in 0..1 (1 = canvas edge) */
  distance?: number;
  /** active / dimmed state */
  active?: boolean;
}

export interface ConstellationEdge {
  from: string;
  to: string;
  active?: boolean;
}

interface ConstellationMapProps {
  nodes: ConstellationNode[];
  edges?: ConstellationEdge[];
  className?: string;
  height?: number;
  caption?: string;
}

const COLORS = {
  core: '#f5d27a',
  pack: '#7c93ff',
  flow: '#c66bff',
  profile: '#5be7c4',
};

/**
 * Canvas2D-rendered constellation map.
 *
 * Used on the Dashboard hero to visualise the kernel + active packs / flows
 * as a small star system. Plain canvas keeps the map crisp and avoids SVG
 * (per project guidance) while staying performant and themeable via CSS
 * custom properties.
 */
export function ConstellationMap({
  nodes,
  edges = [],
  className,
  height = 240,
  caption,
}: ConstellationMapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationRef = useRef<number | null>(null);
  const theme = useAppStore((state) => state.theme);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    let last = performance.now();

    const placement = nodes.map((node, idx) => {
      const angle = node.angle ?? (idx / Math.max(1, nodes.length - 1)) * Math.PI * 2;
      const distance = node.distance ?? (node.kind === 'core' ? 0 : 0.55 + (idx % 3) * 0.12);
      return { ...node, angle, distance };
    });

    const idToPlacement = new Map(placement.map((node) => [node.id, node]));

    const draw = (now: number) => {
      const dt = now - last;
      last = now;

      const rect = canvas.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.42;

      ctx.clearRect(0, 0, rect.width, rect.height);

      // Soft radial halo
      const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.4);
      halo.addColorStop(0, 'rgba(245, 210, 122, 0.20)');
      halo.addColorStop(0.55, 'rgba(124, 147, 255, 0.07)');
      halo.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, rect.width, rect.height);

      // Edges
      for (const edge of edges) {
        const a = idToPlacement.get(edge.from);
        const b = idToPlacement.get(edge.to);
        if (!a || !b) continue;
        const ax = cx + Math.cos(a.angle ?? 0) * radius * (a.distance ?? 0);
        const ay = cy + Math.sin(a.angle ?? 0) * radius * (a.distance ?? 0);
        const bx = cx + Math.cos(b.angle ?? 0) * radius * (b.distance ?? 0);
        const by = cy + Math.sin(b.angle ?? 0) * radius * (b.distance ?? 0);

        const grad = ctx.createLinearGradient(ax, ay, bx, by);
        const alpha = edge.active ? 0.8 : 0.32;
        grad.addColorStop(0, `rgba(245, 210, 122, ${alpha})`);
        grad.addColorStop(1, `rgba(124, 147, 255, ${alpha})`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = edge.active ? 1.6 : 1.0;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }

      // Nodes
      const breathe = (Math.sin(now / 800) + 1) / 2; // 0..1
      for (const node of placement) {
        const x = cx + Math.cos(node.angle ?? 0) * radius * (node.distance ?? 0);
        const y = cy + Math.sin(node.angle ?? 0) * radius * (node.distance ?? 0);
        const isCore = node.kind === 'core';
        const baseSize = isCore ? 7 : 4;
        const size = baseSize + breathe * (isCore ? 2.6 : 1.2);
        const colour = COLORS[node.kind] ?? COLORS.pack;

        // outer glow
        const glow = ctx.createRadialGradient(x, y, 0, x, y, size * 6);
        glow.addColorStop(0, hexWithAlpha(colour, node.active === false ? 0.25 : 0.85));
        glow.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, size * 6, 0, Math.PI * 2);
        ctx.fill();

        // core dot
        ctx.fillStyle = colour;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();

        // label
        if (node.label) {
          ctx.fillStyle = node.active === false
            ? 'rgba(255,255,255,0.45)'
            : 'rgba(255,255,255,0.85)';
          ctx.font = `${isCore ? 600 : 500} ${isCore ? 12 : 11}px Inter, system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(node.label, x, y + size + 6);
        }
      }

      // Outer orbit ring
      ctx.strokeStyle = 'rgba(245, 210, 122, 0.18)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.95, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(124, 147, 255, 0.14)';
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.55, 0, Math.PI * 2);
      ctx.stroke();

      // touch dt to satisfy linter
      void dt;

      animationRef.current = requestAnimationFrame(draw);
    };

    animationRef.current = requestAnimationFrame(draw);

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      observer.disconnect();
    };
  }, [nodes, edges, theme]);

  return (
    <div className={cn('cosmos-canvas relative overflow-hidden', className)} style={{ height }}>
      <canvas ref={canvasRef} className="block h-full w-full" aria-label={caption ?? 'Constellation map'} />
      {caption && (
        <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
          {caption}
        </div>
      )}
    </div>
  );
}

function hexWithAlpha(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const bigint = parseInt(value.length === 3
    ? value.split('').map((c) => c + c).join('')
    : value, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
