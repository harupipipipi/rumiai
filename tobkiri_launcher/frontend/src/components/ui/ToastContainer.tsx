import { useAppStore } from '@/src/store';
import { cn } from '@/src/lib/utils';
import { viewerLayers } from '@/src/lib/layers';
import { CheckCircle2, XCircle } from 'lucide-react';

import {CopyErrorButton} from './CopyErrorButton';

export function ToastContainer() {
  const toasts = useAppStore(state => state.toasts);

  return (
    <div
      className={cn("fixed bottom-4 right-4 flex flex-col gap-2", viewerLayers.toast)}
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
          <span className="min-w-0 flex-1 break-words">{toast.message}</span>
          {toast.type === 'error' ? (
            <CopyErrorButton
              label="Copy error notification"
              text={toast.message}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}
