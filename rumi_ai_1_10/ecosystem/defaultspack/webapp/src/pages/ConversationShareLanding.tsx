import { useEffect, useMemo, useState } from "react";
import { Download, Import, Loader2, ShieldCheck, X } from "lucide-react";

import { api, type ConversationShareRecord } from "../lib/api";


export function shareTokenFromPath(pathname: string): string {
  const match = /^\/share\/([^/]+)\/?$/.exec(pathname);
  return match ? decodeURIComponent(match[1]) : "";
}

export function shareImportDestination(conversationId: string): string {
  return `/chat?chat=${encodeURIComponent(conversationId)}`;
}

export function ImportedConversationNotice({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div role="status" className="mx-3 mt-3 flex items-start gap-3 border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
      <p className="min-w-0 flex-1 leading-5">Shared conversation imported. Some original files, attachments, tool outputs, local paths, or credentials may be unavailable.</p>
      <button type="button" title="Dismiss import notice" aria-label="Dismiss import notice" onClick={onDismiss} className="inline-flex h-7 w-7 shrink-0 items-center justify-center text-amber-200 hover:bg-amber-500/15">
        <X size={15} />
      </button>
    </div>
  );
}

export function ConversationShareLanding() {
  const token = shareTokenFromPath(window.location.pathname);
  const [record, setRecord] = useState<ConversationShareRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("This share link is invalid.");
      return;
    }
    void api.getShare(token).then(setRecord).catch(() => {
      setError("This shared conversation is missing, expired, or has been revoked.");
    });
  }, [token]);

  const summary = useMemo(() => {
    const bundle = record?.content;
    const conversation = bundle?.conversation?.conversation;
    return {
      title: String(bundle?.source?.title || conversation?.title || record?.title || "Shared conversation"),
      messageCount: conversation?.messages?.length ?? 0,
      omittedCount: bundle?.assets?.omitted?.length ?? 0,
      updatedAt: bundle?.conversation?.updated_at ? new Date(bundle.conversation.updated_at).toLocaleString() : "Unknown",
    };
  }, [record]);

  const importAndContinue = async () => {
    setImporting(true);
    setError(null);
    try {
      const result = await api.importShare(token, window.location.href);
      window.location.assign(shareImportDestination(result.conversation_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Import failed.");
      setImporting(false);
    }
  };

  const downloadHistory = () => {
    const conversation = record?.content?.conversation;
    if (!conversation) return;
    const blob = new Blob([JSON.stringify(conversation, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "history.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="min-h-screen bg-[#09090b] px-4 py-10 text-zinc-200 sm:px-8">
      <section className="mx-auto w-full max-w-2xl border border-zinc-800 bg-zinc-950 p-5 shadow-2xl sm:p-8">
        <div className="flex items-center gap-3 text-emerald-300">
          <ShieldCheck size={22} aria-hidden="true" />
          <span className="text-sm font-semibold">Redacted conversation share</span>
        </div>
        {error && !record ? (
          <div role="alert" className="mt-8 border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-100">
            {error}
          </div>
        ) : !record ? (
          <div role="status" className="mt-10 flex items-center gap-3 text-sm text-zinc-400">
            <Loader2 size={18} className="animate-spin" /> Loading shared conversation...
          </div>
        ) : (
          <>
            <h1 className="mt-6 break-words text-2xl font-semibold text-white sm:text-3xl">{summary.title}</h1>
            <dl className="mt-6 grid grid-cols-1 gap-px overflow-hidden border border-zinc-800 bg-zinc-800 sm:grid-cols-3">
              <div className="bg-zinc-950 p-4"><dt className="text-xs text-zinc-500">Messages</dt><dd className="mt-1 text-lg text-zinc-100">{summary.messageCount}</dd></div>
              <div className="bg-zinc-950 p-4"><dt className="text-xs text-zinc-500">Updated</dt><dd className="mt-1 text-sm text-zinc-100">{summary.updatedAt}</dd></div>
              <div className="bg-zinc-950 p-4"><dt className="text-xs text-zinc-500">Omitted assets</dt><dd className="mt-1 text-lg text-zinc-100">{summary.omittedCount}</dd></div>
            </dl>
            <div className="mt-6 border border-amber-500/25 bg-amber-500/10 p-4 text-sm leading-6 text-amber-100">
              Some original files, attachments, tool outputs, local paths, or credentials may be unavailable. Historical tool records will not run during import.
            </div>
            {error && <p role="alert" className="mt-4 text-sm text-red-300">{error}</p>}
            <div className="mt-8 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <button autoFocus type="button" disabled={importing} onClick={() => void importAndContinue()} className="inline-flex h-11 items-center justify-center gap-2 bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-60">
                {importing ? <Loader2 size={16} className="animate-spin" /> : <Import size={16} />} Import and continue
              </button>
              <button type="button" onClick={downloadHistory} className="inline-flex h-11 items-center justify-center gap-2 border border-zinc-700 px-4 text-sm font-semibold text-zinc-100 hover:bg-zinc-900">
                <Download size={16} /> Download history.json
              </button>
              <button type="button" onClick={() => window.location.assign("/chat")} className="inline-flex h-11 items-center justify-center gap-2 px-4 text-sm text-zinc-400 hover:text-white">
                <X size={16} /> Cancel
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
