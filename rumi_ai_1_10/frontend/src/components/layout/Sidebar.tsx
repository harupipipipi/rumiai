import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { Folder, LayoutGrid, Settings, PanelLeft, Home } from 'lucide-react';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const theme = useAppStore(state => state.theme);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  const links = [
    { to: '/panel', icon: Home, label: t('nav.home') },
    { to: '/panel/packs', icon: Folder, label: t('nav.packs') },
    { to: '/panel/flows', icon: LayoutGrid, label: t('nav.flows') },
    { to: '/panel/settings', icon: Settings, label: t('nav.settings') },
  ];


  return (
    <aside
      className={cn(
        "flex-shrink-0 flex flex-col bg-bg-sidebar border-r border-border transition-all duration-300 overflow-hidden",
        isSidebarOpen ? "w-[260px]" : "w-0 border-r-0"
      )}
    >
      {/* Logo Area */}
      <div className="p-3 flex items-center justify-between">
        <div className="flex items-center gap-2 px-2">
          {theme === 'Rumi' && <span className="font-bold text-lg tracking-wide text-text-main">Rumi AI</span>}
          {theme === 'Minimal' && <span className="font-serif text-lg font-medium tracking-wide text-text-main">Rumi</span>}
          {theme === 'Standard' && <span className="font-medium text-lg text-text-main">Rumi</span>}
          {theme === 'Rounded' && <span className="text-xl font-medium text-text-main">Rumi</span>}
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-1.5 hover:bg-bg-hover rounded-md text-text-muted transition-colors"
          title="Close sidebar"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation Links */}
      <div className="px-3 py-2 space-y-1 mt-2 flex-1 overflow-y-auto">
        {links.map((link: any) => {
          const isActive = location.pathname === link.to || (link.to !== '/panel' && location.pathname.startsWith(link.to));
          return (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors font-medium text-sm",
                isActive ? "bg-accent text-accent-fg shadow-sm" : "text-text-muted hover:bg-bg-hover hover:text-text-main"
              )}
            >
              <link.icon className="w-5 h-5" /> {link.label}
            </Link>
          );
        })}
      </div>

      {/* Profile Area */}
      <div className="p-3 border-t border-border mt-auto">
        <Link to="/panel/settings" className="w-full flex items-center justify-between hover:bg-bg-hover p-2 rounded-lg transition-colors">
          <div className="flex items-center gap-3">
            {profile.avatar ? (
              <img src={profile.avatar} alt="User" className="w-8 h-8 rounded-full object-cover border border-border" referrerPolicy="no-referrer" />
            ) : (
              <div className="w-8 h-8 rounded-full bg-gradient-to-r from-green-400 to-blue-500 flex items-center justify-center text-white font-bold text-sm">
                {profile.username.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="text-left leading-tight">
              <div className="text-[13px] font-medium text-text-main">{profile.username}</div>
              <div className="text-[11px] text-text-muted">{t('nav.admin')}</div>
            </div>
          </div>
          <Settings className="w-4 h-4 text-text-muted" />
        </Link>
      </div>
    </aside>
  );
}
