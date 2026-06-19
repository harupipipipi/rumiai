import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { Copy, Check, Smartphone, Apple, AppWindow, QrCode, RefreshCw } from "lucide-react";

import { cn } from "../lib/cn";

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
  if (!host || host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0") {
    return "";
  }
  return host;
}

export function AppsSettingsPanel({ kernelBaseUrl, cloudflarePagesUrl }: AppsSettingsPanelProps) {
  const defaultPcBase = useMemo(() => {
    const host = lanHost();
    return kernelBaseUrl && kernelBaseUrl.trim().length > 0
      ? kernelBaseUrl.trim()
      : host
        ? `http://${host}:8765`
        : "http://127.0.0.1:8765";
  }, [kernelBaseUrl]);

  const [pcBaseUrl, setPcBaseUrl] = useState(defaultPcBase);
  const [pcToken, setPcToken] = useState("");
  const [pagesUrl, setPagesUrl] = useState(cloudflarePagesUrl ?? "");

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
    return host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host === "";
  }, [pcBaseUrl]);

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

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
          <div className="flex items-center gap-2">
            <Smartphone size={15} className="text-zinc-400" />
            <h4 className="text-sm font-medium text-zinc-100">PC接続QR</h4>
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

        <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
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

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
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
    </section>
  );
}
