import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { CosmosLogo } from './CosmosLogo';
import { useCosmosSound } from './SoundProvider';
import { useAppStore } from '@/src/store';

const STORAGE_KEY = 'rumi-cosmos-boot-played';
const MIN_DISPLAY_MS = 2400;
const MAX_DISPLAY_MS = 8000;

const PHASES = [
  { key: 'awake', label: 'Awakening Rumi…', duration: 700 },
  { key: 'calibrate', label: 'Calibrating constellations…', duration: 900 },
  { key: 'kernel', label: 'Aligning Kernel orbit…', duration: 800 },
  { key: 'packs', label: 'Linking pack systems…', duration: 700 },
  { key: 'ready', label: 'Ready', duration: 600 },
] as const;

interface BootSequenceProps {
  /** When true, force-show the boot overlay (for dev / Settings preview). */
  forceShow?: boolean;
  /** Callback fired once the overlay has fully exited. */
  onComplete?: () => void;
}

/**
 * Full-screen cinematic intro shown the first time the panel mounts.
 *
 *   1. A single golden point pulses in the centre.
 *   2. It expands into an orbit ring while the Rumi emblem fades in.
 *   3. Status copy advances through PHASES.
 *   4. Once `runtimeReady` is true (or MAX_DISPLAY_MS elapses) the overlay
 *      slides up and fades out, revealing the app underneath.
 *
 * The overlay respects `prefers-reduced-motion` and uses `motion/react`
 * for the macro transitions; pure CSS keyframes drive the looping bits.
 */
export function BootSequence({ forceShow, onComplete }: BootSequenceProps) {
  const runtimeReady = useAppStore((state) => state.runtimeReady);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const theme = useAppStore((state) => state.theme);
  const sound = useCosmosSound();

  const [visible, setVisible] = useState<boolean>(() => {
    if (forceShow) return true;
    if (typeof window === 'undefined') return false;
    return window.sessionStorage.getItem(STORAGE_KEY) !== '1';
  });
  const [phaseIndex, setPhaseIndex] = useState(0);
  const startedAtRef = useRef<number>(Date.now());
  const playedSoundRef = useRef<boolean>(false);

  // Lock background scroll while showing
  useEffect(() => {
    if (!visible) return;
    document.documentElement.classList.add('cosmos-boot-locked');
    return () => {
      document.documentElement.classList.remove('cosmos-boot-locked');
    };
  }, [visible]);

  // Play boot SFX on first appear (only if user opted in and supports autoplay)
  useEffect(() => {
    if (!visible || playedSoundRef.current) return;
    playedSoundRef.current = true;
    sound.play('boot');
  }, [visible, sound]);

  // Phase transitions
  useEffect(() => {
    if (!visible) return;
    if (phaseIndex >= PHASES.length - 1) return;
    const phase = PHASES[phaseIndex];
    const timer = window.setTimeout(() => {
      setPhaseIndex((index) => Math.min(index + 1, PHASES.length - 1));
    }, phase.duration);
    return () => window.clearTimeout(timer);
  }, [phaseIndex, visible]);

  // Dismiss when ready (with a minimum display time)
  useEffect(() => {
    if (!visible) return;
    if (forceShow) return;

    const elapsed = Date.now() - startedAtRef.current;
    const isFinalPhase = phaseIndex >= PHASES.length - 1;

    if ((runtimeReady || runtimeStatus === 'panel_ready') && elapsed >= MIN_DISPLAY_MS && isFinalPhase) {
      const dismissAfter = window.setTimeout(() => setVisible(false), 320);
      return () => window.clearTimeout(dismissAfter);
    }

    const fallback = window.setTimeout(() => setVisible(false), MAX_DISPLAY_MS);
    return () => window.clearTimeout(fallback);
  }, [forceShow, phaseIndex, runtimeReady, runtimeStatus, visible]);

  // Persist that we've shown the boot for this session
  useEffect(() => {
    if (visible) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore */
    }
  }, [visible]);

  if (theme !== 'Cosmos' && !forceShow) return null;

  return (
    <AnimatePresence onExitComplete={onComplete}>
      {visible && (
        <motion.div
          key="cosmos-boot"
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, y: -32, transition: { duration: 0.65, ease: [0.22, 1, 0.36, 1] } }}
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden"
          style={{
            background:
              'radial-gradient(ellipse at center, #0c1230 0%, #04060f 70%, #02030a 100%)',
            color: '#f3f1ff',
          }}
        >
          {/* CSS-only star wash to ensure depth even before art assets land */}
          <div className="cosmos-stars-css" />

          {/* Outer orbit ring */}
          <motion.div
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 0.55 }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            className="absolute aspect-square w-[520px] max-w-[80vw] rounded-full border border-[var(--cosmos-gold)]/30 cosmos-anim-orbit"
            style={{ animationDuration: '60s' }}
          />
          <motion.div
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 0.4 }}
            transition={{ duration: 1.4, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
            className="absolute aspect-square w-[340px] max-w-[60vw] rounded-full border border-[var(--cosmos-blue)]/30 cosmos-anim-orbit-reverse"
            style={{ animationDuration: '38s' }}
          />

          {/* Central emblem stack */}
          <motion.div
            initial={{ scale: 0.4, opacity: 0, filter: 'blur(20px)' }}
            animate={{ scale: 1, opacity: 1, filter: 'blur(0px)' }}
            transition={{ duration: 0.95, ease: [0.22, 1, 0.36, 1] }}
            className="relative z-10 flex flex-col items-center gap-6"
          >
            <div className="cosmos-anim-pulse rounded-full p-3">
              <CosmosLogo size={128} glow />
            </div>

            <motion.h1
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.4 }}
              className="cosmos-text-gradient font-display text-4xl font-semibold tracking-wide sm:text-5xl"
            >
              Rumi AI
            </motion.h1>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.85 }}
              transition={{ duration: 0.6, delay: 0.65 }}
              className="text-sm uppercase tracking-[0.32em] text-[color:var(--text-muted)]"
            >
              a constellation of intelligence
            </motion.p>

            {/* Phase status */}
            <div className="mt-6 flex h-6 items-center justify-center text-xs uppercase tracking-[0.28em] text-[color:var(--cosmos-gold)]/85">
              <AnimatePresence mode="wait">
                <motion.span
                  key={PHASES[phaseIndex].key}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.3 }}
                >
                  {PHASES[phaseIndex].label}
                </motion.span>
              </AnimatePresence>
            </div>

            {/* Progress dots */}
            <div className="mt-4 flex items-center gap-2">
              {PHASES.map((phase, idx) => (
                <span
                  key={phase.key}
                  className="h-1.5 rounded-full transition-all"
                  style={{
                    width: idx === phaseIndex ? 28 : 8,
                    background:
                      idx <= phaseIndex
                        ? 'linear-gradient(90deg, var(--cosmos-gold) 0%, var(--cosmos-magenta) 100%)'
                        : 'rgba(255,255,255,0.18)',
                  }}
                />
              ))}
            </div>
          </motion.div>

          {/* Bottom version copy */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.55 }}
            transition={{ duration: 1, delay: 1.4 }}
            className="absolute bottom-6 text-[11px] uppercase tracking-[0.4em] text-[color:var(--text-muted)]"
          >
            COSMOS · v1
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
