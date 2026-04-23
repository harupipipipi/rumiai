import { useSearchParams, useLocation } from 'react-router-dom';
import { Search, ChevronDown } from 'lucide-react';
import { useAppStore } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';

export function Header() {
  const profile = useAppStore(state => state.profile);
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const isHome = location.pathname === panelRoutes.home;
  const searchValue = searchParams.get('q') ?? '';

  const updateSearchValue = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) {
      next.set('q', value);
    } else {
      next.delete('q');
    }
    setSearchParams(next, { replace: true });
  };

  return (
    <header className="z-40 flex h-[72px] shrink-0 items-center justify-between border-b border-border bg-bg-header px-6 transition-colors duration-200">
      <div className="flex items-center gap-3">
        <img src="https://picsum.photos/seed/rumi/64/64" alt="Rumi Logo" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
        <span className="text-lg font-bold text-text-main tracking-tight">Rumi AI</span>
      </div>

      {isHome ? (
        <label className="hidden min-w-[360px] max-w-[440px] flex-1 items-center gap-3 rounded-2xl border border-stone-800 bg-[#141414] px-4 py-3 text-stone-400 lg:flex">
          <Search className="h-4 w-4" />
          <input
            value={searchValue}
            onChange={(event) => updateSearchValue(event.target.value)}
            placeholder="Search profiles..."
            className="w-full bg-transparent text-sm text-stone-200 outline-none placeholder:text-stone-500"
          />
        </label>
      ) : (
        <div className="flex-1" />
      )}

      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-text-muted">{profile.username}</span>
        <ChevronDown className="h-4 w-4 text-text-muted" />
        <img src={profile.avatar} alt="User Avatar" className="h-9 w-9 rounded-full object-cover" referrerPolicy="no-referrer" />
      </div>
    </header>
  );
}
