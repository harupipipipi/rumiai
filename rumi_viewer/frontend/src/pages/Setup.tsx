import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Button } from '@/src/components/ui/Button';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';
import { Loader2, CheckCircle2 } from 'lucide-react';
import { CosmosLogo } from '@/src/cosmos/CosmosLogo';
import { COSMOS_BRAND, hideOnError } from '@/src/cosmos/assets';
import { useCosmosSound } from '@/src/cosmos/SoundProvider';
import { cn } from '@/src/lib/utils';

export function Setup() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const connectAccount = useAppStore(state => state.connectAccount);
  const loadProfile = useAppStore(state => state.loadProfile);
  const profile = useAppStore(state => state.profile);
  const addToast = useAppStore(state => state.addToast);
  const theme = useAppStore(state => state.theme);
  const sound = useCosmosSound();
  const t = useT();
  const [loading, setLoading] = useState(false);
  const [linked, setLinked] = useState(false);
  const isCosmos = theme === 'Cosmos';

  const finalizeSetup = async () => {
    setSetupDone(true);
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
      setLinked(true);
      setSetupDone(true);
      addToast(t('setup.link_success') || 'Account linked successfully!', 'success');
      const timer = setTimeout(() => {
        navigate(panelRoutes.home);
      }, 1500);
      return () => clearTimeout(timer);
    }

    if (error) {
      addToast(`OAuth error: ${error}`, 'error');
    }
  }, [searchParams, setSetupDone, addToast, navigate, t]);

  useEffect(() => {
    if (!profile.connected || linked) {
      return;
    }

    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setLoading(true);
    void finalizeSetup()
      .then(() => {
        if (!alive) return;
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
  }, [profile.connected, linked, addToast, navigate, t]);

  const handleConnect = async () => {
    setLoading(true);
    sound.play('launch');
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
    sound.play('click');
    setSetupDone(true);
    navigate(panelRoutes.home);
  };

  if (linked) {
    return (
      <div className="relative flex min-h-screen items-center justify-center p-6">
        <div className="cosmos-anim-fade-up flex w-full max-w-sm flex-col items-center gap-6 text-center">
          <div className="cosmos-anim-pulse flex h-16 w-16 items-center justify-center rounded-full">
            <CheckCircle2 className="h-9 w-9 text-[color:var(--success)]" />
          </div>
          <div>
            <h1
              className={cn(
                'text-xl font-semibold text-text-main',
                isCosmos && 'cosmos-text-gradient font-display tracking-wide',
              )}
            >
              {t('setup.linked_title') || 'Account Linked!'}
            </h1>
            <p className="mt-2 text-sm text-text-muted">
              {t('setup.redirecting') || 'Aligning your constellation…'}
            </p>
          </div>
          <Loader2 className="h-5 w-5 animate-spin text-[color:var(--cosmos-gold)]" />
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-6">
      {/* Decorative companion artwork (right edge) */}
      {isCosmos && (
        <img
          src={COSMOS_BRAND.companion}
          onError={hideOnError}
          alt=""
          className="pointer-events-none absolute right-[-6vw] bottom-[-4vh] hidden max-h-[80vh] w-auto opacity-90 cosmos-anim-fade-up md:block"
          loading="lazy"
          decoding="async"
        />
      )}

      <div
        className={cn(
          'relative z-10 flex w-full max-w-md flex-col items-center gap-10 text-center cosmos-anim-fade-up',
          isCosmos && 'cosmos-glass-strong rounded-3xl px-10 py-12',
        )}
      >
        {/* Logo + Title */}
        <div className="flex flex-col items-center gap-4">
          {isCosmos ? (
            <CosmosLogo size={88} glow />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/10">
              <span className="text-2xl font-bold text-accent">R</span>
            </div>
          )}
          <div>
            <h1
              className={cn(
                'text-2xl font-semibold tracking-tight',
                isCosmos
                  ? 'cosmos-text-gradient font-display text-3xl tracking-wide'
                  : 'text-text-main',
              )}
            >
              Welcome to Rumi AI
            </h1>
            <p className="mt-2 text-sm text-text-muted">
              {isCosmos
                ? 'Step through the gateway and align your constellation of intelligence.'
                : t('setup.subtitle')}
            </p>
          </div>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'h-1.5 w-8 rounded-full',
              isCosmos
                ? 'bg-gradient-to-r from-[color:var(--cosmos-gold)] to-[color:var(--cosmos-magenta)]'
                : 'bg-accent',
            )}
          />
          <div
            className={cn(
              'h-1.5 w-8 rounded-full',
              isCosmos ? 'bg-white/20' : 'bg-border',
            )}
          />
        </div>

        {/* Actions */}
        <div className="flex w-full flex-col gap-3">
          <Button
            size="lg"
            className={cn('w-full', isCosmos && 'cosmos-btn-primary')}
            onClick={handleConnect}
            disabled={loading}
            loading={loading}
          >
            {t('setup.connect_rumi')}
          </Button>
          <div className="flex justify-start">
            <Button variant="ghost" onClick={handleSkip} disabled={loading}>
              {t('setup.skip')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
