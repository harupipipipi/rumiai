import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, Copy, House, MapPinOff } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';

import { Button } from '@/src/components/ui/Button';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';

export function NotFound() {
  const location = useLocation();
  const navigate = useNavigate();
  const t = useT();
  const [copied, setCopied] = useState(false);
  const resetCopiedTimer = useRef<number | undefined>(undefined);
  const diagnosticPath = `${location.pathname}${location.search}${location.hash}`;
  const canGoBack = location.key !== 'default';

  useEffect(() => () => {
    if (resetCopiedTimer.current !== undefined) {
      window.clearTimeout(resetCopiedTimer.current);
    }
  }, []);

  const copyPathWithSelection = () => {
    const textarea = document.createElement('textarea');
    textarea.value = diagnosticPath;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const succeeded = document.execCommand?.('copy') ?? false;
    textarea.remove();
    return succeeded;
  };

  const copyPath = async () => {
    let succeeded = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(diagnosticPath);
        succeeded = true;
      } else {
        succeeded = copyPathWithSelection();
      }
    } catch {
      succeeded = copyPathWithSelection();
    }

    setCopied(succeeded);
    if (!succeeded) return;
    if (resetCopiedTimer.current !== undefined) {
      window.clearTimeout(resetCopiedTimer.current);
    }
    resetCopiedTimer.current = window.setTimeout(() => setCopied(false), 2_000);
  };

  return (
    <section
      aria-labelledby="not-found-title"
      className="flex flex-1 items-center justify-center overflow-y-auto p-6 page-enter"
    >
      <div className="w-full max-w-xl rounded-2xl border border-border bg-bg-card p-6 shadow-sm sm:p-8">
        <div
          className="flex h-12 w-12 items-center justify-center rounded-xl bg-bg-hover text-text-muted"
          aria-hidden="true"
        >
          <MapPinOff className="size-6" />
        </div>
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-text-muted">
          {t('not_found.eyebrow')}
        </p>
        <h1 id="not-found-title" className="mt-2 text-2xl font-semibold tracking-tight text-text-main">
          {t('not_found.title')}
        </h1>
        <p className="mt-2 max-w-md text-sm leading-6 text-text-muted">
          {t('not_found.description')}
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Button className="min-h-11" onClick={() => navigate(panelRoutes.home)}>
            <House className="h-4 w-4" />
            {t('not_found.home')}
          </Button>
          {canGoBack && (
            <Button className="min-h-11" variant="outline" onClick={() => navigate(-1)}>
              <ArrowLeft className="h-4 w-4" />
              {t('not_found.back')}
            </Button>
          )}
        </div>

        <details className="mt-6 border-t border-border pt-4 text-sm">
          <summary className="flex min-h-11 cursor-pointer items-center rounded text-text-muted outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]">
            {t('not_found.details')}
          </summary>
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-bg-hover p-3">
            <code className="min-w-0 flex-1 break-all text-xs text-text-muted">
              {diagnosticPath}
            </code>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-11 w-11 shrink-0"
              aria-label={copied ? t('not_found.copied') : t('not_found.copy_path')}
              title={copied ? t('not_found.copied') : t('not_found.copy_path')}
              onClick={() => void copyPath()}
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
            <span className="sr-only" aria-live="polite">
              {copied ? t('not_found.copied') : ''}
            </span>
          </div>
        </details>
      </div>
    </section>
  );
}
