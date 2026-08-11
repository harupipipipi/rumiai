import {useCallback, useEffect, useState} from 'react';
import {useNavigate} from 'react-router';
import {CheckCircle2} from 'lucide-react';
import {useAppStore} from '@/src/store';
import {Button} from '@/src/components/ui/Button';
import {PresentationSelector} from '@/src/components/presentation/PresentationSelector';
import {TobkiriLoadingMark} from '@/src/components/ui/TobkiriLoader';
import {panelRoutes} from '@/src/lib/routes';
import {
  activateDefaultsProfile,
  fetchDefaultsSetupState,
  type DefaultsSetupState,
} from '@/src/lib/defaultsSetup';
import {
  activateDefaultsWithRecovery,
  recoverDefaultsActivation,
} from '@/src/lib/defaultsActivationRecovery';
import {
  fetchPresentationState,
  launchSelectedPresentation,
  selectPresentation,
} from '@/src/lib/api';
import {refreshMountedRuntimeSurfaces} from '@/src/lib/runtimeSurfaceRefresh';
import type {ApiPresentationSelection, ApiPresentationState} from '@/src/lib/apiTypes';
import {
  defaultPresentationSelection,
  normalizePresentationSelection,
} from '@/src/lib/presentation';
import {LAUNCHER_DISPLAY_NAME} from '@/src/lib/launcherBrand';
import {DefaultsReview} from './DefaultsReview';

function message(error: unknown, fallback: string): string {
  if (typeof error === 'string' && error.trim()) return error;
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

export function Setup() {
  const navigate = useNavigate();
  const setSetupDone = useAppStore((state) => state.setSetupDone);
  const addToast = useAppStore((state) => state.addToast);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const refreshRuntimeHealth = useAppStore((state) => state.refreshRuntimeHealth);
  const refreshPackVMDoctor = useAppStore((state) => state.refreshPackVMDoctor);
  const loadPacks = useAppStore((state) => state.loadPacks);
  const loadFrontendCatalog = useAppStore((state) => state.loadFrontendCatalog);
  const [setup, setSetup] = useState<DefaultsSetupState | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [activating, setActivating] = useState(false);
  const [activationCommitted, setActivationCommitted] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [reconciliationError, setReconciliationError] = useState<string | null>(null);
  const [presentation, setPresentation] = useState<ApiPresentationState | null>(null);
  const [selection, setSelection] = useState<ApiPresentationSelection | null>(null);
  const [presentationLoading, setPresentationLoading] = useState(false);
  const [presentationSaving, setPresentationSaving] = useState(false);
  const [presentationLaunching, setPresentationLaunching] = useState(false);
  const [presentationError, setPresentationError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const profileReconfirmationRequired = runtimeStatus === 'profile_reconfirmation_required';

  const loadPresentation = useCallback(async () => {
    setPresentationLoading(true);
    setPresentationError(null);
    try {
      const next = await fetchPresentationState();
      setPresentation(next);
      setSelection(
        normalizePresentationSelection(next.catalog, next.selection)
          ?? defaultPresentationSelection(next.catalog),
      );
    } catch (error) {
      setPresentationError(message(error, 'Presentation catalog could not be loaded.'));
    } finally {
      setPresentationLoading(false);
    }
  }, []);

  useEffect(() => {
    let live = true;
    void fetchDefaultsSetupState()
      .then((next) => {
        if (!live) return;
        setSetup(next);
        setActivationCommitted(next.state === 'active');
        if (next.state === 'active') void loadPresentation();
      })
      .catch((error) => {
        if (live) setSetupError(message(error, 'Defaults Profile could not be loaded.'));
      });
    return () => { live = false; };
  }, [loadPresentation]);

  const reconcileActiveRuntime = useCallback(async () => {
      await refreshRuntimeHealth();
      if (useAppStore.getState().runtimeStatus !== 'runtime_ready') {
        throw new Error(
          'Defaults activation completed without a verified runtime dispatch map. Retry after the Host is ready.',
        );
      }
      const packVmDoctor = await refreshPackVMDoctor();
      if (!packVmDoctor?.ready) {
        throw new Error(
          'Defaults activation completed, but PackVM readiness could not be verified.',
        );
      }
      await Promise.all([
        loadPacks(true, {skipMutationReconciliation: true}),
        loadFrontendCatalog(true),
      ]);
      const refreshedState = useAppStore.getState();
      if (refreshedState.packsError || refreshedState.frontendCatalogError) {
        throw new Error('Authoritative Pack projections could not be reconciled.');
      }
      await refreshMountedRuntimeSurfaces();
  }, [loadFrontendCatalog, loadPacks, refreshMountedRuntimeSurfaces, refreshPackVMDoctor, refreshRuntimeHealth]);

  const applyRecoveryResult = useCallback(async (
    result: Awaited<ReturnType<typeof recoverDefaultsActivation>>,
  ) => {
    setSetup(result.state);
    setReviewed(false);
    setActivationCommitted(result.activationCommitted);
    const failure = result.error
      ? message(result.error, 'Defaults activation reconciliation failed.')
      : null;
    if (result.state?.state === 'active') {
      setSetupError(null);
      setReconciliationError(failure);
      if (failure) {
        addToast(failure, 'error');
      } else {
        await loadPresentation();
      }
      return;
    }
    setReconciliationError(null);
    setSetupError(failure);
    if (failure) addToast(failure, 'error');
  }, [addToast, loadPresentation]);

  const recoverActivation = useCallback(async () => {
    if (activating) return;
    setActivating(true);
    setSetupError(null);
    const result = await recoverDefaultsActivation({
      fetchAuthoritativeSetup: fetchDefaultsSetupState,
      reconcileActiveRuntime,
    });
    try {
      await applyRecoveryResult(result);
    } finally {
      setActivating(false);
    }
  }, [activating, applyRecoveryResult, reconcileActiveRuntime]);

  const activate = async () => {
    if (activationCommitted || !setup || setup.state !== 'review_required' || !reviewed) return;
    setActivating(true);
    setSetupError(null);
    const result = await activateDefaultsWithRecovery({
      submitActivation: () => activateDefaultsProfile(setup.recommended_default_profile.confirmation),
      fetchAuthoritativeSetup: fetchDefaultsSetupState,
      reconcileActiveRuntime,
    });
    try {
      await applyRecoveryResult(result);
    } finally {
      setActivating(false);
    }
  };

  const savePresentation = async (nextSelection: ApiPresentationSelection) => {
    setPresentationSaving(true);
    setPresentationError(null);
    try {
      const next = await selectPresentation(nextSelection);
      setPresentation(next);
      setSelection(next.selection ?? nextSelection);
      setSetupDone(true);
      setComplete(true);
      window.setTimeout(() => navigate(panelRoutes.home), 500);
    } catch (error) {
      setPresentationError(message(error, 'Presentation selection could not be saved.'));
    } finally {
      setPresentationSaving(false);
    }
  };

  const launchPresentation = async () => {
    setPresentationLaunching(true);
    setPresentationError(null);
    try {
      const result = await launchSelectedPresentation();
      addToast(result.message || 'Selected Shell launched.', 'success');
    } catch (error) {
      setPresentationError(message(error, 'Selected Shell launch was blocked.'));
    } finally {
      setPresentationLaunching(false);
    }
  };

  if (complete) {
    return <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-bg-main text-center">
      <CheckCircle2 className="h-12 w-12 text-emerald-500" />
      <h1 className="text-xl font-semibold text-text-main">Runtime Ready</h1>
      <TobkiriLoadingMark scene="startup" />
    </div>;
  }

  if (setup?.state === 'active') {
    return <div className="min-h-screen bg-bg-main px-6 py-10"><div className="mx-auto max-w-4xl">
      <Header />
      {reconciliationError ? <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-500">
        <p className="font-medium text-text-main">Activation is verified; runtime surfaces need reconciliation.</p>
        <p className="mt-2">{reconciliationError}</p>
        <div className="mt-4"><Button variant="outline" onClick={() => void recoverActivation()} loading={activating}>Retry runtime reconciliation</Button></div>
      </div> : presentation ? <PresentationSelector
        state={presentation}
        selection={selection}
        saving={presentationSaving}
        launching={presentationLaunching}
        error={presentationError}
        onSelectionChange={setSelection}
        onSave={savePresentation}
        onLaunch={launchPresentation}
      /> : <div role={presentationError ? 'alert' : 'status'} className="rounded-xl border border-border bg-bg-card p-6 text-sm text-text-muted">
        {presentationError ?? 'Loading selected presentation…'}
        {presentationError && <div className="mt-4"><Button variant="outline" onClick={() => void loadPresentation()} loading={presentationLoading}>Retry</Button></div>}
      </div>}
    </div></div>;
  }

  return <div className="min-h-screen bg-bg-main px-6 py-10"><div className="mx-auto max-w-3xl">
    <Header />
    <DefaultsReview
      setup={setup}
      reviewed={reviewed}
      activating={activating}
      activationCommitted={activationCommitted}
      error={setupError}
      reconfirmationRequired={profileReconfirmationRequired}
      onRecover={() => void recoverActivation()}
      onReviewedChange={setReviewed}
      onActivate={() => void activate()}
    />
  </div></div>;
}

function Header() {
  return <div className="mb-8 flex items-center gap-3 text-sm font-semibold text-text-main">
    <img src="/panel/assets/tobkiri-launcher-icon.png" alt="Tobkiri" data-asset-trust="bundled" className="h-9 w-9 rounded-lg border border-border" />
    {LAUNCHER_DISPLAY_NAME}
  </div>;
}
