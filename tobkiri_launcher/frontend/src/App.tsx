import {useCallback, useDeferredValue, useEffect, useLayoutEffect, useRef, useState} from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router';
import {
  cancelPackMutationReconciliation,
  useAppStore,
  type RuntimeStatus,
} from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import {
  bootstrapPanelSession,
  hasPendingPanelBootstrapCode,
  reauthorizePanelSession,
} from '@/src/lib/api';
import { applyAppearanceToRoot } from '@/src/lib/appearance';
import { runtimeMonitorDelay } from '@/src/lib/runtimeHealth';
import { panelRoutes } from '@/src/lib/routes';
import { RouteAnnouncer } from '@/src/components/layout/RouteAnnouncer';
import {fetchDefaultsSetupState} from '@/src/lib/defaultsSetup';
import {
  failedSetupState,
  initialSetupVerificationState,
  loadingSetupState,
  SETUP_VERIFICATION_TIMEOUT_MS,
  SetupVerificationSequence,
  type SetupVerificationState,
  verifiedSetupState,
  writeSetupVerificationRecord,
} from '@/src/lib/setupVerification';
import {
  LazyAiInput,
  LazyApiMap,
  LazyFlow,
  LazyGraph,
  LazyPackDetail,
  LazyPacks,
  LazyNodeManager,
  LazyProfile,
  LazyProfileFiles,
  LazyProfileWiring,
  LazySettings,
} from '@/src/lib/routeModules';

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const addToast = useAppStore(state => state.addToast);
  const refreshRuntimeHealth = useAppStore(state => state.refreshRuntimeHealth);
  const [setupVerification, setSetupVerification] = useState(
    () => initialSetupVerificationState(isSetupDone),
  );
  const verificationStateRef = useRef<SetupVerificationState>(setupVerification);
  const verificationSequenceRef = useRef(new SetupVerificationSequence());

  const updateSetupVerification = useCallback((next: SetupVerificationState) => {
    verificationStateRef.current = next;
    setSetupVerification(next);
  }, []);

  const verifyDefaultsProfile = useCallback(async () => {
    const sequence = verificationSequenceRef.current;
    const token = sequence.begin();
    const previous = verificationStateRef.current;
    updateSetupVerification(loadingSetupState(previous));
    try {
      const response = await fetchDefaultsSetupState({
        timeoutMs: SETUP_VERIFICATION_TIMEOUT_MS,
      });
      if (!sequence.isCurrent(token)) return;
      const next = verifiedSetupState(response, Date.now(), previous);
      if (next.kind === 'selected' || next.kind === 'missing') {
        writeSetupVerificationRecord(next);
      }
      updateSetupVerification(next);
      if (next.kind === 'missing') {
        setSetupDone(false);
      }
    } catch (error) {
      if (!sequence.isCurrent(token)) return;
      updateSetupVerification(failedSetupState(error, previous));
    }
  }, [setSetupDone, updateSetupVerification]);

  const reauthorizeSetupVerification = useCallback(async () => {
    const sequence = verificationSequenceRef.current;
    const token = sequence.begin();
    const previous = verificationStateRef.current;
    updateSetupVerification(loadingSetupState(previous));
    try {
      await reauthorizePanelSession();
      if (!sequence.isCurrent(token)) return;
      await verifyDefaultsProfile();
    } catch (error) {
      if (!sequence.isCurrent(token)) return;
      updateSetupVerification(failedSetupState(error, previous));
    }
  }, [updateSetupVerification, verifyDefaultsProfile]);

  useLayoutEffect(() => {
    applyAppearanceToRoot(document.documentElement, { theme, colorMode });
  }, [theme, colorMode]);

  useEffect(() => () => {
    cancelPackMutationReconciliation();
  }, []);

  useEffect(() => {
    if (!hasPendingPanelBootstrapCode()) {
      return;
    }

    void bootstrapPanelSession().catch((error) => {
      const message = error instanceof Error ? error.message : 'Panel bootstrap failed';
      addToast(message, 'error');
    });
  }, [addToast]);

  useEffect(() => {
    if (!isSetupDone) return;
    type IdleWindow = Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (handle: number) => void;
    };
    const target = window as IdleWindow;
    const scheduleVerification = () => {
      void verifyDefaultsProfile();
    };

    let cancelScheduled: () => void;
    if (typeof target.requestIdleCallback === 'function') {
      const handle = target.requestIdleCallback(scheduleVerification, { timeout: 1_000 });
      cancelScheduled = () => target.cancelIdleCallback?.(handle);
    } else {
      const handle = window.setTimeout(scheduleVerification, 300);
      cancelScheduled = () => window.clearTimeout(handle);
    }

    return () => {
      verificationSequenceRef.current.cancel();
      cancelScheduled();
    };
  }, [isSetupDone, verifyDefaultsProfile]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const pollRuntimeHealth = async () => {
      while (!cancelled) {
        await refreshRuntimeHealth();
        if (cancelled) {
          return;
        }
        const currentState = useAppStore.getState();
        await new Promise<void>((resolve) => {
          timer = window.setTimeout(resolve, runtimeMonitorDelay({
            runtimeReady: currentState.runtimeReady,
            runtimeStatus: currentState.runtimeStatus,
            runtimeError: currentState.runtimeError,
            runtimeDisconnected: currentState.runtimeDisconnected,
            lastRuntimeHealthyAt: currentState.lastRuntimeHealthyAt,
          }));
        });
      }
    };

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void refreshRuntimeHealth();
      }
    };

    window.addEventListener('focus', refreshWhenVisible);
    window.addEventListener('online', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    void pollRuntimeHealth();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      window.removeEventListener('focus', refreshWhenVisible);
      window.removeEventListener('online', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [refreshRuntimeHealth]);

  return (
    <BrowserRouter basename="/panel">
      <DeferredRouteTree
        isSetupDone={isSetupDone}
        runtimeStatus={runtimeStatus}
        setupVerification={setupVerification}
        onRetrySetupVerification={() => void verifyDefaultsProfile()}
        onReauthorizeSetupVerification={() => void reauthorizeSetupVerification()}
      />
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}

function DeferredRouteTree({
  isSetupDone,
  runtimeStatus,
  setupVerification,
  onRetrySetupVerification,
  onReauthorizeSetupVerification,
}: {
  isSetupDone: boolean;
  runtimeStatus: RuntimeStatus;
  setupVerification: SetupVerificationState;
  onRetrySetupVerification: () => void;
  onReauthorizeSetupVerification: () => void;
}) {
  const location = useLocation();
  const deferredLocation = useDeferredValue(location);
  const routePending =
    deferredLocation.pathname !== location.pathname ||
    deferredLocation.search !== location.search ||
    deferredLocation.hash !== location.hash;

  return (
    <>
      <RouteAnnouncer pathname={deferredLocation.pathname} />
      <Routes location={deferredLocation}>
        <Route path={panelRoutes.setup} element={<Setup />} />

        <Route
          path={panelRoutes.home}
          element={isSetupDone && runtimeStatus !== 'profile_reconfirmation_required'
            ? <Layout
                setupVerification={setupVerification}
                onRetrySetupVerification={onRetrySetupVerification}
                onReauthorizeSetupVerification={onReauthorizeSetupVerification}
              />
            : <Navigate to={panelRoutes.setup} replace />}
        >
          <Route index element={<Dashboard />} />
          <Route path={panelRoutes.packs.slice(1)} element={<LazyPacks />} />
          <Route path={`${panelRoutes.packs.slice(1)}/:id`} element={<LazyPackDetail />} />
          <Route path={panelRoutes.profile.slice(1)} element={<LazyProfile />} />
          <Route path={panelRoutes.settings.slice(1)} element={<LazySettings />} />
          <Route path={panelRoutes.profileWiring.slice(1)} element={<LazyProfileWiring />} />
          <Route path={panelRoutes.profileFiles.slice(1)} element={<LazyProfileFiles />} />
          <Route path={panelRoutes.flow.slice(1)} element={<LazyFlow />} />
          <Route path={panelRoutes.graph.slice(1)} element={<LazyGraph />} />
          <Route path={panelRoutes.aiInput.slice(1)} element={<LazyAiInput />} />
          <Route path={panelRoutes.apiMap.slice(1)} element={<LazyApiMap />} />
          <Route path={panelRoutes.nodeManager.slice(1)} element={<LazyNodeManager />} />
        </Route>
      </Routes>
      {routePending && (
        <div
          role="status"
          aria-label="Opening page"
          className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5 overflow-hidden bg-accent/15"
        >
          <div className="h-full w-1/3 animate-pulse bg-accent" />
        </div>
      )}
    </>
  );
}
