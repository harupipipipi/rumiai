import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Loader2, Send, Smartphone, X } from "lucide-react";

import { cn } from "../lib/cn";
import { mobileApiResources } from "../features/mobile/resources/mobileApiResources";
import type { MobileDevice } from "../features/mobile/resources/mobileApiResources";

type CredentialTransferModalProps = {
  providerId: string;
  providerLabel?: string;
  apiKey?: string;
  apiId?: string;
  baseUrl?: string;
  defaultModel?: string;
  onClose: () => void;
};

export function CredentialTransferModal({
  providerId,
  providerLabel,
  apiId,
  onClose,
}: CredentialTransferModalProps) {
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const result = await mobileApiResources.listDevices();
        if (disposed || !mountedRef.current) return;
        const onlineDevices = (result.devices ?? []).filter(
          (d) => d.status !== "revoked",
        );
        setDevices(onlineDevices);
      } catch {
        // silent
      } finally {
        if (!disposed && mountedRef.current) setLoading(false);
      }
    };
    void load();
    return () => {
      disposed = true;
    };
  }, []);

  const toggleDevice = (deviceId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(deviceId)) next.delete(deviceId);
      else next.add(deviceId);
      return next;
    });
  };

  const handleSend = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    setError("");
    try {
      throw new Error("端末へのAPI設定転送にはE2E暗号化が必要です。暗号化payloadを作成できないため送信しません。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  };

  const displayName = providerLabel || providerId;

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
            {done ? (
              <div className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
                  <Check size={24} className="text-emerald-400" />
                </div>
                <h3 className="mt-4 text-sm font-medium text-zinc-100">送信完了</h3>
                <p className="mt-1 text-xs text-zinc-500">
                  「{displayName}」のAPI設定を選択した端末に送信しました。
                </p>
                <button
                  type="button"
                  onClick={onClose}
                  className="mt-4 rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:border-zinc-500"
                >
                  閉じる
                </button>
              </div>
            ) : (
              <>
                <h3 className="text-sm font-medium text-zinc-100">API設定の転送</h3>
                <p className="mt-1 text-xs text-zinc-500">
                  {displayName}「{apiId ?? "main"}」を保存しました。このAPI設定をペア済みの端末にもコピーしますか？
                </p>

                <div className="mt-4">
                  {loading ? (
                    <div className="flex items-center justify-center py-6 text-zinc-500">
                      <Loader2 size={16} className="animate-spin" />
                    </div>
                  ) : devices.length === 0 ? (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center text-xs text-zinc-500">
                      オンラインのペア済み端末がありません
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {devices.map((device) => {
                        const isSelected = selected.has(device.device_id);
                        return (
                          <button
                            key={device.device_id}
                            type="button"
                            onClick={() => toggleDevice(device.device_id)}
                            className={cn(
                              "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                              isSelected
                                ? "border-emerald-500/50 bg-emerald-500/10"
                                : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700",
                            )}
                          >
                            <div
                              className={cn(
                                "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
                                isSelected
                                  ? "border-emerald-500 bg-emerald-500"
                                  : "border-zinc-700 bg-zinc-900",
                              )}
                            >
                              {isSelected && <Check size={12} className="text-white" />}
                            </div>
                            <Smartphone size={14} className="shrink-0 text-zinc-400" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm text-zinc-200">{device.label}</div>
                              {device.platform && (
                                <div className="text-[11px] text-zinc-500">{device.platform}</div>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {error && (
                  <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
                    {error}
                  </div>
                )}

                <div className="mt-5 flex gap-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="flex-1 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
                  >
                    PCだけで使う
                  </button>
                  <button
                    type="button"
                    disabled={busy || selected.size === 0}
                    onClick={() => void handleSend()}
                    className={cn(
                      "flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors",
                      busy || selected.size === 0
                        ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                        : "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500",
                    )}
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    このスマホにも送る
                  </button>
                </div>
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
