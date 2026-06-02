import { useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
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

  return (
    <header className={`z-40 flex shrink-0 items-center justify-between border-b border-border bg-bg-header transition-colors duration-[var(--transition-base)] ${isFlows ? 'h-12 px-4' : 'h-14 px-6'}`}>
      <div className="flex items-center gap-2">
        <h1 className="text-sm font-medium text-text-main">{getPageTitle()}</h1>
      </div>

      <div className="flex items-center gap-3">
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
