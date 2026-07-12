export type AmbientDispatchDebugInfo = {
  model: string | null;
  deliveryMode: string | null;
  targetCapability: string | null;
};

export function ambientDispatchDebugInfo(result: Record<string, unknown> | null | undefined): AmbientDispatchDebugInfo {
  const records = nestedRecords(result);
  return {
    model: firstString(records, ["resolved_model", "model", "profile_id"]),
    deliveryMode: firstString(records, ["input_delivery_mode", "delivery_mode", "mode"], true),
    targetCapability: firstString(records, ["target_input_capability", "target_capability"]),
  };
}

export function ambientDeliveryModeLabel(mode: string | null | undefined): string {
  switch (String(mode ?? "").trim()) {
    case "audio_direct":
      return "音声を直接送信";
    case "audio_with_transcript":
      return "音声と文字起こしを送信";
    case "transcript":
    case "transcription_required":
      return "文字起こしを送信";
    case "text":
      return "テキストを送信";
    default:
      return "送信方法は応答で未指定";
  }
}

export function ambientTargetCapabilityLabel(capability: string | null | undefined): string {
  switch (String(capability ?? "").trim()) {
    case "audio":
      return "音声対応モデル";
    case "multimodal_no_audio":
      return "画像対応・音声非対応モデル";
    case "text":
      return "テキストモデル";
    default:
      return "能力未確認（安全側で文字送信）";
  }
}

function nestedRecords(value: Record<string, unknown> | null | undefined): Record<string, unknown>[] {
  if (!value) return [];
  const records = [value];
  for (const key of ["audio_delivery", "input_delivery", "dispatch", "dispatch_result", "result"]) {
    const candidate = value[key];
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      records.push(candidate as Record<string, unknown>);
    }
  }
  return records;
}

function firstString(records: Record<string, unknown>[], keys: string[], skipGenericMode = false): string | null {
  for (const record of records) {
    for (const key of keys) {
      const value = String(record[key] ?? "").trim();
      if (!value) continue;
      if (skipGenericMode && key === "mode" && !value.includes("audio") && value !== "transcript" && value !== "text") continue;
      return value;
    }
  }
  return null;
}
