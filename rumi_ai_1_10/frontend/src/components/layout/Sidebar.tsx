import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';
import { Folder, GitBranch, LayoutGrid, Network, Settings, PanelLeft, Home } from 'lucide-react';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const theme = useAppStore(state => state.theme);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  const links = [
    { to: panelRoutes.home, icon: Home, label: t('nav.home') },
    { to: panelRoutes.packs, icon: Folder, label: t('nav.packs') },
    { to: panelRoutes.nodes, icon: Network, label: t('nav.nodes') },
    { to: panelRoutes.graphEditor, icon: GitBranch, label: 'Graphs' },
    { to: panelRoutes.flows, icon: LayoutGrid, label: t('nav.flows') },
    { to: panelRoutes.settings, icon: Settings, label: t('nav.settings') },
  ];


  return (
    <aside
      className={cn(
        "flex-shrink-0 flex flex-col bg-bg-sidebar border-r border-border transition-all duration-300 overflow-hidden",
        isSidebarOpen ? "w-[260px]" : "w-14"
      )}
    >
      {/* Logo Area */}
      <div className={cn("p-3 flex items-center", isSidebarOpen ? "justify-between" : "justify-center")}>
        {isSidebarOpen ? (
          <div className="flex items-center gap-2 px-2">
            {theme === 'Rumi' && <span className="font-bold text-lg tracking-wide text-text-main">Rumi AI</span>}
            {theme === 'Minimal' && <span className="font-serif text-lg font-medium tracking-wide text-text-main">Rumi</span>}
            {theme === 'Standard' && <span className="font-medium text-lg text-text-main">Rumi</span>}
            {theme === 'Rounded' && <span className="text-xl font-medium text-text-main">Rumi</span>}
          </div>
        ) : null}
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className="p-1.5 hover:bg-bg-hover rounded-md text-text-muted transition-colors"
          title={isSidebarOpen ? "Close sidebar" : "Expand sidebar"}
        >
          <PanelLeft className={cn("w-5 h-5 transition-transform duration-300", !isSidebarOpen && "rotate-180")} />
        </button>
      </div>

      {/* Navigation Links */}
      <div className={cn(
        "py-2 space-y-1 flex-1 overflow-y-auto",
        isSidebarOpen ? "px-3" : "px-1.5"
      )}>
        {links.map((link: any) => {
          const isActive =
            location.pathname === link.to ||
            (link.to !== panelRoutes.home && location.pathname.startsWith(link.to));
          return (
            <Link
              key={link.to}
              to={link.to}
              title={!isSidebarOpen ? link.label : undefined}
              className={cn(
                "flex items-center rounded-lg transition-colors font-medium text-sm",
                isSidebarOpen ? "w-full gap-3 px-3 py-2" : "justify-center p-2.5",
                isActive ? "bg-accent text-accent-fg shadow-sm" : "text-text-muted hover:bg-bg-hover hover:text-text-main"
              )}
            >
              <link.icon className="w-5 h-5" />
              {isSidebarOpen && <span>{link.label}</span>}
            </Link>
          );
        })}
      </div>

      {/* Bottom section: toggle + profile */}
      <div className="mt-auto border-t border-border">
        <div className={cn(isSidebarOpen ? "p-3" : "p-1.5 flex justify-center")}>
          <Link
            to={panelRoutes.settings}
            title={!isSidebarOpen ? t('nav.settings') : undefined}
            className={cn(
              "hover:bg-bg-hover rounded-lg transition-colors",
              isSidebarOpen ? "w-full flex items-center justify-between p-2" : "flex justify-center p-1.5"
            )}
          >
            <div className={cn("flex items-center", isSidebarOpen && "gap-3")}>
              {profile.avatar ? (
                <img src={profile.avatar} alt="User" className="w-8 h-8 rounded-full object-cover border border-border" referrerPolicy="no-referrer" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gradient-to-r from-green-400 to-blue-500 flex items-center justify-center text-white font-bold text-sm">
                  {profile.username.charAt(0).toUpperCase()}
                </div>
              )}
              {isSidebarOpen && (
                <div className="text-left leading-tight">
                  <div className="text-[13px] font-medium text-text-main">{profile.username}</div>
                  <div className="text-[11px] text-text-muted">{t('nav.admin')}</div>
                </div>
              )}
            </div>
            {isSidebarOpen && <Settings className="w-4 h-4 text-text-muted" />}
          </Link>
        </div>
      </div>
    </aside>
  );
}
