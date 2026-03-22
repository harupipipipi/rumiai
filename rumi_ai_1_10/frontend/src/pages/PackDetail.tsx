import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import { Switch } from '@/src/components/ui/Switch';
import { ArrowLeft, Play, Loader2 } from 'lucide-react';

export function PackDetail() {
  const t = useT();
  const { id } = useParams();
  const navigate = useNavigate();
  const packs = useAppStore(state => state.packs);
  const togglePack = useAppStore(state => state.togglePack);
  const addToast = useAppStore(state => state.addToast);
  const [isLoading, setIsLoading] = useState(true);

  const pack = packs.find(p => p.id === id);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 500);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('pack.loading')}</span>
        </div>
      </div>
    );
  }

  if (!pack) {
    return <div className="p-8 text-center text-text-muted">Pack not found</div>;
  }

  const handleToggle = () => {
    const key = pack.enabled ? 'packs.toggle_off' : 'packs.toggle_on';
    togglePack(pack.id);
    addToast(t(key, { name: pack.name }), 'success');
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate('/panel/packs')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <h1 className="text-3xl font-bold tracking-tight text-text-main">{pack.name}</h1>
        <Badge variant="outline">{pack.version}</Badge>
        <Badge variant={pack.type === 'core' ? 'default' : 'secondary'}>{pack.type}</Badge>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm font-medium text-text-muted">{pack.enabled ? t('packs.enabled') : t('packs.disabled')}</span>
          <Switch checked={pack.enabled} onCheckedChange={handleToggle} />
        </div>
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.basic_info')}</h3>
            <p className="text-sm text-text-muted">{pack.description}</p>
          </div>

          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.capabilities')}</h3>
            {pack.capabilities.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <ul className="space-y-3">
                {pack.capabilities.map((cap, i) => (
                  <li key={i} className="flex flex-col gap-1">
                    <span className="text-sm font-medium text-text-main">{cap.name}</span>
                    <span className="text-xs text-text-muted">{cap.description}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.flows')}</h3>
            {pack.flows.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <ul className="space-y-3">
                {pack.flows.map((flow, i) => (
                  <li key={i} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <span className="text-sm font-medium text-text-main">{flow}</span>
                    <Button size="sm" variant="outline" onClick={() => {
                      setTimeout(() => navigate('/panel/flows'), 1000);
                    }}>
                      <Play className="mr-2 h-4 w-4" />
                      {t('pack.run')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.dependencies')}</h3>
            {pack.dependencies.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {pack.dependencies.map((dep, i) => (
                  <Badge key={i} variant="secondary">{dep}</Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
