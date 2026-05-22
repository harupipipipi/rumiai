import { useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';
import { cn } from '@/src/lib/utils';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
  const theme = useAppStore(state => state.theme);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const location = useLocation();
  const isFlows = location.pathname === panelRoutes.flows;
  const isCosmos = theme === 'Cosmos';

  const getPageTitle = () => {
    if (location.pathname === panelRoutes.home) return t('nav.home');
    if (location.pathname === panelRoutes.packs || location.pathname.startsWith(panelRoutes.packs)) return t('nav.packs');
    if (location.pathname === panelRoutes.flows) return t('nav.flows');
    if (location.pathname === panelRoutes.nodes) return t('nav.nodes');
    if (location.pathname === panelRoutes.graphEditor) return 'Graphs';
    if (location.pathname === panelRoutes.profileWorkspace) return 'Profile Workspace';
    if (location.pathname === panelRoutes.settings) return t('nav.settings');
    return '';
  };

  // Status copy + colour
  const statusInfo = runtimeReady
    ? { label: 'Aligned', tone: 'success' as const }
    : runtimeStatus === 'error'
      ? { label: 'Misaligned', tone: 'error' as const }
      : { label: 'Calibrating', tone: 'warning' as const };

  return (
    <header
      className={cn(
        'z-40 flex shrink-0 items-center justify-between border-b transition-colors duration-[var(--transition-base)]',
        isCosmos
          ? 'cosmos-glass border-[color:color-mix(in_srgb,var(--cosmos-gold)_20%,var(--border))]'
          : 'bg-bg-header border-border',
        isFlows ? 'h-12 px-4' : 'h-14 px-6',
      )}
    >
      <div className="flex items-center gap-3">
        <h1
          className={cn(
            'text-sm font-medium',
            isCosmos ? 'font-display tracking-wide text-text-main text-base' : 'text-text-main',
          )}
        >
          {getPageTitle()}
        </h1>
        {isCosmos && (
          <div className="hidden items-center gap-2 rounded-full border border-[color:color-mix(in_srgb,var(--cosmos-gold)_28%,transparent)] bg-[color:color-mix(in_srgb,var(--cosmos-gold)_10%,transparent)] px-3 py-1 text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-muted)] sm:inline-flex">
            <span
              aria-hidden
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                statusInfo.tone === 'success' && 'bg-[color:var(--success)] cosmos-anim-pulse',
                statusInfo.tone === 'error' && 'bg-[color:var(--destructive)]',
                statusInfo.tone === 'warning' && 'bg-[color:var(--cosmos-gold)] cosmos-anim-pulse',
              )}
            />
            {statusInfo.label}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden text-xs text-text-muted sm:block">{profile.username}</span>
        {profile.avatar ? (
          <img
            src={profile.avatar}
            alt={`${profile.username} avatar`}
            className={cn(
              'h-7 w-7 rounded-full object-cover',
              isCosmos
                ? 'ring-1 ring-[color:color-mix(in_srgb,var(--cosmos-gold)_45%,transparent)]'
                : 'border border-border',
            )}
            referrerPolicy="no-referrer"
          />
        ) : (
          <div
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold',
              isCosmos ? 'cosmos-text-gradient font-display' : 'bg-accent/20 text-accent',
            )}
          >
            {profile.username.charAt(0).toUpperCase()}
          </div>
        )}
      </div>
    </header>
  );
}
