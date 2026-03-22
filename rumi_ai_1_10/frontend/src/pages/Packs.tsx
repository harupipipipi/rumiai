import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Input } from '@/src/components/ui/Input';
import { Badge } from '@/src/components/ui/Badge';
import { Switch } from '@/src/components/ui/Switch';
import { Search, Package, Loader2 } from 'lucide-react';

export function Packs() {
  const t = useT();
  const navigate = useNavigate();
  const packs = useAppStore(state => state.packs);
  const togglePack = useAppStore(state => state.togglePack);
  const addToast = useAppStore(state => state.addToast);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 600);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('packs.loading')}</span>
        </div>
      </div>
    );
  }

  const filteredPacks = packs.filter(pack => pack.name.toLowerCase().includes(search.toLowerCase()));

  const handleToggle = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    togglePack(id);
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight text-text-main">{t('packs.title')}</h1>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
        <Input
          placeholder={t('packs.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      <div className="grid gap-4">
        {filteredPacks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Package className="mb-4 h-12 w-12 text-text-muted opacity-20" />
            <h3 className="text-lg font-medium text-text-main">{t('packs.not_found')}</h3>
            <p className="text-sm text-text-muted">{t('packs.try_different')}</p>
          </div>
        ) : (
          filteredPacks.map(pack => (
            <div
              key={pack.id}
              onClick={() => navigate(`/panel/packs/${pack.id}`)}
              className="flex cursor-pointer items-center justify-between rounded-xl border border-border bg-bg-card p-6 shadow-sm transition-colors hover:bg-bg-hover"
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold text-text-main">{pack.name}</h3>
                  <Badge variant="outline">{pack.version}</Badge>
                  <Badge variant={pack.type === 'core' ? 'default' : 'secondary'}>{pack.type}</Badge>
                </div>
                <p className="text-sm text-text-muted">{pack.description}</p>
              </div>
              <div onClick={(e) => e.stopPropagation()}>
                <Switch checked={pack.enabled} onCheckedChange={() => handleToggle(pack.id, { stopPropagation: () => {} } as React.MouseEvent)} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
