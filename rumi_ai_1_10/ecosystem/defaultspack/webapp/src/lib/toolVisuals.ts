export type ToolVisualPoint = {
  id: string;
  label: string;
  xPercent: number;
  yPercent: number;
};

export type ToolVisualImage = {
  kind: "screenshot" | "zoom";
  src: string;
  sourceLabel: string;
  imageSize?: { width: number; height: number };
  cropBounds?: Record<string, unknown>;
  points: ToolVisualPoint[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

export function compactVisualSourceLabel(value: string): string {
  const normalized = value.trim().replace(/\\/g, "/");
  if (!normalized) return "";
  if (/^data:/i.test(normalized)) return "data url";
  if (/^blob:/i.test(normalized)) return "blob";
  try {
    if (/^https?:\/\//i.test(normalized)) {
      const url = new URL(normalized);
      const filename = url.pathname.split("/").filter(Boolean).pop();
      return filename || url.hostname;
    }
    if (/^file:\/\//i.test(normalized)) {
      const url = new URL(normalized);
      const filename = decodeURIComponent(url.pathname).split("/").filter(Boolean).pop();
      return filename || "file";
    }
  } catch {
    // Fall through to path compaction.
  }
  return normalized.split("/").filter(Boolean).pop() || normalized;
}

function nestedRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function imageSrcFromRecord(record: Record<string, unknown>): string {
  for (const key of ["visual_data_url", "visualDataUrl", "click_history_visual_data_url", "thumbnail_data_url", "thumbnailDataUrl"]) {
    const visualUrl = nonEmptyString(record[key]);
    if (visualUrl && visualUrl !== "[image data saved as artifact]") return visualUrl;
  }
  const dataUrl = nonEmptyString(record.data_url);
  if (dataUrl && dataUrl !== "[image data saved as artifact]") return dataUrl;
  const artifact = nestedRecord(record.artifact);
  return (
    nonEmptyString(record.click_history_visual_path)
    || nonEmptyString(record.visual_path)
    || nonEmptyString(record.path)
    || nonEmptyString(record.image_path)
    || nonEmptyString(record.model_image_path)
    || nonEmptyString(artifact.path)
  );
}

function normalizeImageSrc(src: string): string {
  if (/^(data:|https?:|file:|blob:)/i.test(src)) return src;
  if (src.startsWith("/")) {
    const tauriInternals = typeof window === "undefined"
      ? undefined
      : (window as Window & { __TAURI_INTERNALS__?: { convertFileSrc?: (filePath: string, protocol?: string) => string } }).__TAURI_INTERNALS__;
    return tauriInternals?.convertFileSrc?.(src, "asset") ?? `file://${src}`;
  }
  return src;
}

function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function sizeFrom(value: unknown): { width: number; height: number } | undefined {
  if (Array.isArray(value) && value.length >= 2) {
    const width = numberFrom(value[0]);
    const height = numberFrom(value[1]);
    return width && height ? { width, height } : undefined;
  }
  if (!isRecord(value)) return undefined;
  const width = numberFrom(value.width ?? value.w);
  const height = numberFrom(value.height ?? value.h);
  return width && height ? { width, height } : undefined;
}

function coordinateSize(record: Record<string, unknown>): { width: number; height: number } | undefined {
  const actionSize = sizeFrom(record.action_coordinate_system);
  return actionSize ?? sizeFrom(record.image_size) ?? sizeFrom(record.model_image_size);
}

function usesNormalizedCoordinates(record: Record<string, unknown>): boolean {
  const coordinateSystem = record.action_coordinate_system;
  if (typeof coordinateSystem === "string") return coordinateSystem.toLowerCase().includes("normalized");
  if (!isRecord(coordinateSystem)) return false;
  return [
    coordinateSystem.unit,
    coordinateSystem.space,
    coordinateSystem.type,
  ].some((value) => nonEmptyString(value).toLowerCase().includes("normalized"));
}

function pointFromRecord(value: Record<string, unknown>): { x: number; y: number; label?: string; coordinateSpace?: string } | null {
  const x = numberFrom(value.x ?? value.left);
  const y = numberFrom(value.y ?? value.top);
  if (x === null || y === null) return null;
  return {
    x,
    y,
    label: nonEmptyString(value.label) || nonEmptyString(value.name) || nonEmptyString(value.action) || undefined,
    coordinateSpace: nonEmptyString(value.coordinate_space) || nonEmptyString(value.space) || undefined,
  };
}

function collectRawPoints(value: unknown): Array<{ x: number; y: number; label?: string; coordinateSpace?: string }> {
  if (Array.isArray(value)) {
    return value.flatMap((entry) => {
      if (Array.isArray(entry) && entry.length >= 2) {
        const x = numberFrom(entry[0]);
        const y = numberFrom(entry[1]);
        return x === null || y === null ? [] : [{ x, y }];
      }
      if (isRecord(entry)) {
        const point = pointFromRecord(entry);
        return point ? [point] : collectRawPoints(entry);
      }
      return [];
    });
  }
  if (!isRecord(value)) return [];
  const direct = pointFromRecord(value);
  if (direct) return [direct];
  const nested = [value.point, value.position, value.coordinate, value.coordinates, value.target]
    .flatMap((entry) => collectRawPoints(entry));
  return nested;
}

function pointsFromRecord(record: Record<string, unknown>): ToolVisualPoint[] {
  const rawPoints = [
    ...collectRawPoints(record.annotation),
    ...collectRawPoints(record.overlay_points),
    ...collectRawPoints(record.click_history_overlay_points),
    ...collectRawPoints(record.display_overlay_points),
    ...collectRawPoints(record.cursor),
  ];
  const coordinateSystem = isRecord(record.action_coordinate_system) ? record.action_coordinate_system : {};
  const coordinateOrigin = {
    x: numberFrom(coordinateSystem.x) ?? 0,
    y: numberFrom(coordinateSystem.y) ?? 0,
  };
  const size = coordinateSize(record);

  return rawPoints.flatMap((point, index) => {
    const pointSpace = String(point.coordinateSpace ?? "").toLowerCase();
    const normalized = usesNormalizedCoordinates(record) || pointSpace.includes("normalized");
    const x = normalized ? point.x : point.x - coordinateOrigin.x;
    const y = normalized ? point.y : point.y - coordinateOrigin.y;
    const normalizedIsUnit = x >= 0 && x <= 1 && y >= 0 && y <= 1;
    const xPercent = normalized ? (normalizedIsUnit ? x * 100 : x / 10) : (!size && x >= 0 && x <= 1) ? x * 100 : size ? (x / size.width) * 100 : NaN;
    const yPercent = normalized ? (normalizedIsUnit ? y * 100 : y / 10) : (!size && y >= 0 && y <= 1) ? y * 100 : size ? (y / size.height) * 100 : NaN;
    if (!Number.isFinite(xPercent) || !Number.isFinite(yPercent)) return [];
    return [{
      id: `point-${index}`,
      label: point.label ?? (index === 0 ? "point" : `point ${index + 1}`),
      xPercent: Math.max(0, Math.min(100, xPercent)),
      yPercent: Math.max(0, Math.min(100, yPercent)),
    }];
  });
}

function findVisualRecord(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  if (
    imageSrcFromRecord(value)
    || value.crop_bounds
    || value.annotation
    || value.overlay_points
    || value.click_history_overlay_points
    || value.display_overlay_points
  ) {
    return value;
  }
  for (const key of ["data", "result", "output", "payload", "widget"]) {
    const nested = findVisualRecord(value[key]);
    if (nested) return nested;
  }
  return null;
}

export function extractToolVisual(value: unknown): ToolVisualImage | null {
  const record = findVisualRecord(value);
  if (!record) return null;
  const src = imageSrcFromRecord(record);
  if (!src) return null;
  const hasCrop = isRecord(record.crop_bounds);
  return {
    kind: hasCrop ? "zoom" : "screenshot",
    src: normalizeImageSrc(src),
    sourceLabel: compactVisualSourceLabel(
      nonEmptyString(record.click_history_visual_path)
      || nonEmptyString(record.visual_path)
      || nonEmptyString(record.path)
      || nonEmptyString(record.image_path)
      || nonEmptyString(record.model_image_path)
      || nonEmptyString(nestedRecord(record.artifact).path)
      || src,
    ),
    imageSize: sizeFrom(record.image_size) ?? sizeFrom(record.model_image_size),
    cropBounds: hasCrop ? record.crop_bounds as Record<string, unknown> : undefined,
    points: pointsFromRecord(record),
  };
}
