import { useAppStore } from '@/src/store';
import { cn } from '@/src/lib/utils';
import { CheckCircle2, XCircle } from 'lucide-react';

export function ToastContainer() {
  const toasts = useAppStore(state => state.toasts);
  const theme = useAppStore(state => state.theme);
  const isCosmos = theme === 'Cosmos';

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      aria-live="polite"
      aria-atomic="false"
      role="status"
    >
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={cn(
            'pointer-events-auto cosmos-anim-fade-up flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium shadow-lg transition-all',
            isCosmos
              ? toast.type === 'success'
                ? 'cosmos-glass cosmos-halo-blue text-text-main'
                : 'cosmos-glass cosmos-halo-magenta text-text-main'
              : toast.type === 'success'
                ? 'bg-green-600 text-white'
                : 'bg-red-600 text-white',
          )}
          role="alert"
        >
          {toast.type === 'success' ? (
            <CheckCircle2
              className={cn('h-4 w-4', isCosmos && 'text-[color:var(--success)]')}
            />
          ) : (
            <XCircle className={cn('h-4 w-4', isCosmos && 'text-[color:var(--destructive)]')} />
          )}
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
