import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { COSMOS_SFX, type CosmosSfxKey } from './assets';

const STORAGE_KEY = 'rumi-cosmos-sound';
const DEFAULT_VOLUMES: Record<CosmosSfxKey, number> = {
  boot: 0.55,
  click: 0.18,
  nav: 0.22,
  success: 0.32,
  error: 0.32,
  launch: 0.42,
  ambient: 0.18,
};

interface SoundContextValue {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  toggle: () => void;
  play: (key: CosmosSfxKey) => void;
  stop: (key: CosmosSfxKey) => void;
}

const SoundContext = createContext<SoundContextValue | null>(null);

function readInitialEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === '1' || raw === 'true';
}

interface SoundProviderProps {
  children: ReactNode;
}

/**
 * Provides a tiny, dependency-free SFX layer used by the Cosmos UI. Each
 * sound key maps to a single `<audio>` element pooled per provider. Missing
 * audio files are tolerated silently (so the UI ships before assets exist).
 *
 * Sounds are gated behind a localStorage flag (default OFF) and the user
 * can toggle from Settings.
 */
export function SoundProvider({ children }: SoundProviderProps) {
  const [enabled, setEnabledState] = useState<boolean>(() => readInitialEnabled());
  const audiosRef = useRef<Partial<Record<CosmosSfxKey, HTMLAudioElement>>>({});

  // Lazily build the audio elements client-side
  useEffect(() => {
    (Object.keys(COSMOS_SFX) as CosmosSfxKey[]).forEach((key) => {
      if (audiosRef.current[key]) return;
      const audio = new Audio(COSMOS_SFX[key]);
      audio.preload = 'none';
      audio.volume = DEFAULT_VOLUMES[key] ?? 0.3;
      // Suppress the autoplay-policy warning by failing silently
      audio.addEventListener('error', () => {
        /* assets may not exist yet — that's expected */
      });
      audiosRef.current[key] = audio;
    });
  }, []);

  const setEnabled = (next: boolean) => {
    setEnabledState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* private mode etc. — swallow */
    }
  };

  const value = useMemo<SoundContextValue>(() => ({
    enabled,
    setEnabled,
    toggle: () => setEnabled(!enabled),
    play(key) {
      if (!enabled) return;
      const audio = audiosRef.current[key];
      if (!audio) return;
      try {
        audio.currentTime = 0;
        const promise = audio.play();
        if (promise && typeof promise.catch === 'function') {
          promise.catch(() => {
            // Browser blocked autoplay or asset is missing — ignore.
          });
        }
      } catch {
        /* swallow */
      }
    },
    stop(key) {
      const audio = audiosRef.current[key];
      if (!audio) return;
      try {
        audio.pause();
        audio.currentTime = 0;
      } catch {
        /* swallow */
      }
    },
  }), [enabled]);

  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}

export function useCosmosSound(): SoundContextValue {
  const ctx = useContext(SoundContext);
  if (!ctx) {
    // Provide a no-op fallback so components don't need to assert
    return {
      enabled: false,
      setEnabled: () => {},
      toggle: () => {},
      play: () => {},
      stop: () => {},
    };
  }
  return ctx;
}
