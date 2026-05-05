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

function imageSrcFromRecord(record: Record<string, unknown>): string {
  for (const key of ["visual_data_url", "visualDataUrl", "thumbnail_data_url", "thumbnailDataUrl"]) {
    const visualUrl = nonEmptyString(record[key]);
    if (visualUrl && visualUrl !== "[image data saved as artifact]") return visualUrl;
  }
  const dataUrl = nonEmptyString(record.data_url);
  if (dataUrl && dataUrl !== "[image data saved as artifact]") return dataUrl;
  return nonEmptyString(record.path) || nonEmptyString(record.image_path) || nonEmptyString(record.model_image_path);
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

function pointFromRecord(value: Record<string, unknown>): { x: number; y: number; label?: string } | null {
  const x = numberFrom(value.x ?? value.left);
  const y = numberFrom(value.y ?? value.top);
  if (x === null || y === null) return null;
  return {
    x,
    y,
    label: nonEmptyString(value.label) || nonEmptyString(value.name) || nonEmptyString(value.action) || undefined,
  };
}

function collectRawPoints(value: unknown): Array<{ x: number; y: number; label?: string }> {
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
    ...collectRawPoints(record.cursor),
  ];
  const coordinateSystem = isRecord(record.action_coordinate_system) ? record.action_coordinate_system : {};
  const coordinateOrigin = {
    x: numberFrom(coordinateSystem.x) ?? 0,
    y: numberFrom(coordinateSystem.y) ?? 0,
  };
  const size = coordinateSize(record);
  const normalized = usesNormalizedCoordinates(record);

  return rawPoints.flatMap((point, index) => {
    const x = normalized ? point.x : point.x - coordinateOrigin.x;
    const y = normalized ? point.y : point.y - coordinateOrigin.y;
    const xPercent = normalized || (!size && x >= 0 && x <= 1) ? x * 100 : size ? (x / size.width) * 100 : NaN;
    const yPercent = normalized || (!size && y >= 0 && y <= 1) ? y * 100 : size ? (y / size.height) * 100 : NaN;
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
    sourceLabel: nonEmptyString(record.path) || nonEmptyString(record.image_path) || nonEmptyString(record.model_image_path) || "data_url",
    imageSize: sizeFrom(record.image_size) ?? sizeFrom(record.model_image_size),
    cropBounds: hasCrop ? record.crop_bounds as Record<string, unknown> : undefined,
    points: pointsFromRecord(record),
  };
}
