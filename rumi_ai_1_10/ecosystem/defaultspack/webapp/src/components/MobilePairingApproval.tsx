import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, ShieldCheck, ShieldX, Smartphone, X } from "lucide-react";

import { cn } from "../lib/cn";
import { mobileApiResources } from "../features/mobile/resources/mobileApiResources";
import type { MobilePairingReview, MobilePairingStatus } from "../features/mobile/resources/mobileApiResources";

type MobilePairingApprovalProps = {
  pairingId: string;
  onApproved?: (pairingId: string) => void;
  onRejected?: (pairingId: string) => void;
  onExpired?: (pairingId: string) => void;
  onClose?: () => void;
};

const SCOPE_LABELS: Record<string, string> = {
  "chat.read": "チャットの読み取り",
  "chat.write": "チャットの送信",
  "tools.observe": "ツールの監視",
  "authority.request.list": "承認一覧の確認",
  "authority.request.read": "承認内容の確認",
  "authority.request.approve": "署名付き承認",
  "authority.request.deny": "署名付き拒否",
  "credentials.request": "API設定の受け取り",
};

function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

export function MobilePairingApproval({
  pairingId,
  onApproved,
  onRejected,
  onExpired,
  onClose,
}: MobilePairingApprovalProps) {
  const [status, setStatus] = useState<MobilePairingStatus | null>(null);
  const [review, setReview] = useState<MobilePairingReview | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | "">("");
  const [error, setError] = useState("");
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    setStatus(null);
    setReview(null);
    setReviewError("");
    setError("");
  }, [pairingId]);

  useEffect(() => {
    if (!pairingId) return;
    let disposed = false;

    const poll = async () => {
      try {
        const result = await mobileApiResources.getPairingStatus(pairingId);
        if (disposed || !mountedRef.current) return;
        setStatus(result);

        if (result.status === "approved") {
          stopPolling();
          onApproved?.(pairingId);
        } else if (result.status === "rejected") {
          stopPolling();
          onRejected?.(pairingId);
        } else if (result.status === "expired") {
          stopPolling();
          onExpired?.(pairingId);
        }
      } catch {
        // ignore transient poll errors
      }
    };

    void poll();
    pollingRef.current = setInterval(() => void poll(), 2000);

    return () => {
      disposed = true;
      stopPolling();
    };
  }, [pairingId, onApproved, onRejected, onExpired, stopPolling]);

  const loadReview = useCallback(async () => {
    setReviewBusy(true);
    setReviewError("");
    try {
      const result = await mobileApiResources.getPairingReview(pairingId);
      if (!mountedRef.current) return;
      setReview(result);
    } catch (err) {
      if (!mountedRef.current) return;
      setReview(null);
      setReviewError(err instanceof Error ? err.message : "接続要求の詳細を取得できませんでした");
    } finally {
      if (mountedRef.current) setReviewBusy(false);
    }
  }, [pairingId]);

  useEffect(() => {
    if (status?.status !== "claimed") {
      setReview(null);
      setReviewError("");
      return;
    }
    if (review?.pairing.pairing_id === pairingId || reviewBusy || reviewError) return;
    void loadReview();
  }, [loadReview, pairingId, review?.pairing.pairing_id, reviewBusy, reviewError, status?.status]);

  const handleApprove = async () => {
    if (!review) {
      setError("接続要求の詳細を取得してから承認してください");
      return;
    }
    setBusy("approve");
    setError("");
    try {
      await mobileApiResources.approvePairing(pairingId, {
        claim_hash: review.claim_hash,
        scopes: review.claim.requested_scopes,
      });
      onApproved?.(pairingId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "承認に失敗しました");
    } finally {
      if (mountedRef.current) setBusy("");
    }
  };

  const handleReject = async () => {
    setBusy("reject");
    setError("");
    try {
      await mobileApiResources.rejectPairing(pairingId);
      onRejected?.(pairingId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "拒否に失敗しました");
    } finally {
      if (mountedRef.current) setBusy("");
    }
  };

  const isClaimed = status?.status === "claimed";
  const isFinished = status?.status === "approved" || status?.status === "rejected" || status?.status === "expired";
  const confirmationCode = review?.claim.verification_code ?? "";
  const deviceLabel = review?.claim.device_label ?? "Rumi Mobile";
  const devicePreview = review?.claim.device_id_preview ?? "";
  const requestedScopes = review?.claim.requested_scopes ?? [];
  const hasElevatedScope = requestedScopes.some(
    (scope) => scope.startsWith("authority.") || scope.startsWith("credentials."),
  );
  const signingFingerprint = review?.claim.signing_key_fingerprint ?? "";
  const encryptionFingerprint = review?.claim.encryption_key_fingerprint ?? "";
  const canApprove = busy === "" && Boolean(review) && !reviewBusy && !reviewError;

  if (!isClaimed || isFinished) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 rumi-layer-modal flex items-center justify-center bg-black/60 p-4"
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="relative w-full max-w-md rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl"
        >
          <button
            type="button"
            onClick={onClose}
            className="absolute right-3 top-3 rounded-lg p-1 text-zinc-500 transition-colors hover:text-zinc-200"
          >
            <X size={16} />
          </button>

          <div className="p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900">
                <Smartphone size={18} className="text-zinc-300" />
              </div>
              <div>
                <h3 className="text-sm font-medium text-zinc-100">スマホからの接続要求</h3>
                <p className="text-xs text-zinc-500">新しいデバイスがペアリングを要求しています</p>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              {reviewBusy && !review && (
                <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
                  <Loader2 size={14} className="animate-spin" />
                  接続要求の詳細を確認しています
                </div>
              )}

              {reviewError && !review && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                  <div className="text-xs font-medium text-amber-100">接続要求の詳細を取得できませんでした</div>
                  <div className="mt-1 text-[11px] leading-5 text-amber-200/80">
                    安全のため、詳細を確認できるまで承認できません。
                  </div>
                  <button
                    type="button"
                    disabled={reviewBusy}
                    onClick={() => void loadReview()}
                    className="mt-3 inline-flex items-center gap-2 rounded-lg border border-amber-500/40 px-3 py-1.5 text-[11px] text-amber-100 hover:bg-amber-500/10 disabled:opacity-50"
                  >
                    {reviewBusy && <Loader2 size={12} className="animate-spin" />}
                    再試行
                  </button>
                </div>
              )}

              {review && (
                <>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                    <div className="text-[11px] uppercase text-zinc-500">デバイス</div>
                    <div className="mt-1 text-sm font-medium text-zinc-100">{deviceLabel}</div>
                    {devicePreview && <div className="mt-1 font-mono text-[11px] text-zinc-500">{devicePreview}</div>}
                  </div>

                  {confirmationCode && (
                    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-center">
                      <div className="text-[11px] uppercase text-emerald-400">確認コード</div>
                      <div className="mt-1 text-lg font-semibold text-emerald-200">{confirmationCode}</div>
                      <div className="mt-1 text-[11px] text-emerald-400/70">
                        スマホに表示されているコードと一致することを確認してください
                      </div>
                    </div>
                  )}

                  {requestedScopes.length > 0 && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                      <div className="text-[11px] uppercase text-zinc-500">許可する権限</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {requestedScopes.map((scope) => (
                          <span
                            key={scope}
                            className="rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300"
                          >
                            {scopeLabel(scope)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                    <div className="text-[11px] uppercase text-zinc-500">セキュリティ</div>
                    <div className="mt-2 space-y-1 text-[11px] text-zinc-400">
                      <div>トークンは端末公開鍵で暗号化</div>
                      <div>pickup secretはPOST bodyのみ</div>
                      {!hasElevatedScope && <div>APIキー転送/ツール承認は含まれません</div>}
                      {encryptionFingerprint && <div className="font-mono">{encryptionFingerprint}</div>}
                      {signingFingerprint && <div className="font-mono">{signingFingerprint}</div>}
                    </div>
                  </div>
                </>
              )}
            </div>

            {error && (
              <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
                {error}
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                disabled={busy !== ""}
                onClick={() => void handleReject()}
                className={cn(
                  "flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors",
                  busy === "reject"
                    ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                    : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100",
                )}
              >
                {busy === "reject" ? <Loader2 size={14} className="animate-spin" /> : <ShieldX size={14} />}
                拒否
              </button>
              <button
                type="button"
                disabled={!canApprove}
                onClick={() => void handleApprove()}
                className={cn(
                  "flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors",
                  !canApprove
                    ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                    : "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500",
                )}
              >
                {busy === "approve" ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                このスマホを許可
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
