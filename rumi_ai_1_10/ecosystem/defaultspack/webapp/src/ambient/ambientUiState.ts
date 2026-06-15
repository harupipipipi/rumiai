import type { AmbientPermissionId, AmbientStatus } from "./ambientTriggerClient";

export const AMBIENT_REQUIRED_PERMISSIONS: AmbientPermissionId[] = [
  "microphone.capture",
  "camera.capture",
  "ambient.trigger.dispatch",
];

export const AMBIENT_AUTHORITY_REQUEST_ID = "rumi_ambient_trigger_pack";

export const AMBIENT_OS_PERMISSIONS: AmbientPermissionId[] = [
  "microphone.capture",
  "camera.capture",
];

export type AmbientPermissionBucket = "unknown" | "prompt" | "granted" | "denied" | "blocked";

export type AmbientRuntimeStatus =
  | "off"
  | "monitoring"
  | "recording"
  | "sending"
  | "paused"
  | "blocked"
  | "error";

export type AmbientUiState =
  | "setupNeeded"
  | "rumiPermissionNeeded"
  | "osPermissionNeeded"
  | "readyOff"
  | "monitoring"
  | "recording"
  | "sending"
  | "paused"
  | "denied"
  | "blocked"
  | "error";

type AmbientStateCopy = {
  badge: string;
  headline: string;
  body: string;
  primary: string;
  tone: "amber" | "blue" | "emerald" | "red" | "purple" | "zinc";
};

export const ambientPermissionLabels: Record<string, string> = {
  "microphone.capture": "マイク入力を使う",
  "camera.capture": "カメラで指の動きを見る",
  "ambient.trigger.dispatch": "音声をAIに送る",
};

export const ambientCopyJa = {
  title: "指で録音",
  subtitle: "Ambient Trigger",
  gestureShort: "指をくっつけている間だけ録音。離すとAIに送信。",
  privacyShort: "音声・映像は保存しません",
  auditShort: "履歴には使った時刻と結果だけ残します",
  states: {
    setupNeeded: {
      badge: "準備が必要",
      headline: "まずRumiでこの機能を許可してください",
      body: "Rumi許可の後に、端末のマイク・カメラ許可へ進みます",
      primary: "セットアップする",
      tone: "amber",
    },
    rumiPermissionNeeded: {
      badge: "Rumi許可が必要",
      headline: "Rumi内の許可が必要です",
      body: "この機能にマイク・カメラ・AI送信を許可してください",
      primary: "Rumiで許可する",
      tone: "amber",
    },
    osPermissionNeeded: {
      badge: "端末許可が必要",
      headline: "マイク・カメラを許可してください",
      body: "ブラウザまたはOSの確認画面で許可します",
      primary: "マイク・カメラを許可",
      tone: "amber",
    },
    readyOff: {
      badge: "停止中",
      headline: "手の認識を始めると録音できます",
      body: "Rumiと端末の許可は済んでいます。まだ手の認識は始めていません",
      primary: "手の認識を開始",
      tone: "zinc",
    },
    monitoring: {
      badge: "待機中",
      headline: "指をくっつけると録音します",
      body: "離すとAIに送信します",
      primary: "手の認識を停止",
      tone: "emerald",
    },
    recording: {
      badge: "録音中",
      headline: "指を離すとAIに送信します",
      body: "録音しています。保存はされません",
      primary: "キャンセル",
      tone: "red",
    },
    sending: {
      badge: "送信中",
      headline: "音声をAIに送っています",
      body: "送信後、待機に戻ります",
      primary: "送信中...",
      tone: "purple",
    },
    paused: {
      badge: "一時停止中",
      headline: "一時停止しています",
      body: "再開すると指の検出に戻ります",
      primary: "手の認識を再開",
      tone: "zinc",
    },
    denied: {
      badge: "許可が拒否されています",
      headline: "マイクまたはカメラが拒否されています",
      body: "設定から許可を変更して、再確認してください",
      primary: "設定方法を見る",
      tone: "red",
    },
    blocked: {
      badge: "利用できません",
      headline: "この環境では利用できません",
      body: "カメラ・マイク・ブラウザ設定を確認してください",
      primary: "解決方法を見る",
      tone: "red",
    },
    error: {
      badge: "エラー",
      headline: "問題が発生しました",
      body: "状態を確認して、もう一度お試しください",
      primary: "再確認",
      tone: "red",
    },
  } satisfies Record<AmbientUiState, AmbientStateCopy>,
};

export function deriveAmbientUiState(
  status: AmbientStatus | null,
  runtimeStatus: AmbientRuntimeStatus,
): AmbientUiState {
  if (runtimeStatus === "error") return "error";
  if (runtimeStatus === "blocked") return "blocked";

  if (!status) return "setupNeeded";

  const rumiStatuses = AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => rumiPermissionBucket(status, permissionId));
  const osStatuses = AMBIENT_OS_PERMISSIONS.map((permissionId) => osPermissionBucket(status, permissionId));

  const hasMissingRumi = rumiStatuses.some((permission) => permission !== "granted");
  const hasMissingOs = osStatuses.some((permission) => permission !== "granted");

  if (hasMissingRumi) {
    if (rumiStatuses.includes("blocked")) return "blocked";
    if (rumiStatuses.includes("denied")) return "denied";
    return hasMissingOs ? "setupNeeded" : "rumiPermissionNeeded";
  }
  if (hasMissingOs) {
    if (osStatuses.includes("blocked")) return "blocked";
    if (osStatuses.includes("denied")) return "denied";
    return "osPermissionNeeded";
  }

  if (runtimeStatus === "sending") return "sending";
  if (runtimeStatus === "recording") return "recording";
  if (runtimeStatus === "monitoring") return "monitoring";
  if (runtimeStatus === "paused") return "paused";

  return "readyOff";
}

export function rumiPermissionBucket(status: AmbientStatus | null, permissionId: AmbientPermissionId): AmbientPermissionBucket {
  const entry = status?.permissions.rumi[permissionId];
  if (entry?.granted) return "granted";
  return normalizePermissionStatus(entry?.status, "prompt");
}

export function osPermissionBucket(status: AmbientStatus | null, permissionId: AmbientPermissionId): AmbientPermissionBucket {
  const entry = status?.permissions.os[permissionId];
  if (entry?.granted) return "granted";
  return normalizePermissionStatus(entry?.status, "unknown");
}

export function grantedPermissionCount(status: AmbientStatus | null, permissionIds: AmbientPermissionId[], scope: "rumi" | "os"): number {
  return permissionIds.filter((permissionId) => (
    scope === "rumi"
      ? rumiPermissionBucket(status, permissionId) === "granted"
      : osPermissionBucket(status, permissionId) === "granted"
  )).length;
}

export function hasAllRumiPermissions(status: AmbientStatus | null): boolean {
  return grantedPermissionCount(status, AMBIENT_REQUIRED_PERMISSIONS, "rumi") === AMBIENT_REQUIRED_PERMISSIONS.length;
}

export function hasAllOsPermissions(status: AmbientStatus | null): boolean {
  return grantedPermissionCount(status, AMBIENT_OS_PERMISSIONS, "os") === AMBIENT_OS_PERMISSIONS.length;
}

export function permissionBucketLabel(bucket: AmbientPermissionBucket): string {
  switch (bucket) {
    case "granted":
      return "許可済み";
    case "denied":
      return "拒否";
    case "blocked":
      return "利用不可";
    case "prompt":
      return "未許可";
    default:
      return "未確認";
  }
}

function normalizePermissionStatus(value: string | undefined, fallback: AmbientPermissionBucket): AmbientPermissionBucket {
  const status = String(value ?? "").trim().toLowerCase();
  if (status === "granted" || status === "approved" || status === "allowed") return "granted";
  if (status === "denied" || status === "rejected") return "denied";
  if (status === "blocked" || status === "unsupported" || status === "unavailable") return "blocked";
  if (status === "prompt" || status === "missing" || status === "required") return "prompt";
  return fallback;
}
