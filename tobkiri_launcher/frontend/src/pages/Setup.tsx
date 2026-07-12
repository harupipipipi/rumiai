import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Button } from '@/src/components/ui/Button';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';
import {
  SETUP_PACK_RETURN_PARAM,
  hasSelectedSetupPack,
  setupPackSelectionUrl,
} from '@/src/lib/setupPacks';
import { Loader2, CheckCircle2 } from 'lucide-react';
import { LAUNCHER_DISPLAY_NAME } from '@/src/lib/launcherBrand';

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
  const [setupPackError, setSetupPackError] = useState<string | null>(null);

  const finalizeSetup = async (): Promise<boolean> => {
    if (!await hasSelectedSetupPack()) {
      return false;
    }
    setSetupDone(true);
    return true;
  };

  const openSetupPackSelection = () => {
    window.location.assign(setupPackSelectionUrl());
  };

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

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
      let timer: ReturnType<typeof setTimeout> | null = null;
      setLoading(true);
      void finalizeSetup()
        .then((completed) => {
          if (!alive) return;
          if (!completed) {
            openSetupPackSelection();
            return;
          }
          setLinked(true);
          addToast(t('setup.link_success') || 'Account linked successfully!', 'success');
          timer = setTimeout(() => {
            navigate(panelRoutes.home);
          }, 1500);
        })
        .catch((setupError) => {
          if (!alive) return;
          setSetupPackError(setupError instanceof Error ? setupError.message : 'Setup pack selection failed');
          setLoading(false);
        });
      return () => {
        alive = false;
        if (timer) clearTimeout(timer);
      };
    }

    if (error) {
      addToast(`OAuth error: ${error}`, 'error');
    }
  }, [searchParams, addToast, navigate, t]);

  useEffect(() => {
    if (searchParams.get(SETUP_PACK_RETURN_PARAM) !== '1') {
      return;
    }

    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setLoading(true);
    void finalizeSetup()
      .then((completed) => {
        if (!alive) return;
        if (!completed) {
          setSetupPackError('Choose and install a setup pack before opening the panel.');
          setLoading(false);
          return;
        }
        setLinked(true);
        addToast(t('setup.link_success') || 'Account linked successfully!', 'success');
        timer = setTimeout(() => {
          navigate(panelRoutes.home);
        }, 800);
      })
      .catch((setupError) => {
        if (!alive) return;
        setSetupPackError(setupError instanceof Error ? setupError.message : 'Setup pack selection failed');
        setLoading(false);
      });

    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [searchParams, addToast, navigate, t]);

  useEffect(() => {
    if (!profile.connected || linked || searchParams.get(SETUP_PACK_RETURN_PARAM) === '1') {
      return;
    }

    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setLoading(true);
    void finalizeSetup()
      .then((completed) => {
        if (!alive) return;
        if (!completed) {
          openSetupPackSelection();
          return;
        }
        setLinked(true);
        addToast(t('setup.link_success') || 'Account linked successfully!', 'success');
        timer = setTimeout(() => {
          navigate(panelRoutes.home);
        }, 1500);
      })
      .catch(() => {
        if (!alive) return;
        addToast(t('setup.connect_failed') || 'Failed to connect', 'error');
        setLoading(false);
      });

    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [profile.connected, linked, searchParams, addToast, navigate, t]);

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

  if (linked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-main p-6">
        <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center page-enter">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950/30">
            <CheckCircle2 className="h-7 w-7 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-text-main">{t('setup.linked_title') || 'Account Linked!'}</h1>
            <p className="mt-2 text-sm text-text-muted">{t('setup.redirecting') || 'Redirecting to dashboard...'}</p>
          </div>
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-main p-6">
      <div className="flex w-full max-w-md flex-col items-center gap-10 text-center page-enter">
        {/* Logo + Title */}
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/10">
            <span className="text-2xl font-bold text-accent">T</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-main">Welcome to {LAUNCHER_DISPLAY_NAME}</h1>
            <p className="mt-2 text-sm text-text-muted">{t('setup.subtitle')}</p>
          </div>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-8 rounded-full bg-accent" />
          <div className="h-1.5 w-8 rounded-full bg-border" />
        </div>

        {/* Actions: primary right, secondary left */}
        <div className="flex w-full flex-col gap-3">
          <Button size="lg" className="w-full" onClick={handleConnect} disabled={loading} loading={loading}>
            {t('setup.connect_rumi')}
          </Button>
          {setupPackError ? (
            <p className="text-sm text-red-500">{setupPackError}</p>
          ) : null}
          <div className="flex justify-start">
            <Button variant="ghost" onClick={handleSkip} disabled={loading}>
              {t('setup.choose_packs')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
