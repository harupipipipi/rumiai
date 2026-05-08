import { useAppStore } from '@/src/store';
import { cn } from '@/src/lib/utils';
import { CheckCircle2, XCircle } from 'lucide-react';

export function ToastContainer() {
  const toasts = useAppStore(state => state.toasts);

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      aria-live="polite"
      aria-atomic="false"
      role="status"
    >
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={cn(
            "flex items-center gap-2 rounded-md px-4 py-3 text-sm font-medium text-white shadow-lg transition-all animate-in slide-in-from-bottom-5",
            toast.type === 'success' ? 'bg-green-600' : 'bg-red-600'
          )}
          role="alert"
        >
          {toast.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
          {toast.message}
        </div>
      ))}
    </div>
  );
}
