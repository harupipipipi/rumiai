import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';

export function Header() {
  const t = useT();
  const profile = useAppStore(state => state.profile);

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-bg-header px-6 transition-colors duration-200 shrink-0 z-40">
      <div className="flex items-center gap-3">
        <img src="https://picsum.photos/seed/rumi/64/64" alt="Rumi Logo" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
        <span className="text-lg font-bold text-text-main tracking-tight">Rumi AI</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-text-muted">{profile.username}</span>
        <img src={profile.avatar} alt="User Avatar" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
      </div>
    </header>
  );
}
