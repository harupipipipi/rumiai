import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { launchDefaultspackDesktop } from '@/src/lib/api';
import { isDefaultspackLaunchPack } from '@/src/lib/defaultspackLaunch';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { Badge } from '@/src/components/ui/Badge';
import { Switch } from '@/src/components/ui/Switch';
import { Card } from '@/src/components/ui/Card';
import { panelRoutes } from '@/src/lib/routes';
import { AppWindow, Search, Package, Loader2 } from 'lucide-react';

export function Packs() {
  const t = useT();
  const navigate = useNavigate();
  const packs = useAppStore(state => state.packs);
  const isLoading = useAppStore(state => state.isLoading);
  const loadPacks = useAppStore(state => state.loadPacks);
  const togglePack = useAppStore(state => state.togglePack);
  const addToast = useAppStore(state => state.addToast);
  const [search, setSearch] = useState('');
  const [launchingDesktop, setLaunchingDesktop] = useState(false);

  useEffect(() => {
    loadPacks();
  }, [loadPacks]);

  if (isLoading && packs.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('packs.loading')}</span>
        </div>
      </div>
    );
  }

  const filteredPacks = packs.filter(pack => pack.name.toLowerCase().includes(search.toLowerCase()));

  const handleLaunchDefaultspack = async () => {
    if (launchingDesktop) return;
    setLaunchingDesktop(true);
    try {
      const message = await launchDefaultspackDesktop();
      addToast(message, 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Defaultspackを開けませんでした';
      addToast(message, 'error');
    } finally {
      setLaunchingDesktop(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto page-enter">
      <div className="mx-auto max-w-4xl px-6 py-8 flex flex-col gap-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-main">{t('packs.title')}</h1>
          <p className="mt-1 text-sm text-text-muted">Manage installed packs and their capabilities.</p>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <Input
            placeholder={t('packs.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
            aria-label="Search packs"
          />
        </div>

        {/* Pack list */}
        {filteredPacks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-bg-hover">
              <Package className="h-5 w-5 text-text-muted" />
            </div>
            <h3 className="mt-4 text-base font-medium text-text-main">{t('packs.not_found')}</h3>
            <p className="mt-1 text-sm text-text-muted">{t('packs.try_different')}</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {filteredPacks.map(pack => (
              <Card
                key={pack.id}
                className="cursor-pointer transition-all hover:shadow-[var(--shadow-md)]"
                onClick={() => navigate(panelRoutes.packDetail(pack.id))}
              >
                <div className="flex items-center justify-between p-5">
                  <div className="flex flex-col gap-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-text-main">{pack.name}</h3>
                      <Badge variant="outline">{pack.version}</Badge>
                      <Badge variant={pack.type === 'core' ? 'default' : 'secondary'}>{pack.type}</Badge>
                      <Badge variant={pack.enabled ? 'success' : 'secondary'}>
                        {pack.enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </div>
                    <p className="text-sm text-text-muted truncate">{pack.description}</p>
                  </div>
                  <div className="ml-4 flex shrink-0 items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    {isDefaultspackLaunchPack(pack) && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleLaunchDefaultspack()}
                        loading={launchingDesktop}
                      >
                        <AppWindow className="h-3.5 w-3.5" />
                        Defaultspackを開く
                      </Button>
                    )}
                    <Switch
                      checked={pack.enabled}
                      onCheckedChange={() => togglePack(pack.id)}
                      aria-label={`Toggle ${pack.name}`}
                    />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
