import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Button } from '@/src/components/ui/Button';
import { useT } from '@/src/lib/i18n';
import { Loader2, CheckCircle2 } from 'lucide-react';

export function Setup() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const connectAccount = useAppStore(state => state.connectAccount);
  const addToast = useAppStore(state => state.addToast);
  const t = useT();
  const [loading, setLoading] = useState(false);
  const [linked, setLinked] = useState(false);

  // Handle OAuth callback redirect params
  useEffect(() => {
    const isLinked = searchParams.get('linked');
    const error = searchParams.get('error');

    if (isLinked === 'true') {
      setLinked(true);
      setSetupDone(true);
      addToast(t('setup.link_success') || 'Account linked successfully!', 'success');
      const timer = setTimeout(() => {
        navigate('/panel');
      }, 1500);
      return () => clearTimeout(timer);
    }

    if (error) {
      addToast(`OAuth error: ${error}`, 'error');
    }
  }, [searchParams, setSetupDone, addToast, navigate, t]);

  const handleConnect = async () => {
    setLoading(true);
    try {
      await connectAccount();
      // connectAccount redirects the page via window.location.href
      // so we won't reach here normally
    } catch {
      setLoading(false);
      addToast(t('setup.connect_failed') || 'Failed to connect', 'error');
    }
  };

  const handleSkip = () => {
    setSetupDone(true);
    navigate('/panel');
  };

  if (linked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-main p-4 transition-colors duration-200">
        <div className="flex w-full max-w-md flex-col items-center justify-center gap-6 text-center animate-in fade-in zoom-in-95">
          <CheckCircle2 className="h-16 w-16 text-green-500" />
          <h1 className="text-2xl font-bold text-text-main">{t('setup.linked_title') || 'Account Linked!'}</h1>
          <p className="text-text-muted">{t('setup.redirecting') || 'Redirecting to dashboard...'}</p>
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-main p-4 transition-colors duration-200">
      <div className="flex w-full max-w-md flex-col items-center justify-center gap-8 text-center animate-in fade-in zoom-in-95">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-24 w-24 items-center justify-center rounded-[var(--radius)] bg-bg-hover shadow-xl overflow-hidden">
            <img src="https://picsum.photos/seed/rumi/200/200" alt="Rumi Logo" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-text-main">Rumi AI</h1>
          <p className="text-text-muted">{t('setup.subtitle')}</p>
        </div>

        <div className="flex w-full flex-col gap-4">
          <Button size="lg" className="w-full text-base" onClick={handleConnect} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}
            {t('setup.connect_rumi')}
          </Button>
          <Button variant="ghost" className="w-full" onClick={handleSkip} disabled={loading}>
            {t('setup.skip')}
          </Button>
        </div>
      </div>
    </div>
  );
}
