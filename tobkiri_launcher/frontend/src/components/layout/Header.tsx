import { Link, useLocation } from 'react-router';
import { Menu } from 'lucide-react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { describeRuntimeStatus } from '@/src/lib/runtimeHealth';
import { isPanelRouteActive, panelRouteMeta, panelRouteTitleKey, panelRoutes, viewerNavGroups } from '@/src/lib/routes';
import { preloadPanelRoute } from '@/src/lib/routeModules';
import { Avatar } from '@/src/components/ui/Avatar';
import { Popover, PopoverContent, PopoverTrigger } from '@/src/components/ui/Popover';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);
  const runtimeDisconnected = useAppStore(state => state.runtimeDisconnected);
  const lastRuntimeHealthyAt = useAppStore(state => state.lastRuntimeHealthyAt);
  const location = useLocation();
  const runtimeStatusDescription = describeRuntimeStatus({
    runtimeReady,
    runtimeStatus,
    runtimeError,
    runtimeDisconnected,
    lastRuntimeHealthyAt,
  });
  const pageTitle = t(panelRouteTitleKey(location.pathname));

  return (
    <header
      data-tauri-drag-region
      className="z-40 flex h-14 shrink-0 items-center justify-between border-b border-border bg-bg-header px-6 transition-colors duration-[var(--transition-base)]"
    >
      <div className="flex min-w-0 items-center gap-3">
        <div className="md:hidden">
          <Popover>
            <PopoverTrigger className="rounded-md p-2 text-text-muted transition hover:bg-bg-hover hover:text-text-main" aria-label={t('nav.open_menu')} aria-haspopup="dialog">
              <Menu className="h-4 w-4" />
            </PopoverTrigger>
            <PopoverContent align="left" className="w-64" role="dialog" aria-label={t('nav.mobile_navigation')}>
              <nav aria-label={t('nav.mobile_navigation')} className="max-h-[70vh] overflow-y-auto p-1">
                {viewerNavGroups.map((group) => (
                  <div key={group.id} className="py-1">
                    <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted/70">
                      {t(group.labelKey)}
                    </div>
                    <div className="flex flex-col gap-1">
                      {group.routes.map((route) => {
                        const meta = panelRouteMeta[route];
                        const isActive = isPanelRouteActive(location.pathname, meta.path);
                        return (
                          <Link
                            key={route}
                            to={meta.path}
                            aria-current={isActive ? 'page' : undefined}
                            className={cn(
                              "min-h-11 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]",
                              isActive ? "bg-accent/8 text-accent" : "text-text-muted hover:bg-bg-hover hover:text-text-main",
                            )}
                          >
                            {t(meta.navKey || meta.titleKey)}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </nav>
            </PopoverContent>
          </Popover>
        </div>
        <h1 className="min-w-0 truncate text-sm font-medium text-text-main">{pageTitle}</h1>
      </div>

      <div className="flex items-center gap-3">
        {runtimeStatusDescription.kind === 'reconfirmation' ? (
          <Link
            to={panelRoutes.setup}
            className="rumi-control-pill inline-flex min-h-11 text-amber-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] dark:text-amber-400"
            aria-label={`${t(runtimeStatusDescription.labelKey)}. ${t('runtime.open_setup')}`}
            aria-live="polite"
            title={t(runtimeStatusDescription.detailKey)}
          >
            <span className="rumi-control-pill-dot bg-amber-500" />
            <span>{t(runtimeStatusDescription.labelKey)}</span>
          </Link>
        ) : runtimeStatusDescription.kind === 'healthy' ? (
          <div
            className="rumi-control-pill hidden text-emerald-600 dark:text-emerald-400 sm:inline-flex"
            role="status"
            aria-live="polite"
            title={t(runtimeStatusDescription.detailKey)}
          >
            <span className="rumi-control-pill-dot bg-emerald-500" />
            <span>{t(runtimeStatusDescription.labelKey)}</span>
          </div>
        ) : null}
        <Popover>
          <PopoverTrigger
            className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-left transition hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
            aria-label={`${profile.username} profile and settings`}
            aria-haspopup="dialog"
          >
            <span className="text-xs text-text-muted hidden sm:block">{profile.username}</span>
            <Avatar
              src={profile.avatar}
              username={profile.username}
              alt={`${profile.username} avatar`}
              className="size-7 text-xs"
            />
          </PopoverTrigger>
          <PopoverContent align="right" className="w-64" role="dialog" aria-label="Profile menu">
            <div className="border-b border-border px-3 py-2">
              <p className="truncate text-sm font-semibold text-text-main">{profile.username}</p>
              <p className="text-xs text-text-muted">Launcher-local profile</p>
            </div>
            <nav className="flex flex-col gap-1 p-1" aria-label="Profile and settings">
              {(['profile', 'settings'] as const).map((route) => {
                const meta = panelRouteMeta[route];
                const isActive = location.pathname === meta.path;
                return (
                  <Link
                    key={route}
                    to={meta.path}
                    aria-current={isActive ? 'page' : undefined}
                    onFocus={() => { void preloadPanelRoute(route); }}
                    onPointerEnter={() => { void preloadPanelRoute(route); }}
                    className={cn(
                      "flex min-h-11 items-center rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]",
                      isActive ? "bg-accent/8 text-accent" : "text-text-muted hover:bg-bg-hover hover:text-text-main",
                    )}
                  >
                    {t(meta.navKey || meta.titleKey)}
                  </Link>
                );
              })}
            </nav>
          </PopoverContent>
        </Popover>
      </div>
    </header>
  );
}
