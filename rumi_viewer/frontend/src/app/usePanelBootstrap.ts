import { useEffect } from 'react';

import { useAppStore } from '@/src/store';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';

function usePanelThemeClass() {
  const theme = useAppStore(state => state.theme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('theme-rumi', 'theme-minimal', 'theme-standard', 'theme-rounded');
    root.classList.add(`theme-${theme.toLowerCase()}`);
  }, [theme]);
}

function usePanelColorModeClass() {
  const colorMode = useAppStore(state => state.colorMode);

  useEffect(() => {
    const root = document.documentElement;
    if (colorMode === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [colorMode]);
}

function usePanelSessionBootstrap() {
  const addToast = useAppStore(state => state.addToast);

  useEffect(() => {
    if (!hasPendingPanelBootstrapCode()) {
      return;
    }

    void bootstrapPanelSession().catch((error) => {
      const message = error instanceof Error ? error.message : 'Panel bootstrap failed';
      addToast(message, 'error');
    });
  }, [addToast]);
}

function useRuntimeReadinessPolling() {
  const refreshRuntimeHealth = useAppStore(state => state.refreshRuntimeHealth);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const pollRuntimeReadiness = async () => {
      while (!cancelled) {
        await refreshRuntimeHealth();
        if (cancelled) {
          return;
        }
        const currentState = useAppStore.getState();
        if (currentState.runtimeReady || currentState.runtimeStatus === 'error') {
          return;
        }
        await new Promise<void>((resolve) => {
          timer = window.setTimeout(resolve, 250);
        });
      }
    };

    void pollRuntimeReadiness();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [refreshRuntimeHealth, runtimeReady, runtimeStatus]);
}

export function usePanelBootstrap() {
  usePanelThemeClass();
  usePanelColorModeClass();
  usePanelSessionBootstrap();
  useRuntimeReadinessPolling();
}
