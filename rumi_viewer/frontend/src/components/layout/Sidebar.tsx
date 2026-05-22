import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';
import { Folder, FolderCog, LayoutGrid, Network, Settings, PanelLeft, Home, GitBranch } from 'lucide-react';
import { CosmosLogo } from '@/src/cosmos/CosmosLogo';
import { useCosmosSound } from '@/src/cosmos/SoundProvider';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);
  const theme = useAppStore(state => state.theme);
  const sound = useCosmosSound();
  const isCosmos = theme === 'Cosmos';

  // Ordered: general user first → advanced/developer last
  const links = [
    { to: panelRoutes.home, icon: Home, label: t('nav.home') },
    { to: panelRoutes.packs, icon: Folder, label: t('nav.packs') },
    { to: panelRoutes.flows, icon: LayoutGrid, label: t('nav.flows') },
    { to: panelRoutes.nodes, icon: Network, label: t('nav.nodes') },
    { to: panelRoutes.graphEditor, icon: GitBranch, label: 'Graphs' },
    { to: panelRoutes.profileWorkspace, icon: FolderCog, label: 'Profile Workspace' },
    { to: panelRoutes.settings, icon: Settings, label: t('nav.settings') },
  ];

  return (
    <aside
      className={cn(
        'relative z-10 flex shrink-0 flex-col overflow-hidden border-r transition-[width] duration-[var(--transition-slow)]',
        isCosmos
          ? 'cosmos-glass-strong border-[color:color-mix(in_srgb,var(--cosmos-gold)_20%,var(--border))]'
          : 'border-border bg-bg-sidebar',
        isSidebarOpen ? 'w-[240px]' : 'w-[56px]',
      )}
    >
      {/* Brand + Toggle */}
      <div
        className={cn(
          'flex h-16 items-center border-b',
          isCosmos
            ? 'border-[color:color-mix(in_srgb,var(--cosmos-gold)_22%,var(--border))]'
            : 'border-border',
          isSidebarOpen ? 'justify-between px-4' : 'justify-center',
        )}
      >
        {isSidebarOpen && (
          <Link
            to={panelRoutes.home}
            onClick={() => sound.play('nav')}
            className="flex items-center gap-2"
            aria-label="Rumi AI home"
          >
            {isCosmos ? (
              <>
                <CosmosLogo size={28} glow />
                <span className="cosmos-text-gradient font-display text-lg font-semibold tracking-wide">
                  Rumi AI
                </span>
              </>
            ) : (
              <span className="text-base font-semibold tracking-tight text-text-main">Rumi AI</span>
            )}
          </Link>
        )}
        {!isSidebarOpen && isCosmos && <CosmosLogo size={26} glow />}
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
          aria-label={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <PanelLeft
            className={cn(
              'h-4 w-4 transition-transform duration-[var(--transition-slow)]',
              !isSidebarOpen && 'rotate-180',
            )}
          />
        </button>
      </div>

      {/* Navigation */}
      <nav
        className={cn('scrollbar-hidden flex-1 overflow-y-auto py-3', isSidebarOpen ? 'px-3' : 'px-1.5')}
        aria-label="Main navigation"
      >
        <ul className="space-y-1">
          {links.map((link) => {
            const isActive =
              location.pathname === link.to ||
              (link.to !== panelRoutes.home && location.pathname.startsWith(link.to));
            return (
              <li key={link.to}>
                <Link
                  to={link.to}
                  onClick={() => sound.play('nav')}
                  title={!isSidebarOpen ? link.label : undefined}
                  aria-current={isActive ? 'page' : undefined}
                  className={cn(
                    'group relative flex items-center rounded-lg text-sm font-medium transition-colors duration-[var(--transition-fast)]',
                    isSidebarOpen ? 'gap-3 px-3 py-2' : 'justify-center p-2.5',
                    isActive
                      ? isCosmos
                        ? 'cosmos-glass text-text-main'
                        : 'bg-accent/8 text-accent'
                      : 'text-text-muted hover:bg-bg-hover hover:text-text-main',
                  )}
                >
                  {isActive && isSidebarOpen && (
                    isCosmos
                      ? <span className="cosmos-nav-star" aria-hidden />
                      : <div className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-accent" />
                  )}
                  <link.icon
                    className={cn(
                      'h-[18px] w-[18px] shrink-0',
                      isActive
                        ? isCosmos
                          ? 'text-[color:var(--cosmos-gold)]'
                          : 'text-accent'
                        : 'text-text-muted group-hover:text-text-main',
                    )}
                  />
                  {isSidebarOpen && <span>{link.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User section */}
      <div
        className={cn(
          'border-t',
          isCosmos
            ? 'border-[color:color-mix(in_srgb,var(--cosmos-gold)_20%,var(--border))]'
            : 'border-border',
        )}
      >
        <div className={cn(isSidebarOpen ? 'p-3' : 'flex justify-center p-1.5')}>
          <Link
            to={panelRoutes.settings}
            title={!isSidebarOpen ? profile.username : undefined}
            onClick={() => sound.play('nav')}
            className={cn(
              'flex items-center rounded-lg transition-colors',
              isCosmos ? 'hover:cosmos-glass' : 'hover:bg-bg-hover',
              isSidebarOpen ? 'w-full gap-3 p-2' : 'justify-center p-2',
            )}
          >
            {profile.avatar ? (
              <img
                src={profile.avatar}
                alt=""
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
                  isCosmos
                    ? 'cosmos-text-gradient font-display'
                    : 'bg-accent/20 text-accent',
                )}
              >
                {profile.username.charAt(0).toUpperCase()}
              </div>
            )}
            {isSidebarOpen && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-text-main">{profile.username}</div>
              </div>
            )}
          </Link>
        </div>
      </div>
    </aside>
  );
}
