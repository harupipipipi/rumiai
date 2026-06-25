import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import QRCode from "qrcode";
import {
  ChevronDown,
  Copy,
  Check,
  Smartphone,
  Apple,
  AppWindow,
  QrCode,
  RefreshCw,
  Loader2,
  Link2,
  Trash2,
  ShieldCheck,
} from "lucide-react";

import { cn } from "../lib/cn";
import { mobileApiResources } from "../features/mobile/resources/mobileApiResources";
import type { MobileDevice, P2PPairing } from "../features/mobile/resources/mobileApiResources";
import { buildMobilePairingBaseUrls, isLoopbackHost } from "../lib/mobilePairingUrls";
import { MobilePairingApproval } from "./MobilePairingApproval";

type AppsSettingsPanelProps = {
  kernelBaseUrl?: string;
  cloudflarePagesUrl?: string;
};

type PcConnectionPayload = {
  kind: "rumi_pc";
  baseUrl: string;
  token: string;
};

type ApiImportPayload = {
  kind: "rumi_api";
  baseUrl: string;
  apiKey: string;
  model?: string;
  label?: string;
};

type MobilePairQrPayload = {
  kind: "rumi_mobile_pair_v1";
  version: 1;
  pairingId: string;
  code: string;
  baseUrls: string[];
  manifestUrl: string;
  roles: ("mobile_client" | "mobile_approver")[];
  serverPublicKey: string;
  expiresAt: number;
};

function useQrDataUrl(value: string): { dataUrl: string | null; error: string | null } {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!value.trim()) {
      setDataUrl(null);
      setError(null);
      return;
    }
    QRCode.toDataURL(value, { errorCorrectionLevel: "M", margin: 2, width: 320 })
      .then((url) => {
        if (!cancelled) {
          setDataUrl(url);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setDataUrl(null);
          setError(err instanceof Error ? err.message : "QR生成に失敗しました");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [value]);
  return { dataUrl, error };
}

function QrCard({
  title,
  description,
  dataUrl,
  error,
  emptyHint,
}: {
  title: string;
  description: string;
  dataUrl: string | null;
  error: string | null;
  emptyHint: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
      <div className="flex items-center gap-2">
        <QrCode size={15} className="text-zinc-400" />
        <h4 className="text-sm font-medium text-zinc-100">{title}</h4>
      </div>
      <p className="mt-1 text-xs leading-5 text-zinc-500">{description}</p>
      <div className="mt-3 flex items-center justify-center rounded-lg border border-zinc-800 bg-black/40 p-3">
        {dataUrl ? (
          <img src={dataUrl} alt={title} className="h-48 w-48" />
        ) : (
          <div className="flex h-48 w-48 flex-col items-center justify-center text-center text-[11px] text-zinc-600">
            {error ? <span className="text-rose-300">{error}</span> : emptyHint}
          </div>
        )}
      </div>
    </div>
  );
}

function CopyField({
  label,
  value,
  placeholder,
  onChange,
  readOnly,
  mono,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange?: (next: string) => void;
  readOnly?: boolean;
  mono?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-medium uppercase text-zinc-500">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          readOnly={readOnly}
          placeholder={placeholder}
          onChange={(event) => onChange?.(event.target.value)}
          className={cn(
            "min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-600",
            mono && "font-mono",
          )}
        />
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(value);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-zinc-800 text-zinc-500 transition-colors hover:border-zinc-600 hover:text-zinc-200"
          title="コピー"
        >
          {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
        </button>
      </div>
    </label>
  );
}

function ComingSoonBadge() {
  return (
    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-200">
      Coming soon
    </span>
  );
}

function lanHost() {
  if (typeof window === "undefined") return "";
  const host = window.location.hostname;
  if (isLoopbackHost(host)) {
    return "";
  }
  return host;
}

function windowOrigin() {
  if (typeof window === "undefined") return "";
  return window.location?.origin ?? "";
}

function formatRelativeTime(isoString: string | undefined): string {
  if (!isoString) return "不明";
  const date = new Date(isoString);
  const now = Date.now();
  const diffMs = now - date.getTime();
  if (diffMs < 0) return "たった今";
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "たった今";
  if (diffMin < 60) return `${diffMin}分前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}時間前`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}日前`;
}

function PairingV2Section({ kernelBaseUrl }: { kernelBaseUrl?: string }) {
  const [pairing, setPairing] = useState<P2PPairing | null>(null);
  const [manualBaseUrl, setManualBaseUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showApproval, setShowApproval] = useState(false);
  const mountedRef = useRef(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  const startPairing = async () => {
    setBusy(true);
    setError("");
    setPairing(null);
    setManualBaseUrl("");
    setShowApproval(false);
    try {
      const result = await mobileApiResources.startPairing({
        capabilities: [
          "chat.read",
          "chat.write",
          "tools.observe",
          "authority.request.list",
          "authority.request.read",
          "authority.request.approve",
          "authority.request.deny",
          "credentials.request",
        ],
      });
      if (!mountedRef.current) return;
      setPairing(result.pairing);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "ペアリングの開始に失敗しました");
      }
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  };

  useEffect(() => {
    if (!pairing || pairing.status !== "pending") {
      stopPolling();
      return;
    }
    let disposed = false;
    const poll = async () => {
      try {
        const status = await mobileApiResources.getPairingStatus(pairing.pairing_id);
        if (disposed || !mountedRef.current) return;
        if (status.status === "claimed") {
          setShowApproval(true);
          stopPolling();
        } else if (status.status === "approved" || status.status === "rejected" || status.status === "expired") {
          stopPolling();
          if (status.status === "approved") {
            setPairing((prev) => prev ? { ...prev, status: "approved" } : prev);
          }
        }
      } catch {
        // ignore transient poll errors
      }
    };
    pollRef.current = setInterval(() => void poll(), 2000);
    return () => {
      disposed = true;
      stopPolling();
    };
  }, [pairing, stopPolling]);

  const advertisedBaseUrls = useMemo(
    () => pairing?.base_urls?.filter((value): value is string => typeof value === "string") ?? [],
    [pairing?.base_urls],
  );
  const currentOrigin = windowOrigin();
  const qrBaseUrls = useMemo(
    () => buildMobilePairingBaseUrls([manualBaseUrl, ...advertisedBaseUrls, kernelBaseUrl, currentOrigin]),
    [advertisedBaseUrls, currentOrigin, kernelBaseUrl, manualBaseUrl],
  );

  const qrPayload: MobilePairQrPayload | null = pairing && qrBaseUrls.length > 0 ? {
    kind: "rumi_mobile_pair_v1",
    version: 1,
    pairingId: pairing.pairing_id,
    code: pairing.code,
    baseUrls: qrBaseUrls,
    manifestUrl: `${qrBaseUrls[0].replace(/\/+$/, "")}/api/mobile/v1/manifest`,
    roles: ["mobile_client", "mobile_approver"],
    serverPublicKey: "",
    expiresAt: pairing.expires_at,
  } : null;

  const qrValue = qrPayload ? JSON.stringify(qrPayload) : "";
  const qr = useQrDataUrl(qrValue);

  const isExpired = pairing ? pairing.expires_at * 1000 < Date.now() : false;
  const isFinished = pairing?.status === "approved" || pairing?.status === "rejected" || isExpired;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="flex items-center gap-2">
        <Link2 size={15} className="text-zinc-400" />
        <h4 className="text-sm font-medium text-zinc-100">スマホをペアリング</h4>
      </div>
      <p className="mt-1 text-xs leading-5 text-zinc-500">
        ペアリングQRを生成してスマホアプリでスキャンすると、PCと安全に接続できます。
      </p>

      {!pairing || isFinished ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void startPairing()}
          className={cn(
            "mt-3 inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
            busy
              ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
              : "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500",
          )}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Smartphone size={14} />}
          ペアリングを開始
        </button>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="flex items-center justify-center rounded-lg border border-zinc-800 bg-black/40 p-3">
            {qr.dataUrl ? (
              <img src={qr.dataUrl} alt="ペアリングQR" className="h-56 w-56" />
            ) : (
              <div className="flex h-56 w-56 items-center justify-center text-[11px] text-zinc-600">
                {qr.error ? (
                  <span className="text-rose-300">{qr.error}</span>
                ) : qrBaseUrls.length === 0 ? (
                  "LAN URLを入力するとQRが表示されます。"
                ) : (
                  "QRを生成中..."
                )}
              </div>
            )}
          </div>

          <CopyField
            label="PC LAN URL"
            value={manualBaseUrl || qrBaseUrls[0] || ""}
            onChange={setManualBaseUrl}
            placeholder="http://192.168.x.x:8765"
            mono
          />

          {qrBaseUrls.length === 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-amber-200">
              スマホから到達できるPCのLAN URLを検出できませんでした。localhostでは接続できないため、PCのLAN IPを入力してください。
            </div>
          )}

          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-center">
            <div className="text-[11px] uppercase text-emerald-400">確認コード</div>
            <div className="mt-1 text-lg font-semibold text-emerald-200">{pairing.code}</div>
          </div>

          <div className="text-center text-[11px] text-zinc-500">
            スマホアプリでこのQRをスキャンしてください
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
          {error}
        </div>
      )}

      {pairing && showApproval && (
        <MobilePairingApproval
          pairingId={pairing.pairing_id}
          onApproved={() => {
            setShowApproval(false);
            setPairing((prev) => prev ? { ...prev, status: "approved" } : prev);
          }}
          onRejected={() => {
            setShowApproval(false);
            setPairing((prev) => prev ? { ...prev, status: "rejected" } : prev);
          }}
          onExpired={() => {
            setShowApproval(false);
          }}
          onClose={() => setShowApproval(false)}
        />
      )}
    </div>
  );
}

function DeviceManagementSection() {
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState<string>("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadDevices = useCallback(async () => {
    try {
      const result = await mobileApiResources.listDevices();
      if (mountedRef.current) setDevices(result.devices ?? []);
    } catch {
      // silent
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  const handleRevoke = async (deviceId: string) => {
    setRevoking(deviceId);
    try {
      await mobileApiResources.revokeDevice(deviceId);
      if (mountedRef.current) {
        setDevices((prev) => prev.filter((d) => d.device_id !== deviceId));
      }
    } catch {
      // silent
    } finally {
      if (mountedRef.current) setRevoking("");
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
        <div className="flex items-center gap-2">
          <Smartphone size={15} className="text-zinc-400" />
          <h4 className="text-sm font-medium text-zinc-100">ペア済み端末</h4>
        </div>
        <div className="mt-3 flex items-center justify-center py-4 text-zinc-500">
          <Loader2 size={16} className="animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="flex items-center gap-2">
        <ShieldCheck size={15} className="text-zinc-400" />
        <h4 className="text-sm font-medium text-zinc-100">ペア済み端末</h4>
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        ペアリング済みのモバイル端末を管理します。
      </p>

      {devices.length === 0 ? (
        <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center text-xs text-zinc-500">
          ペア済みの端末はありません
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {devices.map((device) => (
            <div
              key={device.device_id}
              className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2.5"
            >
              <Smartphone size={14} className="shrink-0 text-zinc-400" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-zinc-200">{device.label}</div>
                <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                  {device.scopes && device.scopes.length > 0 && (
                    <span>{device.scopes.join(", ")}</span>
                  )}
                  {device.last_seen_at && (
                    <span>最終接続: {formatRelativeTime(device.last_seen_at)}</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                disabled={revoking === device.device_id}
                onClick={() => void handleRevoke(device.device_id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] transition-colors",
                  revoking === device.device_id
                    ? "cursor-not-allowed border-zinc-800 text-zinc-600"
                    : "border-zinc-700 text-zinc-400 hover:border-rose-600 hover:text-rose-300",
                )}
              >
                {revoking === device.device_id ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Trash2 size={12} />
                )}
                取り消し
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LegacyQrSection({
  kernelBaseUrl,
  cloudflarePagesUrl,
}: {
  kernelBaseUrl?: string;
  cloudflarePagesUrl?: string;
}) {
  const defaultPcBase = useMemo(() => {
    const host = lanHost();
    const detected = buildMobilePairingBaseUrls([kernelBaseUrl, windowOrigin()])[0] ?? "";
    return detected
      ? detected
      : kernelBaseUrl && kernelBaseUrl.trim().length > 0
      ? kernelBaseUrl.trim()
      : host
        ? `http://${host}:8765`
        : "http://127.0.0.1:8765";
  }, [kernelBaseUrl]);

  const [pcBaseUrl, setPcBaseUrl] = useState(defaultPcBase);
  const [pcToken, setPcToken] = useState("");
  const [pagesUrl, setPagesUrl] = useState(cloudflarePagesUrl ?? "");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setPcBaseUrl(defaultPcBase);
  }, [defaultPcBase]);

  const pcPayload: PcConnectionPayload = useMemo(
    () => ({ kind: "rumi_pc", baseUrl: pcBaseUrl.trim(), token: pcToken.trim() }),
    [pcBaseUrl, pcToken],
  );
  const pcQrValue = useMemo(() => JSON.stringify(pcPayload), [pcPayload]);

  const pagesQr = useQrDataUrl(pagesUrl.trim());
  const pcQr = useQrDataUrl(pcQrValue);

  const apiImportPayload: ApiImportPayload = useMemo(
    () => ({ kind: "rumi_api", baseUrl: pcBaseUrl.trim(), apiKey: pcToken.trim() }),
    [pcBaseUrl, pcToken],
  );
  const apiImportText = useMemo(() => JSON.stringify(apiImportPayload), [apiImportPayload]);
  const apiQr = useQrDataUrl(apiImportText);

  const isLoopbackUrl = useMemo(() => {
    const host = (() => {
      try {
        return new URL(pcBaseUrl.trim()).hostname;
      } catch {
        return "";
      }
    })();
    return isLoopbackHost(host);
  }, [pcBaseUrl]);

  return (
    <details
      className="rounded-lg border border-zinc-800 bg-zinc-950/40"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer items-center gap-2 p-4 text-sm text-zinc-400 hover:text-zinc-200">
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
        上級者向け: 直接HMACキーで接続
      </summary>
      {open && (
        <div className="space-y-4 px-4 pb-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
              <div className="flex items-center gap-2">
                <Smartphone size={15} className="text-zinc-400" />
                <h4 className="text-sm font-medium text-zinc-100">PC接続QR (Legacy)</h4>
              </div>
              <p className="text-xs leading-5 text-zinc-500">
                スマホアプリでこのQRをスキャンすると、PCのKernel APIへ接続します。トークンは
                <code className="mx-1 rounded bg-zinc-900 px-1 py-0.5 text-[10px] text-zinc-300">rumi_ai_1_10/user_data/hmac_keys.json</code>
                のアクティブキーを貼り付けてください。
              </p>
              <CopyField label="Kernel API URL" value={pcBaseUrl} onChange={setPcBaseUrl} mono />
              <CopyField label="Bearer token" value={pcToken} onChange={setPcToken} placeholder="HMACKeyManager().get_active_key()" mono />
              <button
                type="button"
                onClick={() => setPcBaseUrl(defaultPcBase)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
              >
                <RefreshCw size={12} /> URLを再検出
              </button>
              {isLoopbackUrl && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-amber-200">
                  現在のURLはこのPC自身（localhost / 127.0.0.1）を指しています。スマホからは到達できません。PCのLAN IP（例: 192.168.x.x）を入力してください。
                </div>
              )}
              <QrCard
                title="PC接続QR"
                description="スマホの「PCに接続」からスキャン。"
                dataUrl={pcQr.dataUrl}
                error={pcQr.error}
                emptyHint="URLとトークンを入力するとQRが表示されます。"
              />
            </div>

            <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
              <div className="flex items-center gap-2">
                <AppWindow size={15} className="text-zinc-400" />
                <h4 className="text-sm font-medium text-zinc-100">Cloudflare Pages QR</h4>
              </div>
              <p className="text-xs leading-5 text-zinc-500">
                スマホアプリのランディング/接続ガイドをCloudflare Pagesで公開したURLを入力するとQRを発行します。スマホでスキャンして開けます。
              </p>
              <CopyField
                label="Cloudflare Pages URL"
                value={pagesUrl}
                onChange={setPagesUrl}
                placeholder="https://rumi-mobile.pages.dev"
                mono
              />
              <QrCard
                title="Cloudflare Pages QR"
                description="スマホカメラ/アプリでスキャンして開く。"
                dataUrl={pagesQr.dataUrl}
                error={pagesQr.error}
                emptyHint="Pages URLを入力するとQRが表示されます。"
              />
            </div>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
            <div className="flex items-center gap-2">
              <QrCode size={15} className="text-zinc-400" />
              <h4 className="text-sm font-medium text-zinc-100">API/モデル インポート用ペイロード</h4>
            </div>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              上のPC接続情報をAPI/モデルインポート形式で出力します。スマホアプリの「APIをQRで取り込む」でこのQRをスキャンすると、APIキーとエンドポイントを取り込めます。
            </p>
            <div className="mt-3">
              <QrCard
                title="API/モデル インポートQR"
                description="kind=rumi_api。baseUrlとapiKeyを取り込みます。"
                dataUrl={apiQr.dataUrl}
                error={apiQr.error}
                emptyHint="URLとキーを入力するとQRが表示されます。"
              />
            </div>
            <pre className="mt-3 overflow-x-auto rounded-lg border border-zinc-800 bg-black/40 p-3 text-[11px] leading-5 text-zinc-400">
{apiImportText}
            </pre>
          </div>
        </div>
      )}
    </details>
  );
}

export function AppsSettingsPanel({ kernelBaseUrl, cloudflarePagesUrl }: AppsSettingsPanelProps) {
  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-zinc-100">アプリ</h3>
        <p className="text-xs text-zinc-500">
          Rumi Mobileアプリの入手と、スマホからの接続に使うQRを発行します。スマホアプリでQRをスキャンしてPCと接続、あるいはAPI/モデルをインポートできます。
        </p>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
        <div className="flex items-center gap-2">
          <Smartphone size={15} className="text-zinc-400" />
          <h4 className="text-sm font-medium text-zinc-100">アプリを入手</h4>
        </div>
        <p className="mt-1 text-xs text-zinc-500">現在はアプリ配信を準備中です。公開され次第、ここからインストールできるようになります。</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-3">
            <div className="flex items-center gap-3">
              <Apple size={18} className="text-zinc-300" />
              <div>
                <div className="text-sm text-zinc-200">TestFlight</div>
                <div className="text-[11px] text-zinc-500">iOSベータ版</div>
              </div>
            </div>
            <ComingSoonBadge />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-3">
            <div className="flex items-center gap-3">
              <AppWindow size={18} className="text-zinc-300" />
              <div>
                <div className="text-sm text-zinc-200">App Store</div>
                <div className="text-[11px] text-zinc-500">iOS / Android</div>
              </div>
            </div>
            <ComingSoonBadge />
          </div>
        </div>
      </div>

      <PairingV2Section kernelBaseUrl={kernelBaseUrl} />

      <DeviceManagementSection />

      <LegacyQrSection kernelBaseUrl={kernelBaseUrl} cloudflarePagesUrl={cloudflarePagesUrl} />
    </section>
  );
}
