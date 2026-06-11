import { useLocation } from 'react-router-dom';
import { ArrowDown, Loader2 } from 'lucide-react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { describeRuntimeBadge } from '@/src/lib/runtimeHealth';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);
  const runtimeDisconnected = useAppStore(state => state.runtimeDisconnected);
  const lastRuntimeHealthyAt = useAppStore(state => state.lastRuntimeHealthyAt);
  const location = useLocation();
  const isFlows = location.pathname === panelRoutes.flows;
  const runtimeBadge = describeRuntimeBadge({
    runtimeReady,
    runtimeStatus,
    runtimeError,
    runtimeDisconnected,
    lastRuntimeHealthyAt,
  });

  const getPageTitle = () => {
    if (location.pathname === panelRoutes.home) return t('nav.home');
    if (location.pathname === panelRoutes.packs || location.pathname.startsWith(panelRoutes.packs)) return t('nav.packs');
    if (location.pathname === panelRoutes.flows) return t('nav.flows');
    if (location.pathname === panelRoutes.nodes) return t('nav.nodes');
    if (location.pathname === panelRoutes.graphEditor) return 'Graphs';
    if (location.pathname === panelRoutes.profileGraph) return 'Profile Graph';
    if (location.pathname === panelRoutes.apiMap) return 'API Map';
    if (location.pathname === panelRoutes.profileWorkspace) return 'Profile Workspace';
    if (location.pathname === panelRoutes.settings) return t('nav.settings');
    return '';
  };

  const runtimePill = (() => {
    if (runtimeBadge.tone === 'danger') {
      return {
        label: runtimeBadge.label,
        dotClass: 'bg-red-500',
        textClass: 'text-red-600 dark:text-red-400',
      };
    }
    if (runtimeBadge.tone === 'warning') {
      return {
        label: runtimeBadge.label,
        dotClass: 'bg-amber-500 animate-pulse',
        textClass: 'text-amber-600 dark:text-amber-400',
      };
    }
    return {
      label: runtimeBadge.label,
      dotClass: 'bg-emerald-500',
      textClass: 'text-emerald-600 dark:text-emerald-400',
    };
  })();
  const showRuntimeSpinner = runtimeBadge.tone === 'warning' && !runtimeReady && runtimeStatus !== 'error';

  return (
    <header className={`z-40 flex shrink-0 items-center justify-between border-b border-border bg-bg-header transition-colors duration-[var(--transition-base)] ${isFlows ? 'h-12 px-4' : 'h-14 px-6'}`}>
      <div className="flex min-w-0 items-center gap-3">
        <div className="relative shrink-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-border/70 bg-[radial-gradient(circle_at_top,#7dd3fc,transparent_55%),linear-gradient(135deg,#111827,#1f2937)] text-xs font-semibold text-white shadow-sm">
            R
          </div>
          {runtimeBadge.showOfflineBadge ? (
            <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-white shadow-sm">
              <ArrowDown className="h-2.5 w-2.5" />
            </span>
          ) : null}
        </div>
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-sm font-medium text-text-main">{getPageTitle()}</h1>
            <span
              className={`hidden rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] sm:inline-flex ${
                runtimeBadge.tone === 'success'
                  ? 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-300'
                  : runtimeBadge.tone === 'danger'
                    ? 'bg-red-500/12 text-red-600 dark:text-red-300'
                    : 'bg-amber-500/12 text-amber-600 dark:text-amber-300'
              }`}
            >
              {runtimeBadge.label}
            </span>
          </div>
          <p className="hidden truncate text-[11px] text-text-muted sm:block">{runtimeBadge.detail}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div
          className={cn(
            "rumi-control-pill hidden md:inline-flex",
            runtimePill.textClass,
          )}
          role="status"
          aria-live="polite"
          title={runtimeBadge.detail}
        >
          {showRuntimeSpinner ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <span className={cn("rumi-control-pill-dot", runtimePill.dotClass)} />
          )}
          <span>{runtimePill.label}</span>
        </div>
        <span className="text-xs text-text-muted hidden sm:block">{profile.username}</span>
        {profile.avatar ? (
          <img
            src={profile.avatar}
            alt={`${profile.username} avatar`}
            className="h-7 w-7 rounded-full object-cover border border-border"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="h-7 w-7 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-semibold">
            {profile.username.charAt(0).toUpperCase()}
          </div>
        )}
      </div>
    </header>
  );
}
