import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Button } from '@/src/components/ui/Button';
import { useT } from '@/src/lib/i18n';
import { Loader2 } from 'lucide-react';

export function Setup() {
  const navigate = useNavigate();
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const connectAccount = useAppStore(state => state.connectAccount);
  const t = useT();
  const [loading, setLoading] = useState(false);

  const handleConnect = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      connectAccount();
      setSetupDone(true);
      navigate('/panel');
    }, 2000);
  };

  const handleSkip = () => {
    setSetupDone(true);
    navigate('/panel');
  };

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
