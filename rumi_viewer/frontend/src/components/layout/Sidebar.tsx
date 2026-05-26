import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';
import { Folder, FolderCog, LayoutGrid, Network, Settings, PanelLeft, Home, GitBranch, Share2, Route } from 'lucide-react';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  // Ordered: general user first → advanced/developer last
  const links = [
    { to: panelRoutes.home, icon: Home, label: t('nav.home') },
    { to: panelRoutes.packs, icon: Folder, label: t('nav.packs') },
    { to: panelRoutes.flows, icon: LayoutGrid, label: t('nav.flows') },
    { to: panelRoutes.nodes, icon: Network, label: t('nav.nodes') },
    { to: panelRoutes.graphEditor, icon: GitBranch, label: 'Graphs' },
    { to: panelRoutes.profileGraph, icon: Share2, label: 'Profile Graph' },
    { to: panelRoutes.apiMap, icon: Route, label: 'API Map' },
    { to: panelRoutes.profileWorkspace, icon: FolderCog, label: 'Profile Workspace' },
    { to: panelRoutes.settings, icon: Settings, label: t('nav.settings') },
  ];

  return (
    <aside
      className={cn(
        "flex-shrink-0 flex flex-col bg-bg-sidebar border-r border-border transition-[width] duration-[var(--transition-slow)] overflow-hidden",
        isSidebarOpen ? "w-[240px]" : "w-[56px]"
      )}
    >
      {/* Brand + Toggle */}
      <div className={cn("flex items-center h-14 border-b border-border", isSidebarOpen ? "px-4 justify-between" : "justify-center")}>
        {isSidebarOpen && (
          <span className="text-base font-semibold tracking-tight text-text-main">Rumi AI</span>
        )}
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className="p-1.5 rounded-md text-text-muted hover:bg-bg-hover hover:text-text-main transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
          aria-label={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          <PanelLeft className={cn("w-4 h-4 transition-transform duration-[var(--transition-slow)]", !isSidebarOpen && "rotate-180")} />
        </button>
      </div>

      {/* Navigation */}
      <nav className={cn("flex-1 overflow-y-auto py-3", isSidebarOpen ? "px-3" : "px-1.5")} aria-label="Main navigation">
        <ul className="space-y-1">
          {links.map((link) => {
            const isActive =
              location.pathname === link.to ||
              (link.to !== panelRoutes.home && location.pathname.startsWith(link.to));
            return (
              <li key={link.to}>
                <Link
                  to={link.to}
                  title={!isSidebarOpen ? link.label : undefined}
                  aria-current={isActive ? 'page' : undefined}
                  className={cn(
                    "group relative flex items-center rounded-lg transition-colors duration-[var(--transition-fast)] text-sm font-medium",
                    isSidebarOpen ? "gap-3 px-3 py-2" : "justify-center p-2.5",
                    isActive
                      ? "bg-accent/8 text-accent"
                      : "text-text-muted hover:bg-bg-hover hover:text-text-main"
                  )}
                >
                  {isActive && isSidebarOpen && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 bg-accent rounded-r-full" />
                  )}
                  <link.icon className={cn("w-[18px] h-[18px] shrink-0", isActive ? "text-accent" : "text-text-muted group-hover:text-text-main")} />
                  {isSidebarOpen && <span>{link.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User section */}
      <div className="border-t border-border">
        <div className={cn(isSidebarOpen ? "p-3" : "p-1.5 flex justify-center")}>
          <Link
            to={panelRoutes.settings}
            title={!isSidebarOpen ? profile.username : undefined}
            className={cn(
              "flex items-center rounded-lg transition-colors hover:bg-bg-hover",
              isSidebarOpen ? "gap-3 p-2 w-full" : "p-2 justify-center"
            )}
          >
            {profile.avatar ? (
              <img src={profile.avatar} alt="" className="w-7 h-7 rounded-full object-cover border border-border" referrerPolicy="no-referrer" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-semibold">
                {profile.username.charAt(0).toUpperCase()}
              </div>
            )}
            {isSidebarOpen && (
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text-main truncate">{profile.username}</div>
              </div>
            )}
          </Link>
        </div>
      </div>
    </aside>
  );
}
