import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { panelRoutes } from '@/src/lib/routes';
import { BrainCircuit, Folder, FolderCog, LayoutGrid, Network, Settings, PanelLeft, Home, GitBranch, Share2, Route } from 'lucide-react';

type NavGroup = {
  id: 'workspace' | 'advanced';
  items: { to: string; icon: typeof Home; label: string }[];
};

const sidebarAnimation = 'duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  // Ordered: workspace surfaces first, advanced/developer surfaces last
  const navGroups: NavGroup[] = [
    {
      id: 'workspace',
      items: [
        { to: panelRoutes.home, icon: Home, label: t('nav.home') },
        { to: panelRoutes.packs, icon: Folder, label: t('nav.packs') },
        { to: panelRoutes.flows, icon: LayoutGrid, label: t('nav.flows') },
        { to: panelRoutes.nodes, icon: Network, label: t('nav.nodes') },
      ],
    },
    {
      id: 'advanced',
      items: [
        { to: panelRoutes.graphEditor, icon: GitBranch, label: 'Graphs' },
        { to: panelRoutes.profileGraph, icon: Share2, label: 'Profile Graph' },
        { to: panelRoutes.aiInput, icon: BrainCircuit, label: 'AI Input' },
        { to: panelRoutes.apiMap, icon: Route, label: 'API Map' },
        { to: panelRoutes.profileWorkspace, icon: FolderCog, label: 'Profile Workspace' },
        { to: panelRoutes.settings, icon: Settings, label: t('nav.settings') },
      ],
    },
  ];

  const groupLabels: Record<NavGroup['id'], string> = {
    workspace: 'Workspace',
    advanced: 'Advanced',
  };

  return (
    <aside
      className={cn(
        "flex-shrink-0 flex flex-col bg-bg-sidebar border-r border-border transition-[width] overflow-hidden will-change-[width]",
        sidebarAnimation,
        isSidebarOpen ? "w-[240px]" : "w-[56px]"
      )}
    >
      {/* Brand + Toggle */}
      <div
        className={cn(
          "grid h-14 grid-cols-[minmax(0,1fr)_32px] items-center overflow-hidden border-b border-border transition-[padding]",
          sidebarAnimation,
          isSidebarOpen ? "px-4" : "px-3",
        )}
      >
        <span
          className={cn(
            "block min-w-0 overflow-hidden whitespace-nowrap text-base font-semibold tracking-tight text-text-main transition-[max-width,opacity,transform]",
            sidebarAnimation,
            isSidebarOpen ? "max-w-32 translate-x-0 opacity-100" : "max-w-0 -translate-x-2 opacity-0",
          )}
          aria-hidden={!isSidebarOpen}
        >
          Rumi AI
        </span>
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className={cn(
            "justify-self-center rounded-md p-1.5 text-text-muted transition-[background-color,color,transform] hover:bg-bg-hover hover:text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]",
            sidebarAnimation,
            !isSidebarOpen && "scale-105",
          )}
          aria-label={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          <PanelLeft className={cn("w-4 h-4 transition-transform", sidebarAnimation, !isSidebarOpen && "rotate-180")} />
        </button>
      </div>

      {/* Navigation */}
      <nav
        className={cn(
          "flex-1 overflow-y-auto py-3 transition-[padding]",
          sidebarAnimation,
          isSidebarOpen ? "px-3" : "px-1.5",
        )}
        aria-label="Main navigation"
      >
        <ul
          className={cn(
            "flex flex-col transition-[gap]",
            sidebarAnimation,
            isSidebarOpen ? "gap-4" : "gap-2",
          )}
        >
          {navGroups.map((group, groupIndex) => (
            <li key={group.id} className="flex flex-col gap-1">
              {groupIndex > 0 && (
                <div
                  className={cn(
                    "mx-2 h-px bg-border/60 transition-[margin,opacity]",
                    sidebarAnimation,
                    isSidebarOpen ? "my-0 opacity-0" : "my-1 opacity-100",
                  )}
                  aria-hidden="true"
                />
              )}
              <div
                className={cn(
                  "overflow-hidden px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted/70 transition-[max-height,padding,opacity,transform,border-color]",
                  sidebarAnimation,
                  groupIndex > 0 && "border-t border-border/60",
                  isSidebarOpen
                    ? cn("max-h-10 translate-x-0 pt-1 opacity-100", groupIndex > 0 && "pt-3")
                    : "max-h-0 -translate-x-1 pt-0 opacity-0 border-transparent",
                )}
                aria-hidden={!isSidebarOpen}
              >
                {groupLabels[group.id]}
              </div>
              <ul
                className={cn(
                  "flex flex-col transition-[gap]",
                  sidebarAnimation,
                  isSidebarOpen ? "gap-1" : "gap-1.5",
                )}
              >
                {group.items.map((link) => {
                  const isActive =
                    location.pathname === link.to ||
                    (link.to !== panelRoutes.home && location.pathname.startsWith(link.to));
                  return (
                    <li key={link.to}>
                      <Link
                        to={link.to}
                        title={!isSidebarOpen ? link.label : undefined}
                        aria-label={link.label}
                        aria-current={isActive ? 'page' : undefined}
                        className={cn(
                          "group relative flex items-center rounded-lg text-sm font-medium transition-[gap,padding,background-color,color]",
                          sidebarAnimation,
                          isSidebarOpen ? "gap-3 px-3 py-2" : "justify-center gap-0 p-2.5",
                          isActive
                            ? "bg-accent/8 text-accent"
                            : "text-text-muted hover:bg-bg-hover hover:text-text-main"
                        )}
                      >
                        <div
                          className={cn(
                            "absolute left-0 top-1/2 w-[3px] -translate-y-1/2 rounded-r-full bg-accent transition-[height,opacity]",
                            sidebarAnimation,
                            isActive && isSidebarOpen ? "h-4 opacity-100" : "h-2 opacity-0",
                          )}
                          aria-hidden="true"
                        />
                        <link.icon className={cn("w-[18px] h-[18px] shrink-0", isActive ? "text-accent" : "text-text-muted group-hover:text-text-main")} />
                        <span
                          className={cn(
                            "block min-w-0 overflow-hidden whitespace-nowrap transition-[max-width,opacity,transform]",
                            sidebarAnimation,
                            isSidebarOpen ? "max-w-40 translate-x-0 opacity-100" : "max-w-0 -translate-x-2 opacity-0",
                          )}
                          aria-hidden={!isSidebarOpen}
                        >
                          {link.label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      </nav>

      {/* User section */}
      <div className="border-t border-border">
        <div
          className={cn(
            "transition-[padding]",
            sidebarAnimation,
            isSidebarOpen ? "p-3" : "flex justify-center p-1.5",
          )}
        >
          <Link
            to={panelRoutes.settings}
            title={!isSidebarOpen ? profile.username : undefined}
            aria-label={profile.username}
            className={cn(
              "flex items-center rounded-lg transition-[gap,padding,background-color] hover:bg-bg-hover",
              sidebarAnimation,
              isSidebarOpen ? "gap-3 p-2 w-full" : "justify-center gap-0 p-2"
            )}
          >
            {profile.avatar ? (
              <img src={profile.avatar} alt="" className="w-7 h-7 rounded-full object-cover border border-border" referrerPolicy="no-referrer" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-semibold">
                {profile.username.charAt(0).toUpperCase()}
              </div>
            )}
            <div
              className={cn(
                "min-w-0 flex-1 overflow-hidden transition-[max-width,opacity,transform]",
                sidebarAnimation,
                isSidebarOpen ? "max-w-32 translate-x-0 opacity-100" : "max-w-0 -translate-x-2 opacity-0",
              )}
              aria-hidden={!isSidebarOpen}
            >
              <div className="truncate text-sm font-medium text-text-main">{profile.username}</div>
            </div>
          </Link>
        </div>
      </div>
    </aside>
  );
}
