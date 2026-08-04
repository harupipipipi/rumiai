import { useCallback, useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useAppStore } from '@/src/store';
import { Button } from '@/src/components/ui/Button';
import { PresentationSelector } from '@/src/components/presentation/PresentationSelector';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';
import {
  fetchPresentationState,
  launchSelectedPresentation,
  selectPresentation,
} from '@/src/lib/api';
import type {
  ApiPresentationSelection,
  ApiPresentationState,
} from '@/src/lib/apiTypes';
import {
  defaultPresentationSelection,
  normalizePresentationSelection,
} from '@/src/lib/presentation';
import {
  SETUP_PACK_RETURN_PARAM,
  hasSelectedSetupPack,
  setupPackSelectionUrl,
} from '@/src/lib/setupPacks';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { TobkiriLoadingMark } from '@/src/components/ui/TobkiriLoader';
import { motion } from 'motion/react';
import { LAUNCHER_DISPLAY_NAME } from '@/src/lib/launcherBrand';
import tobkiriIconUrl from '../../../assets/app-icon/tobkiri-launcher-icon.png';

const TRUSTED_ASSET_ORIGIN = 'https://tobkiri.invalid';
const TRUSTED_ASSET_PREFIXES = ['/assets/', '/panel/assets/'];
const TRUSTED_LAUNCHER_ICON = /(?:^|\/)tobkiri-launcher-icon(?:-[a-z0-9_-]+)?\.png$/i;

function presentationErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallback;
}

type TrustedImageProps = {
  readonly src: string;
  readonly alt: string;
  readonly 'data-asset-trust': 'bundled';
};

function trustedBundledImageProps(source: unknown, alt: string): TrustedImageProps | null {
  const value = typeof source === 'string' ? source.trim() : '';
  if (
    !value
    || value.length > 2048
    || /[\u0000-\u001f\u007f]/.test(value)
    || value.startsWith('//')
    || /^[a-z][a-z\d+.-]*:/i.test(value)
    || value.split('/').some((segment) => segment === '.' || segment === '..')
  ) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(value, TRUSTED_ASSET_ORIGIN);
  } catch {
    return null;
  }
  if (
    parsed.origin !== TRUSTED_ASSET_ORIGIN
    || parsed.search
    || parsed.hash
    || !TRUSTED_ASSET_PREFIXES.some((prefix) => parsed.pathname.startsWith(prefix))
    || !TRUSTED_LAUNCHER_ICON.test(parsed.pathname)
  ) {
    return null;
  }
  return {src: value, alt, 'data-asset-trust': 'bundled'};
}

const trustedLauncherIcon = trustedBundledImageProps(tobkiriIconUrl, 'Tobkiri');

function LauncherBrandMark() {
  if (!trustedLauncherIcon) {
    return (
      <span
        role="img"
        aria-label="Tobkiri"
        className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-bg-card text-text-main"
      >
        T
      </span>
    );
  }
  return (
    <img
      {...trustedLauncherIcon}
      className="h-9 w-9 rounded-lg border border-border bg-bg-card object-cover"
    />
  );
}

export function Setup() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const connectAccount = useAppStore(state => state.connectAccount);
  const loadProfile = useAppStore(state => state.loadProfile);
  const profile = useAppStore(state => state.profile);
  const addToast = useAppStore(state => state.addToast);
  const t = useT();
  const [loading, setLoading] = useState(false);
  const [linked, setLinked] = useState(false);
  const [setupPackReady, setSetupPackReady] = useState(false);
  const [presentationState, setPresentationState] = useState<ApiPresentationState | null>(null);
  const [presentationSelection, setPresentationSelection] = useState<ApiPresentationSelection | null>(null);
  const [presentationLoading, setPresentationLoading] = useState(false);
  const [presentationSaving, setPresentationSaving] = useState(false);
  const [presentationLaunching, setPresentationLaunching] = useState(false);
  const [presentationError, setPresentationError] = useState<string | null>(null);
  const [setupPackError, setSetupPackError] = useState<string | null>(null);

  const loadPresentation = useCallback(async (): Promise<ApiPresentationState> => {
    setPresentationLoading(true);
    setPresentationError(null);
    try {
      const nextState = await fetchPresentationState();
      const nextSelection = normalizePresentationSelection(nextState.catalog, nextState.selection);
      setPresentationState(nextState);
      setPresentationSelection(nextSelection ?? defaultPresentationSelection(nextState.catalog));
      return nextState;
    } catch (error) {
      const message = presentationErrorMessage(error, 'Presentation catalog could not be loaded.');
      setPresentationError(message);
      throw error;
    } finally {
      setPresentationLoading(false);
    }
  }, []);

  const preparePresentationSetup = useCallback(async (): Promise<boolean> => {
    if (!await hasSelectedSetupPack()) {
      return false;
    }
    setSetupPackReady(true);
    await loadPresentation();
    return true;
  }, [loadPresentation]);

  const openSetupPackSelection = useCallback(() => {
    const colorMode = document.documentElement.dataset.colorMode;
    window.location.assign(setupPackSelectionUrl(undefined, colorMode));
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    let alive = true;
    void hasSelectedSetupPack()
      .then((selected) => {
        if (!alive || !selected) return;
        setSetupPackReady(true);
        void loadPresentation().catch((error: unknown) => {
          if (!alive) return;
          setPresentationError(
            presentationErrorMessage(error, 'Presentation catalog could not be loaded.'),
          );
        });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setSetupPackError(
          presentationErrorMessage(error, 'Setup pack status could not be checked.'),
        );
      });
    return () => {
      alive = false;
    };
  }, [loadPresentation]);

  useEffect(() => {
    const refreshProfile = () => {
      void loadProfile();
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshProfile();
      }
    };

    window.addEventListener('focus', refreshProfile);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.removeEventListener('focus', refreshProfile);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [loadProfile]);

  // Handle OAuth callback redirect params
  useEffect(() => {
    const isLinked = searchParams.get('linked');
    const error = searchParams.get('error');

    if (isLinked === 'true') {
      let alive = true;
      setLoading(true);
      void preparePresentationSetup()
        .then((completed) => {
          if (!alive) return;
          if (!completed) {
            openSetupPackSelection();
            return;
          }
          setLoading(false);
        })
        .catch((setupError) => {
          if (!alive) return;
          setSetupPackError(presentationErrorMessage(setupError, 'Setup pack selection failed'));
          setLoading(false);
        });
      return () => {
        alive = false;
      };
    }

    if (error) {
      addToast(`OAuth error: ${error}`, 'error');
    }
  }, [searchParams, preparePresentationSetup, openSetupPackSelection]);

  useEffect(() => {
    if (searchParams.get(SETUP_PACK_RETURN_PARAM) !== '1') {
      return;
    }

    let alive = true;
    setLoading(true);
    void preparePresentationSetup()
      .then((completed) => {
        if (!alive) return;
        if (!completed) {
          setSetupPackError('Choose and install a setup pack before opening the panel.');
          setLoading(false);
          return;
        }
        setLoading(false);
      })
      .catch((setupError) => {
        if (!alive) return;
        setSetupPackError(presentationErrorMessage(setupError, 'Setup pack selection failed'));
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [searchParams, preparePresentationSetup, openSetupPackSelection]);

  useEffect(() => {
    if (!profile.connected || linked || searchParams.get(SETUP_PACK_RETURN_PARAM) === '1') {
      return;
    }

    let alive = true;
    setLoading(true);
    void preparePresentationSetup()
      .then((completed) => {
        if (!alive) return;
        if (!completed) {
          openSetupPackSelection();
          return;
        }
        setLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        addToast(t('setup.connect_failed') || 'Failed to connect', 'error');
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [profile.connected, linked, searchParams, preparePresentationSetup, openSetupPackSelection, addToast, t]);

  const handleConnect = async () => {
    setLoading(true);
    try {
      await connectAccount();
      addToast(
        t('setup.connect_started') || 'Browser opened. Finish signing in there, then return.',
        'success',
      );
    } catch {
      addToast(t('setup.connect_failed') || 'Failed to connect', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = () => {
    setSetupPackError(null);
    openSetupPackSelection();
  };

  const handlePresentationSave = async (selection: ApiPresentationSelection) => {
    setPresentationSaving(true);
    setPresentationError(null);
    try {
      const nextState = await selectPresentation(selection);
      setPresentationState(nextState);
      setPresentationSelection(nextState.selection ?? selection);
      setSetupDone(true);
      setLinked(true);
      addToast(t('setup.link_success') || 'Tobkiri Launcher setup saved.', 'success');
      window.setTimeout(() => navigate(panelRoutes.home), 800);
    } catch (error) {
      const message = presentationErrorMessage(error, 'Presentation selection could not be saved.');
      setPresentationError(message);
      addToast(message, 'error');
    } finally {
      setPresentationSaving(false);
    }
  };

  const handlePresentationLaunch = async () => {
    setPresentationLaunching(true);
    setPresentationError(null);
    try {
      const result = await launchSelectedPresentation();
      addToast(result.message || 'Selected Shell launched.', 'success');
    } catch (error) {
      const message = presentationErrorMessage(error, 'Selected Shell launch was blocked.');
      setPresentationError(message);
      addToast(message, 'error');
    } finally {
      setPresentationLaunching(false);
    }
  };

  if (linked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-main p-6">
        <motion.div initial={{opacity: 0, scale: .96}} animate={{opacity: 1, scale: 1}} className="relative flex w-full max-w-sm flex-col items-center gap-6 text-center">
          <motion.div initial={{scale: .8}} animate={{scale: 1}} transition={{type: 'spring', stiffness: 260, damping: 22}} className="flex h-14 w-14 items-center justify-center rounded-xl border border-border bg-bg-card">
            <CheckCircle2 className="h-9 w-9 text-emerald-500" />
          </motion.div>
          <div>
            <h1 className="text-xl font-semibold text-text-main">{t('setup.linked_title') || 'Account Linked!'}</h1>
            <p className="mt-2 text-sm text-text-muted">{t('setup.redirecting') || 'Redirecting to dashboard...'}</p>
          </div>
          <TobkiriLoadingMark scene="startup" />
        </motion.div>
      </div>
    );
  }

  if (setupPackReady) {
    return (
      <div className="min-h-screen bg-bg-main px-6 py-10">
        <div className="mx-auto w-full max-w-4xl">
          <div className="mb-8 flex items-center gap-3 text-sm font-semibold text-text-main">
            <LauncherBrandMark />
            {LAUNCHER_DISPLAY_NAME}
          </div>
          {presentationLoading && !presentationState ? (
            <div role="status" className="rounded-xl border border-border bg-bg-card p-6 text-sm text-text-muted">
              Loading verified Base Pack and Shell metadata…
            </div>
          ) : presentationState ? (
            <PresentationSelector
              state={presentationState}
              selection={presentationSelection}
              saving={presentationSaving}
              launching={presentationLaunching}
              error={presentationError}
              onSelectionChange={setPresentationSelection}
              onSave={handlePresentationSave}
              onLaunch={handlePresentationLaunch}
            />
          ) : (
            <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm text-text-muted">
              {presentationError || 'The Launcher could not load the presentation catalog.'}
              <div className="mt-4">
                <Button type="button" variant="outline" onClick={() => void loadPresentation()} loading={presentationLoading}>
                  Retry
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-bg-main">
      <div className="mx-auto grid w-full max-w-4xl items-center gap-10 px-6 py-10 lg:grid-cols-[1fr_400px]">
        <motion.section initial={{opacity: 0, x: -18}} animate={{opacity: 1, x: 0}} transition={{duration: .45}} className="max-w-xl">
          <div className="mb-10 flex items-center gap-3 text-sm font-semibold text-text-main">
            <LauncherBrandMark />
            {LAUNCHER_DISPLAY_NAME}
          </div>
          <div>
            <span className="text-xs font-medium text-text-muted">初期設定</span>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-.035em] text-text-main sm:text-4xl">Tobkiriをセットアップ</h1>
            <p className="mt-4 max-w-md text-sm leading-7 text-text-muted">アカウント、Base Pack、互換Shellを設定します。選択したpresentationはあとから変更できます。</p>
          </div>
          <div className="mt-9 space-y-3 border-l border-border pl-4 text-xs leading-5 text-text-muted">
            <p>1. アカウントを接続</p>
            <p>2. Base Packと互換Shellを確認</p>
          </div>
        </motion.section>

        <motion.section initial={{opacity: 0, y: 14}} animate={{opacity: 1, y: 0}} transition={{delay: .06, duration: .36}} className="rounded-[18px] border border-border bg-bg-card p-6 shadow-lg sm:p-7">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted">初期セットアップ</span>
            <span className="rounded-full border border-border bg-bg-main px-2.5 py-1 text-[10px] font-semibold text-text-muted">1 / 2</span>
          </div>
          <div className="mt-4 flex gap-1.5"><i className="h-1 flex-1 rounded-full bg-text-main" /><i className="h-1 flex-1 rounded-full bg-border" /></div>
          <h2 className="mt-7 text-lg font-semibold text-text-main">アカウント</h2>
          <p className="mt-2 text-sm leading-6 text-text-muted">接続するとプロファイルを同期できます。接続せずにpack選択へ進むこともできます。</p>
          <div className="mt-7 flex flex-col gap-3">
            <Button size="lg" className="w-full justify-between" onClick={handleConnect} disabled={loading} loading={loading}>
              <span>{t('setup.connect_rumi')}</span>{!loading && <ArrowRight className="h-4 w-4" />}
            </Button>
            <Button variant="outline" size="lg" className="w-full" onClick={handleSkip} disabled={loading}>{t('setup.choose_packs')}</Button>
          </div>
          {setupPackError && <p className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-500">{setupPackError}</p>}
          <p className="mt-6 border-t border-border pt-4 text-xs leading-5 text-text-muted">Base PackはHost authorityを付与しません。ShellのProvider trust、authority mode、production artifactを次の画面で確認します。</p>
        </motion.section>
      </div>
    </div>
  );
}
