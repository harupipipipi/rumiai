import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAppStore, type Pack } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Input } from '@/src/components/ui/Input';
import { Badge } from '@/src/components/ui/Badge';
import { Switch } from '@/src/components/ui/Switch';
import { Card } from '@/src/components/ui/Card';
import { panelRoutes } from '@/src/lib/routes';
import { AlertTriangle, Search, Package, Loader2, ShieldCheck } from 'lucide-react';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning';

function approvalBadgeVariant(pack: Pack): BadgeVariant {
  if (pack.approved) return 'success';
  if (pack.approvalStatus === 'pending' || pack.approvalStatus === 'installed') return 'warning';
  if (pack.criticalChanged || ['blocked', 'error', 'modified'].includes(pack.approvalStatus)) return 'destructive';
  return 'warning';
}

function approvalBadgeLabel(pack: Pack): string {
  if (pack.approved) return 'Approved';
  if (pack.approvalStatus === 'pending' || pack.approvalStatus === 'installed') return 'Needs approval';
  if (pack.approvalStatus === 'blocked') return 'Blocked';
  if (pack.criticalChanged || pack.approvalStatus === 'modified') return 'Modified';
  return 'Approval unknown';
}

function approvalIssueText(pack: Pack): string {
  return pack.approvalReason || pack.approvalIssues[0] || 'Pack approval needs attention.';
}

export function Packs() {
  const t = useT();
  const packs = useAppStore(state => state.packs);
  const isLoading = useAppStore(state => state.isLoading);
  const loadPacks = useAppStore(state => state.loadPacks);
  const togglePack = useAppStore(state => state.togglePack);
  const [search, setSearch] = useState('');

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
                className="transition-all hover:shadow-[var(--shadow-md)] focus-within:shadow-[var(--shadow-md)]"
              >
                <div className="flex items-center justify-between">
                  <Link
                    to={panelRoutes.packDetail(pack.id)}
                    aria-label={`Open ${pack.name} details`}
                    className="flex min-h-11 min-w-0 flex-1 cursor-pointer flex-col gap-1.5 rounded-l-xl p-5 text-inherit focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--ring-color)]"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-text-main">{pack.name}</h3>
                      <Badge variant="outline">{pack.version}</Badge>
                      <Badge variant={pack.type === 'core' ? 'default' : 'secondary'}>{pack.type}</Badge>
                      <Badge variant={pack.enabled ? 'success' : 'secondary'}>
                        {pack.enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                      <Badge variant={approvalBadgeVariant(pack)} className="inline-flex items-center gap-1">
                        {pack.approved ? (
                          <ShieldCheck className="h-3 w-3" />
                        ) : (
                          <AlertTriangle className="h-3 w-3" />
                        )}
                        {approvalBadgeLabel(pack)}
                      </Badge>
                    </div>
                    <p className="text-sm text-text-muted truncate">{pack.description}</p>
                    {(!pack.approved || pack.approvalIssues.length > 0) && (
                      <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{approvalIssueText(pack)}</span>
                      </div>
                    )}
                  </Link>
                  <div className="mx-2 flex min-h-11 min-w-11 shrink-0 items-center justify-center">
                    <Switch
                      checked={pack.enabled}
                      onCheckedChange={() => togglePack(pack.id)}
                      aria-label={`Toggle ${pack.name}`}
                      className="relative after:absolute after:-inset-2.5"
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
