import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Button } from './Button';

export function DialogContainer() {
  const t = useT();
  const dialog = useAppStore(state => state.dialog);
  const closeDialog = useAppStore(state => state.closeDialog);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!dialog) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;

    const timer = setTimeout(() => {
      dialogRef.current?.focus();
    }, 0);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeDialog();
        return;
      }

      if (e.key === 'Tab') {
        const focusableElements = dialogRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusableElements || focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [dialog, closeDialog]);

  const handleConfirm = useCallback(() => {
    if (!dialog) return;
    dialog.onConfirm();
    closeDialog();
  }, [dialog, closeDialog]);

  if (!dialog) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in"
      onClick={closeDialog}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-description"
        tabIndex={-1}
        className="w-full max-w-md rounded-xl border border-border bg-bg-card p-6 shadow-xl animate-in zoom-in-95 outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="dialog-title" className="text-lg font-semibold text-text-main">{dialog.title}</h2>
        <p id="dialog-description" className="mt-2 text-sm text-text-muted">{dialog.message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={closeDialog}>
            {dialog.cancelText || t('dialog.cancel')}
          </Button>
          <Button onClick={handleConfirm}>
            {dialog.confirmText || t('dialog.confirm')}
          </Button>
        </div>
      </div>
    </div>
  );
}
