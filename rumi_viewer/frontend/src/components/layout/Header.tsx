import { useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';
import { Loader2 } from 'lucide-react';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const location = useLocation();
  const isFlows = location.pathname === panelRoutes.flows;

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
    if (runtimeStatus === 'error') {
      return {
        label: 'Runtime error',
        dotClass: 'bg-red-500',
        textClass: 'text-red-600 dark:text-red-400',
      };
    }
    if (!runtimeReady) {
      return {
        label: 'Warming up',
        dotClass: 'bg-amber-500 animate-pulse',
        textClass: 'text-amber-600 dark:text-amber-400',
      };
    }
    return {
      label: 'Runtime ready',
      dotClass: 'bg-emerald-500',
      textClass: 'text-emerald-600 dark:text-emerald-400',
    };
  })();

  return (
    <header className={`z-40 flex shrink-0 items-center justify-between border-b border-border bg-bg-header transition-colors duration-[var(--transition-base)] ${isFlows ? 'h-12 px-4' : 'h-14 px-6'}`}>
      <div className="flex items-center gap-2">
        <h1 className="text-sm font-medium text-text-main">{getPageTitle()}</h1>
      </div>

      <div className="flex items-center gap-3">
        <div
          className={cn(
            "rumi-control-pill hidden md:inline-flex",
            runtimePill.textClass,
          )}
          role="status"
          aria-live="polite"
          title={runtimePill.label}
        >
          {!runtimeReady && runtimeStatus !== 'error' ? (
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
