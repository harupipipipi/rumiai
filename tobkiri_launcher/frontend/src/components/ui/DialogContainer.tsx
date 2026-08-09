import { useEffect, useRef, useCallback, useState } from 'react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { viewerLayers } from '@/src/lib/layers';
import { cn } from '@/src/lib/utils';
import { Button } from './Button';

export function DialogContainer() {
  const t = useT();
  const dialog = useAppStore(state => state.dialog);
  const closeDialog = useAppStore(state => state.closeDialog);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const isConfirmingRef = useRef(false);
  const [isConfirming, setIsConfirming] = useState(false);
  isConfirmingRef.current = isConfirming;

  useEffect(() => {
    if (!dialog) {
      setIsConfirming(false);
      return;
    }

    previousFocusRef.current = document.activeElement as HTMLElement | null;

    const timer = setTimeout(() => {
      dialogRef.current?.focus();
    }, 0);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (!isConfirmingRef.current) {
          closeDialog();
        }
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

  const handleClose = useCallback(() => {
    if (!isConfirming) {
      closeDialog();
    }
  }, [closeDialog, isConfirming]);

  const handleConfirm = useCallback(async () => {
    if (!dialog || isConfirmingRef.current) return;
    isConfirmingRef.current = true;
    setIsConfirming(true);
    try {
      await dialog.onConfirm();
      closeDialog();
    } catch (error) {
      console.error('Dialog confirmation failed:', error);
    } finally {
      isConfirmingRef.current = false;
      setIsConfirming(false);
    }
  }, [dialog, closeDialog]);

  if (!dialog) return null;

  return (
    <div
      className={cn("fixed inset-0 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in", viewerLayers.dialog)}
      onClick={handleClose}
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
          <Button variant="outline" onClick={handleClose} disabled={isConfirming}>
            {dialog.cancelText || t('dialog.cancel')}
          </Button>
          <Button onClick={handleConfirm} loading={isConfirming}>
            {isConfirming
              ? (dialog.confirmPendingText || t('dialog.pending'))
              : (dialog.confirmText || t('dialog.confirm'))}
          </Button>
        </div>
      </div>
    </div>
  );
}
