import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import {
  Fingerprint,
  Loader2,
  ShieldCheck,
  ShieldX,
  Smartphone,
  Sparkles,
  X,
} from "lucide-react";

import { mobileApiResources } from "../features/mobile/resources/mobileApiResources";
import type {
  MobilePairingReview,
  MobilePairingStatus,
} from "../features/mobile/resources/mobileApiResources";
import {
  LiquidButton,
  LiquidCard,
  LiquidPill,
  ScopeChip,
  SecurityRow,
  StatusDots,
} from "./liquidParts";

type MobilePairingApprovalProps = {
  pairingId: string;
  onApproved?: (pairingId: string) => void;
  onRejected?: (pairingId: string) => void;
  onExpired?: (pairingId: string) => void;
  onClose?: () => void;
};

const EMPTY_SCOPES: string[] = [];

const SCOPE_LABELS: Record<string, string> = {
  "chat.read": "PCのチャットを読む",
  "chat.write": "PCへメッセージを送る",
  "tools.observe": "PCの作業状況を見る",
  "authority.request.list": "承認一覧を見る",
  "authority.request.read": "承認内容を見る",
  "authority.request.approve": "PCの承認を許可",
  "authority.request.deny": "PCの拒否を許可",
  "credentials.request": "API設定を受け取る",
};

function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

function isElevatedScope(scope: string): boolean {
  return scope.startsWith("authority.") || scope.startsWith("credentials.");
}

function shortHash(value?: string): string {
  if (!value) return "";
  return value.replace(/^sha256:/, "").slice(0, 12);
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
        // Keep this quiet; the admin review request below drives the safety UI.
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
    if (status && status.status !== "claimed") {
      setReview(null);
      setReviewError("");
      return;
    }
    if (review?.pairing.pairing_id === pairingId || reviewBusy || reviewError) return;
    void loadReview();
  }, [loadReview, pairingId, review?.pairing.pairing_id, reviewBusy, reviewError, status]);

  const claim = review?.claim;
  const requestedScopes = claim?.requested_scopes ?? EMPTY_SCOPES;
  const elevatedScopes = useMemo(() => requestedScopes.filter(isElevatedScope), [requestedScopes]);
  const safeScopes = useMemo(() => requestedScopes.filter((scope) => !isElevatedScope(scope)), [requestedScopes]);
  const canApprove = busy === "" && Boolean(review) && !reviewBusy && !reviewError;

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

  const isFinished =
    status?.status === "approved" ||
    status?.status === "rejected" ||
    status?.status === "expired";

  if (isFinished) return null;

  const approvalCard = (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
        animate={{ opacity: 1, backdropFilter: "blur(16px)" }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 rumi-layer-modal flex items-center justify-center bg-black/60 p-4"
      >
        <motion.div
          initial={{ y: 20, scale: 0.94, opacity: 0 }}
          animate={{ y: 0, scale: 1, opacity: 1 }}
          exit={{ y: 14, scale: 0.96, opacity: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
          className="rumi-liquid-shell w-full max-w-lg p-1"
        >
          <div className="relative rounded-[30px] p-5 sm:p-6">
            <button
              type="button"
              onClick={onClose}
              className="absolute right-4 top-4 rounded-full border border-white/10 bg-white/5 p-2 text-zinc-400 transition hover:bg-white/10 hover:text-white"
              aria-label="閉じる"
            >
              <X size={16} />
            </button>

            <div className="pr-10">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[11px] text-zinc-200">
                <Sparkles size={12} className="text-cyan-200" />
                スマホからの接続リクエスト
              </div>
              <h3 className="mt-4 text-2xl font-black tracking-tight text-white">
                このスマホをつなぎますか？
              </h3>
              <p className="mt-2 text-sm leading-6 text-zinc-300">
                スマホ側に表示されている確認コードと一致することを確かめてから承認してください。
              </p>
            </div>

            <div className="mt-5 space-y-3">
              {reviewBusy && !review && (
                <LiquidCard className="flex items-center gap-3 p-4 text-sm text-zinc-300">
                  <Loader2 size={17} className="animate-spin text-cyan-200" />
                  <span>接続要求の詳細を確認しています</span>
                  <StatusDots />
                </LiquidCard>
              )}

              {reviewError && !review && (
                <LiquidCard className="p-4">
                  <div className="text-sm font-bold text-amber-100">詳細を確認できませんでした</div>
                  <p className="mt-1 text-xs leading-5 text-amber-100/75">
                    安全のため、端末名・確認コード・権限を確認できるまで承認できません。
                  </p>
                  <LiquidButton
                    quiet
                    type="button"
                    disabled={reviewBusy}
                    busy={reviewBusy}
                    onClick={() => void loadReview()}
                    className="mt-3"
                  >
                    もう一度確認
                  </LiquidButton>
                </LiquidCard>
              )}

              {review && (
                <>
                  <LiquidCard className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/10 text-cyan-100">
                        <Smartphone size={22} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                          Device
                        </div>
                        <div className="truncate text-base font-extrabold text-white">
                          {claim?.device_label || "Rumi Mobile"}
                        </div>
                        {claim?.device_id_preview && (
                          <div className="mt-0.5 truncate font-mono text-[11px] text-zinc-500">
                            {claim.device_id_preview}
                          </div>
                        )}
                      </div>
                    </div>
                  </LiquidCard>

                  <LiquidCard className="p-4 text-center">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-200/80">
                      合言葉
                    </div>
                    <div className="mt-2 flex justify-center">
                      <div className="rumi-code-badge">{claim?.verification_code || "確認中"}</div>
                    </div>
                    <p className="mt-3 text-xs leading-5 text-zinc-400">
                      スマホに出ているコードと同じなら、この接続要求は同じ端末から来ています。
                    </p>
                  </LiquidCard>

                  <LiquidCard className="p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                          Permissions
                        </div>
                        <div className="mt-1 text-sm font-bold text-white">このスマホでできること</div>
                      </div>
                      <LiquidPill tone={elevatedScopes.length > 0 ? "violet" : "mint"}>
                        {elevatedScopes.length > 0 ? "追加権限あり" : "最小権限"}
                      </LiquidPill>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {safeScopes.map((scope) => (
                        <ScopeChip key={scope} label={scopeLabel(scope)} />
                      ))}
                      {elevatedScopes.map((scope) => (
                        <span
                          key={scope}
                          className="inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-xs text-amber-100"
                        >
                          {scopeLabel(scope)}
                        </span>
                      ))}
                    </div>
                  </LiquidCard>

                  <LiquidCard className="p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                      Safety
                    </div>
                    <div className="mt-3 space-y-2">
                      <SecurityRow>端末トークンはスマホの公開鍵で暗号化して受け渡します。</SecurityRow>
                      <SecurityRow>pickup は POST body だけで使い、URLには載せません。</SecurityRow>
                      {elevatedScopes.length === 0 && (
                        <SecurityRow>APIキー転送やPC承認操作は、この接続には含まれていません。</SecurityRow>
                      )}
                    </div>
                    <details className="mt-3 rounded-2xl border border-white/10 bg-black/15 p-3 text-[11px] text-zinc-500">
                      <summary className="cursor-pointer select-none font-bold text-zinc-400">
                        fingerprint
                      </summary>
                      <div className="mt-2 grid gap-2">
                        {claim?.encryption_key_fingerprint && (
                          <div className="flex items-center gap-2 font-mono">
                            <Fingerprint size={13} />
                            {claim.encryption_key_fingerprint}
                          </div>
                        )}
                        {claim?.signing_key_fingerprint && (
                          <div className="flex items-center gap-2 font-mono">
                            <ShieldCheck size={13} />
                            {claim.signing_key_fingerprint}
                          </div>
                        )}
                        <div className="font-mono">claim {shortHash(review.claim_hash)}</div>
                      </div>
                    </details>
                  </LiquidCard>
                </>
              )}
            </div>

            {(error || (reviewError && review)) && (
              <div className="mt-3 rounded-2xl border border-rose-300/25 bg-rose-400/10 px-4 py-3 text-xs text-rose-100">
                {error || reviewError}
              </div>
            )}

            <div className="mt-5 grid grid-cols-2 gap-3">
              <LiquidButton
                quiet
                danger
                type="button"
                disabled={busy !== ""}
                busy={busy === "reject"}
                onClick={() => void handleReject()}
              >
                <ShieldX size={15} />
                今回はやめる
              </LiquidButton>
              <LiquidButton
                type="button"
                disabled={!canApprove}
                busy={busy === "approve"}
                onClick={() => void handleApprove()}
              >
                <ShieldCheck size={15} />
                このスマホをつなぐ
              </LiquidButton>
            </div>

            {!canApprove && !reviewBusy && (
              <p className="mt-3 text-center text-[11px] text-zinc-500">
                詳細を確認できるまで承認できません。
              </p>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );

  if (typeof document === "undefined") return approvalCard;
  return createPortal(approvalCard, document.body);
}
