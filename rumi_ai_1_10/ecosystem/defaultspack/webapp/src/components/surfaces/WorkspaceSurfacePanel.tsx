import {
  AlignLeft,
  Bold,
  ChevronDown,
  Cloud,
  Film,
  Image as ImageIcon,
  Italic,
  Layers3,
  List,
  MonitorPlay,
  MousePointer2,
  PanelRight,
  Play,
  Printer,
  Redo2,
  Scissors,
  Send,
  Shapes,
  Share2,
  SlidersHorizontal,
  Subtitles,
  Type,
  Undo2,
  Video,
  Volume2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import type { SurfaceDescriptor } from "../../lib/api";

type WorkspaceSurfacePanelProps = {
  surface: SurfaceDescriptor;
  draft: string;
  onDraftChange: (value: string) => void;
  onAppendDraftToComposer: () => void;
  onClose?: () => void;
};

type ToolbarMode = "write" | "image" | "slide" | "movie";

type IconButtonProps = {
  label: string;
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
};

type MovieClip = {
  id: string;
  name: string;
  assetId: string;
  track: string;
  start: number;
  duration: number;
  inPoint: number;
  outPoint: number;
  color: string;
  source: string;
  rawSource: string;
  mimeType: string;
};

type MovieCaption = {
  id: string;
  text: string;
  start: number;
  duration: number;
};

type MovieAsset = {
  id: string;
  name: string;
  kind: string;
  duration: number;
  start: number;
  track: string;
  source: string;
  rawSource: string;
  mimeType: string;
};

type MovieProject = {
  projectId: string;
  title: string;
  brief: string;
  format: string;
  resolution: string;
  fps: number;
  clips: MovieClip[];
  captions: MovieCaption[];
  assets: MovieAsset[];
  audioGain: number;
  renderEnabled: boolean;
  timelineDuration: number;
  timelineTracks: string[];
  timelineMetadata: Record<string, unknown>;
};

type ImageProject = {
  projectId: string;
  prompt: string;
  mode: string;
  assets: MovieAsset[];
  variants: ImageVariant[];
};

type ImageVariant = {
  id: string;
  label: string;
  status: string;
  source: string;
  rawSource: string;
  assetId: string;
  mimeType: string;
};

type SlideAsset = {
  id: string;
  name: string;
  kind: string;
  source: string;
  rawSource: string;
  mimeType: string;
};

type SlideElement = {
  id: string;
  type: string;
  text: string;
  assetId: string;
  x: number;
  y: number;
  width: number;
  height: number;
  style: CSSProperties;
};

type Slide = {
  id: string;
  title: string;
  subtitle: string;
  layout: string;
  bullets: string[];
  notes: string;
  accent: string;
  assetIds: string[];
  elements: SlideElement[];
};

type SlideProject = {
  projectId: string;
  title: string;
  brief: string;
  themeName: string;
  slides: Slide[];
  assets: SlideAsset[];
  statusCards: { label: string; value: string; status: string }[];
  exportFormat: string;
  exportFilename: string;
  exportStatus: string;
};

const clipTone: Record<string, string> = {
  sky: "bg-sky-500",
  violet: "bg-violet-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-300",
  rose: "bg-rose-400",
  cyan: "bg-cyan-400",
};

const slideAccentTone: Record<string, string> = {
  blue: "bg-blue-500",
  emerald: "bg-emerald-400",
  amber: "bg-amber-300",
  rose: "bg-rose-400",
  violet: "bg-violet-400",
  cyan: "bg-cyan-400",
};

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function jsonRecordFromText(value: unknown): Record<string, unknown> {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return {};
  const unfenced = text.startsWith("```")
    ? text.replace(/^```[^\n]*\n?/, "").replace(/\n?```\s*$/, "").trim()
    : text;
  const candidates = [unfenced];
  const firstBrace = unfenced.indexOf("{");
  const lastBrace = unfenced.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) candidates.push(unfenced.slice(firstBrace, lastBrace + 1));
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      const record = recordValue(parsed);
      if (Object.keys(record).length) return record;
    } catch {
      // Natural-language drafts are expected here too.
    }
  }
  return {};
}

function structuredProjectFromPayload(
  payload: Record<string, unknown>,
  draft: string,
  keys: string[],
): Record<string, unknown> {
  for (const key of keys) {
    const direct = recordValue(payload[key]);
    if (Object.keys(direct).length) return direct;
  }
  for (const source of [payload.initial_text, draft]) {
    const parsed = jsonRecordFromText(source);
    if (!Object.keys(parsed).length) continue;
    for (const key of keys) {
      const nested = recordValue(parsed[key]);
      if (Object.keys(nested).length) return nested;
    }
    return parsed;
  }
  return {};
}

function naturalTextFromPayload(payload: Record<string, unknown>, draft: string): string {
  for (const source of [payload.initial_text, draft]) {
    const parsed = jsonRecordFromText(source);
    if (Object.keys(parsed).length) {
      const prose = stringValue(parsed.text ?? parsed.prompt, "");
      if (prose) return prose;
      continue;
    }
    const prose = stringValue(source, "");
    if (prose) return prose;
  }
  return "";
}

function safeMediaSource(value: unknown): string {
  const source = stringValue(value, "");
  if (!source || source.startsWith("generated:")) return "";
  if (/^data:(image\/(?!svg\+xml)|video\/|audio\/)/i.test(source)) return source;
  if (/^(https?:|blob:|\/|\.\.?\/)/i.test(source)) return source;
  if (/^[a-z0-9_@%+./-]+(?:\?[^\s]*)?$/i.test(source)) return source;
  return "";
}

function sanitizedSvgSource(value: unknown): string {
  let svg = typeof value === "string" ? value.trim() : "";
  if (/^data:image\/svg\+xml(?:;charset=[^,]+)?,/i.test(svg)) {
    try { svg = decodeURIComponent(svg.slice(svg.indexOf(",") + 1)); } catch { return ""; }
  }
  if (!svg.startsWith("<svg") || typeof DOMParser === "undefined" || typeof XMLSerializer === "undefined") return "";
  const documentNode = new DOMParser().parseFromString(svg, "image/svg+xml");
  if (documentNode.querySelector("parsererror")) return "";
  documentNode.querySelectorAll("script, foreignObject, iframe, object, embed").forEach((node) => node.remove());
  documentNode.querySelectorAll("*").forEach((node) => {
    Array.from(node.attributes).forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      const content = attribute.value.trim();
      if (name.startsWith("on") || ((name === "href" || name === "xlink:href") && !content.startsWith("#"))) {
        node.removeAttribute(attribute.name);
      }
    });
  });
  const sanitized = new XMLSerializer().serializeToString(documentNode.documentElement);
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(sanitized)}`;
}

function mediaSourceFromRecord(item: Record<string, unknown>): string {
  return sanitizedSvgSource(item.svg ?? item.svg_data)
    || safeMediaSource(item.source ?? item.path ?? item.url ?? item.data_uri ?? item.data ?? item.image ?? item.image_data);
}

function mediaKind(source: string, kind: unknown, mimeType: unknown): string {
  const explicit = stringValue(kind, "").toLowerCase();
  const mime = stringValue(mimeType, "").toLowerCase();
  if (explicit.startsWith("image/")) return "image";
  if (explicit.startsWith("video/")) return "video";
  if (explicit.startsWith("audio/")) return "audio";
  if (explicit) return explicit;
  if (mime.startsWith("image/") || /^data:image\//i.test(source)) return "image";
  if (mime.startsWith("video/") || /^data:video\//i.test(source)) return "video";
  if (mime.startsWith("audio/") || /^data:audio\//i.test(source)) return "audio";
  if (/\.(png|jpe?g|gif|webp|avif)(?:[?#]|$)/i.test(source)) return "image";
  if (/\.(mp4|webm|mov)(?:[?#]|$)/i.test(source)) return "video";
  return "file";
}

function percentage(value: unknown, fallback: number): number {
  const parsed = Number.parseFloat(String(value ?? ""));
  if (!Number.isFinite(parsed)) return fallback;
  const normalized = parsed > 0 && parsed <= 1 ? parsed * 100 : parsed;
  return Math.min(100, Math.max(0, normalized));
}

function safeElementStyle(value: unknown): CSSProperties {
  const raw = recordValue(value);
  const style: CSSProperties = {};
  const color = stringValue(raw.color, "");
  const background = stringValue(raw.background ?? raw.backgroundColor, "");
  if (/^(#[0-9a-f]{3,8}|rgba?\([\d\s,.%]+\)|hsla?\([\d\s,.%]+\)|[a-z]+)$/i.test(color)) style.color = color;
  if (/^(#[0-9a-f]{3,8}|rgba?\([\d\s,.%]+\)|hsla?\([\d\s,.%]+\)|[a-z]+)$/i.test(background)) style.backgroundColor = background;
  const fontSize = Number(raw.fontSize ?? raw.font_size);
  if (Number.isFinite(fontSize)) style.fontSize = `${Math.min(72, Math.max(8, fontSize))}px`;
  const weight = Number(raw.fontWeight ?? raw.font_weight);
  if (Number.isFinite(weight)) style.fontWeight = Math.min(900, Math.max(100, weight));
  const align = stringValue(raw.textAlign ?? raw.text_align, "");
  if (["left", "center", "right"].includes(align)) style.textAlign = align as CSSProperties["textAlign"];
  const fit = stringValue(raw.objectFit ?? raw.object_fit, "");
  if (["contain", "cover", "fill", "none", "scale-down"].includes(fit)) style.objectFit = fit as CSSProperties["objectFit"];
  const radius = Number(raw.borderRadius ?? raw.border_radius);
  if (Number.isFinite(radius)) style.borderRadius = `${Math.min(64, Math.max(0, radius))}px`;
  return style;
}

function arrayValue<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function stringValue(value: unknown, fallback = ""): string {
  if (value !== null && typeof value === "object") return fallback;
  const text = String(value ?? "").trim();
  return text || fallback;
}

function numberValue(value: unknown, fallback: number, minimum = 0): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minimum, Math.round(parsed * 100) / 100);
}

function cleanTitle(text: string, fallback: string): string {
  const firstLine = text
    .split(/\r?\n/)
    .map((line) => line.replace(/^#+\s*/, "").trim())
    .find(Boolean);
  return firstLine ? firstLine.slice(0, 72) : fallback;
}

function normalizeClip(raw: unknown, index: number, fallbackStart: number): MovieClip {
  const item = recordValue(raw);
  const start = numberValue(item.start, fallbackStart);
  const inPoint = numberValue(item.in ?? item.in_point, 0);
  const endDuration = numberValue(item.end, start, start) - start;
  const outPoint = item.out ?? item.out_point;
  const duration = numberValue(item.duration, hasOwn(item, "end") ? endDuration : numberValue(outPoint, inPoint + 4) - inPoint, 0.25);
  return {
    id: stringValue(item.id ?? item.clip_id, `clip-${index}`),
    name: stringValue(item.name ?? item.label, `Clip ${index}`),
    assetId: stringValue(item.asset_id ?? item.assetId, `asset-${index}`),
    track: stringValue(item.track, "video"),
    start,
    duration,
    inPoint,
    outPoint: numberValue(outPoint, inPoint + duration, inPoint + 0.25),
    color: stringValue(item.color, ["sky", "violet", "emerald", "amber"][index % 4]),
    source: mediaSourceFromRecord(item),
    rawSource: stringValue(item.source ?? item.path ?? item.url ?? item.data_uri, ""),
    mimeType: stringValue(item.mime_type ?? item.mimeType, ""),
  };
}

function normalizeCaption(raw: unknown, index: number): MovieCaption {
  const item = recordValue(raw);
  const start = numberValue(item.start, (index - 1) * 4);
  return {
    id: stringValue(item.id, `caption-${index}`),
    text: stringValue(item.text ?? item.caption ?? item.content, ""),
    start,
    duration: numberValue(item.duration, hasOwn(item, "end") ? numberValue(item.end, start, start) - start : 3, 0.25),
  };
}

function normalizeAsset(raw: unknown, index: number): MovieAsset {
  const item = recordValue(raw);
  const placement = recordValue(item.placement);
  const start = numberValue(item.start ?? placement.start, 0);
  const source = mediaSourceFromRecord(item);
  const rawSource = stringValue(item.source ?? item.path ?? item.url ?? item.data_uri, "");
  const mimeType = stringValue(item.mime_type ?? item.mimeType, "");
  const kind = mediaKind(source, item.kind ?? item.type, mimeType);
  return {
    id: stringValue(item.id ?? item.asset_id, `asset-${index}`),
    name: stringValue(item.name ?? item.label ?? item.asset_id, `Asset ${index}`),
    kind,
    duration: numberValue(item.duration, hasOwn(placement, "end") ? numberValue(placement.end, start, start) - start : 4, 0.25),
    start,
    track: stringValue(item.track, kind),
    source,
    rawSource,
    mimeType,
  };
}

function normalizeSlideAsset(raw: unknown, index: number): SlideAsset {
  const item = recordValue(raw);
  const source = mediaSourceFromRecord(item);
  const rawSource = stringValue(item.source ?? item.path ?? item.url ?? item.data_uri, "");
  const mimeType = stringValue(item.mime_type ?? item.mimeType, "");
  return {
    id: stringValue(item.id ?? item.asset_id, `asset-${index}`),
    name: stringValue(item.name ?? item.label ?? item.asset_id, `Asset ${index}`),
    kind: mediaKind(source, item.kind ?? item.type, mimeType),
    source,
    rawSource,
    mimeType,
  };
}

function normalizeSlideElement(raw: unknown, index: number): SlideElement {
  const item = recordValue(raw);
  return {
    id: stringValue(item.id, `element-${index}`),
    type: stringValue(item.type ?? item.kind, "text").toLowerCase(),
    text: stringValue(item.text ?? item.content ?? item.label, ""),
    assetId: stringValue(item.asset_id ?? item.assetId, ""),
    x: percentage(item.x ?? item.left, 0),
    y: percentage(item.y ?? item.top, 0),
    width: percentage(item.width ?? item.w, 100),
    height: percentage(item.height ?? item.h, 100),
    style: safeElementStyle(item.style),
  };
}

function normalizeStatusCard(raw: unknown, index: number): { label: string; value: string; status: string } {
  const item = recordValue(raw);
  return {
    label: stringValue(item.label ?? item.title, `Status ${index}`),
    value: stringValue(item.value ?? (item.progress === undefined ? "" : `${item.progress}%`), ""),
    status: stringValue(item.status, "ready"),
  };
}

function normalizeSlide(raw: unknown, index: number, fallbackAssetIds: string[]): Slide {
  const item = recordValue(raw);
  const rawBullets = item.bullets ?? item.points ?? item.content;
  const bullets = typeof rawBullets === "string"
    ? rawBullets.split(/\r?\n/).map((line) => line.replace(/^[-*#\d. ]+/, "").trim()).filter(Boolean)
    : arrayValue(rawBullets).map((bullet) => stringValue(bullet)).filter(Boolean);
  const rawAssetIds = arrayValue(item.asset_ids ?? item.assetIds ?? item.assets)
    .map((asset) => stringValue(recordValue(asset).id ?? recordValue(asset).asset_id ?? asset))
    .filter(Boolean);
  const elements = arrayValue(item.elements ?? recordValue(item.layout).elements).map(normalizeSlideElement);
  return {
    id: stringValue(item.id, `slide-${index}`),
    title: stringValue(item.title ?? item.heading, `Slide ${index}`),
    subtitle: stringValue(item.subtitle ?? item.summary, ""),
    layout: stringValue(recordValue(item.layout).name ?? item.layout, bullets.length ? "title-and-bullets" : "title"),
    bullets,
    notes: stringValue(item.notes ?? item.speaker_notes, ""),
    accent: stringValue(item.accent, ["blue", "emerald", "amber", "rose", "violet", "cyan"][(index - 1) % 6]),
    assetIds: rawAssetIds.length ? rawAssetIds : fallbackAssetIds.slice(index - 1, index),
    elements,
  };
}

function resequenceMovieProject(project: MovieProject): MovieProject {
  let cursor = 0;
  const clips = project.clips.map((clip) => {
    const next = { ...clip, start: cursor };
    cursor = Math.round((cursor + clip.duration) * 100) / 100;
    return next;
  });
  return { ...project, clips, timelineDuration: Math.max(cursor, project.timelineDuration) };
}

function defaultMovieProject(draft: string, surface: SurfaceDescriptor, assets: MovieAsset[] = []): MovieProject {
  const title = cleanTitle(draft, "Untitled movie");
  const clips = assets.map((asset, index) => ({
    id: `clip-${index + 1}`,
    name: asset.name,
    assetId: asset.id,
    track: asset.kind === "audio" ? "audio" : "video",
    start: 0,
    duration: asset.duration,
    inPoint: 0,
    outPoint: asset.duration,
    color: ["sky", "violet", "emerald", "amber"][(index + 1) % 4],
    source: asset.source,
    rawSource: asset.rawSource,
    mimeType: asset.mimeType,
  }));
  return resequenceMovieProject({
    projectId: surface.resourceId ?? surface.id,
    title,
    brief: draft,
    format: "16:9 / H.264",
    resolution: "1920x1080",
    fps: 30,
    renderEnabled: false,
    timelineDuration: 0,
    timelineTracks: Array.from(new Set(clips.map((clip) => clip.track))),
    timelineMetadata: {},
    audioGain: 0.82,
    assets,
    clips,
    captions: [],
  });
}

function movieProjectFromSurface(surface: SurfaceDescriptor, draft: string): MovieProject {
  const payload = recordValue(surface.payload);
  const naturalText = naturalTextFromPayload(payload, draft);
  const rawProject = structuredProjectFromPayload(payload, draft, ["movie_project", "project"]);
  const attachedAssets = arrayValue(payload.attached_files).map(normalizeAsset);
  if (!Object.keys(rawProject).length) return defaultMovieProject(naturalText, surface, attachedAssets);
  const rawAssets = hasOwn(rawProject, "assets") ? arrayValue(rawProject.assets).map(normalizeAsset) : attachedAssets;
  const fallback = defaultMovieProject(stringValue(rawProject.brief, naturalText), surface, rawAssets);
  const rawTimeline = recordValue(rawProject.timeline ?? payload.tool_timeline);
  const rawClips = arrayValue(rawProject.clips ?? rawTimeline.clips);
  const rawCaptions = arrayValue(rawProject.captions);
  let cursor = 0;
  const hasStructuredClips = hasOwn(rawProject, "clips") || hasOwn(rawTimeline, "clips");
  const clips = (hasStructuredClips ? rawClips : fallback.clips).map((clip, index) => {
    const normalized = normalizeClip(clip, index + 1, cursor);
    cursor = Math.max(cursor, normalized.start + normalized.duration);
    return normalized;
  });
  const captions = (hasOwn(rawProject, "captions") ? rawCaptions : fallback.captions).map(normalizeCaption);
  const computedDuration = Math.max(
    cursor,
    ...captions.map((caption) => caption.start + caption.duration),
    ...rawAssets.map((asset) => asset.start + asset.duration),
  );
  const project: MovieProject = {
    projectId: stringValue(rawProject.project_id ?? rawProject.projectId, surface.resourceId ?? surface.id),
    title: stringValue(rawProject.title, cleanTitle(stringValue(rawProject.brief, naturalText), fallback.title)),
    brief: stringValue(rawProject.brief, naturalText),
    format: stringValue(rawProject.format, fallback.format),
    resolution: stringValue(rawProject.resolution, fallback.resolution),
    fps: numberValue(rawProject.fps ?? rawTimeline.fps, fallback.fps, 1),
    audioGain: numberValue(recordValue(rawProject.audio).voice_gain, fallback.audioGain),
    renderEnabled: false,
    timelineDuration: numberValue(rawTimeline.duration, computedDuration),
    timelineTracks: arrayValue(rawTimeline.tracks).map((track) => stringValue(recordValue(track).id ?? recordValue(track).name ?? track)).filter(Boolean),
    timelineMetadata: rawTimeline,
    assets: rawAssets,
    clips,
    captions,
  };
  return project;
}

function imageProjectFromSurface(surface: SurfaceDescriptor, draft: string): ImageProject {
  const payload = recordValue(surface.payload);
  const naturalText = naturalTextFromPayload(payload, draft);
  const rawProject = structuredProjectFromPayload(payload, draft, ["image_project", "project"]);
  const assets = (hasOwn(rawProject, "assets") ? arrayValue(rawProject.assets) : arrayValue(payload.attached_files)).map(normalizeAsset);
  const rawVariants = arrayValue<Record<string, unknown>>(rawProject.variants);
  return {
    projectId: stringValue(rawProject.project_id ?? rawProject.projectId, surface.resourceId ?? surface.id),
    prompt: stringValue(rawProject.prompt, naturalText),
    mode: stringValue(rawProject.mode, "compose"),
    assets,
    variants: rawVariants.map((variant, index) => ({
        id: stringValue(variant.id, `variant-${index + 1}`),
        label: stringValue(variant.label, `Variant ${index + 1}`),
        status: stringValue(variant.status, "editable"),
        source: mediaSourceFromRecord(variant),
        rawSource: stringValue(variant.source ?? variant.path ?? variant.url ?? variant.data_uri ?? variant.image_data, ""),
        assetId: stringValue(variant.asset_id ?? variant.assetId, ""),
        mimeType: stringValue(variant.mime_type ?? variant.mimeType, ""),
      })),
  };
}

function stableProjectKey(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function slideProjectSyncKey(surface: SurfaceDescriptor, draft: string): string {
  const payload = recordValue(surface.payload);
  const rawProject = structuredProjectFromPayload(payload, draft, ["slide_project", "deck", "project"]);
  if (Object.keys(rawProject).length) {
    return stableProjectKey({
      id: surface.id,
      resourceId: surface.resourceId,
      projectId: rawProject.project_id ?? rawProject.projectId,
      project: rawProject,
    });
  }
  return stableProjectKey({
    id: surface.id,
    resourceId: surface.resourceId,
    draft: stringValue(payload.initial_text, draft),
    attachedFiles: payload.attached_files,
  });
}

function movieProjectSyncKey(surface: SurfaceDescriptor, draft: string): string {
  const payload = recordValue(surface.payload);
  return stableProjectKey({
    id: surface.id,
    resourceId: surface.resourceId,
    project: structuredProjectFromPayload(payload, draft, ["movie_project", "project"]),
    initialText: payload.initial_text,
    attachedFiles: payload.attached_files,
  });
}

function imageProjectSyncKey(surface: SurfaceDescriptor, draft: string): string {
  const payload = recordValue(surface.payload);
  return stableProjectKey({
    id: surface.id,
    resourceId: surface.resourceId,
    project: structuredProjectFromPayload(payload, draft, ["image_project", "project"]),
    initialText: payload.initial_text,
    attachedFiles: payload.attached_files,
  });
}

function slidesFromText(draft: string, assets: SlideAsset[]): Slide[] {
  const lines = draft.split(/\r?\n/);
  const title = cleanTitle(draft, "Untitled deck");
  const specs: { title: string; bullets: string[] }[] = [];
  let current: { title: string; bullets: string[] } | undefined;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const heading = trimmed.startsWith("#") ? trimmed.replace(/^#+\s*/, "").trim() : "";
    if (heading && (/^(slide|section)\s+/i.test(heading) || trimmed.startsWith("##"))) {
      if (current) specs.push(current);
      current = { title: heading, bullets: [] };
      continue;
    }
    if (!current) {
      if (trimmed.startsWith("#")) continue;
      current = { title, bullets: [] };
    }
    const bullet = trimmed.replace(/^[-*#\d. ]+/, "").trim();
    if (bullet) current.bullets.push(bullet);
  }
  if (current) specs.push(current);
  if (!specs.length && draft.trim()) specs.push({ title, bullets: [] });
  return specs.map((slide, index) => ({
    id: `slide-${index + 1}`,
    title: slide.title,
    subtitle: "",
    layout: slide.bullets.length ? "title-and-bullets" : "title",
    bullets: slide.bullets,
    notes: "",
    accent: ["blue", "emerald", "amber", "rose", "violet", "cyan"][index % 6],
    assetIds: assets[index] ? [assets[index].id] : [],
    elements: [],
  }));
}

function defaultSlideProject(draft: string, surface: SurfaceDescriptor, assets: SlideAsset[] = []): SlideProject {
  const title = cleanTitle(draft, "Untitled deck");
  const slides = slidesFromText(draft, assets);
  return {
    projectId: surface.resourceId ?? surface.id,
    title,
    brief: draft,
    themeName: "Rumi clean",
    slides,
    assets,
    statusCards: [
      { label: "Slides", value: String(slides.length), status: "editable" },
      { label: "Assets", value: String(assets.length), status: assets.length ? "linked" : "none" },
      { label: "Export", value: "pptx/json", status: "ready" },
    ],
    exportFormat: "pptx",
    exportFilename: "deck.pptx",
    exportStatus: "ready",
  };
}

function slideProjectFromSurface(surface: SurfaceDescriptor, draft: string): SlideProject {
  const payload = recordValue(surface.payload);
  const naturalText = naturalTextFromPayload(payload, draft);
  const rawProject = structuredProjectFromPayload(payload, draft, ["slide_project", "deck", "project"]);
  const rawAssets = hasOwn(rawProject, "assets") ? arrayValue(rawProject.assets) : arrayValue(payload.attached_files);
  const assets = rawAssets.map(normalizeSlideAsset);
  if (!Object.keys(rawProject).length) return defaultSlideProject(naturalText, surface, assets);
  const fallback = defaultSlideProject(stringValue(rawProject.brief, naturalText), surface, assets);
  const rawSlides = arrayValue(rawProject.slides);
  const fallbackAssetIds = assets.map((asset) => asset.id);
  const slides = hasOwn(rawProject, "slides")
    ? rawSlides.map((slide, index) => normalizeSlide(slide, index + 1, fallbackAssetIds))
    : fallback.slides;
  const rawTheme = recordValue(rawProject.theme);
  const rawExport = recordValue(rawProject.export);
  const statusCards = arrayValue(rawProject.status_cards ?? rawProject.statusCards).map(normalizeStatusCard);
  return {
    projectId: stringValue(rawProject.project_id ?? rawProject.projectId, fallback.projectId),
    title: stringValue(rawProject.title, fallback.title),
    brief: stringValue(rawProject.brief, naturalText),
    themeName: stringValue(rawTheme.name ?? rawProject.theme, fallback.themeName),
    slides,
    assets,
    statusCards: statusCards.length ? statusCards : [
      { label: "Slides", value: String(slides.length), status: "editable" },
      { label: "Assets", value: String(assets.length), status: assets.length ? "linked" : "none" },
      { label: "Export", value: stringValue(rawExport.format, "pptx/json"), status: stringValue(rawExport.status, "ready") },
    ],
    exportFormat: stringValue(rawExport.format, "pptx"),
    exportFilename: stringValue(rawExport.filename ?? rawProject.export_filename, `${surface.id.replace(/[^a-z0-9]+/gi, "-")}.pptx`),
    exportStatus: stringValue(rawExport.status, "ready"),
  };
}

function IconButton({ label, children, active = false, onClick }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-zinc-400 transition",
        active
          ? "border-blue-500/50 bg-blue-500/15 text-blue-100"
          : "border-transparent hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-100",
      )}
    >
      {children}
    </button>
  );
}

function downloadBlob(content: BlobPart, type: string, filename: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.replace(/[^a-z0-9._-]+/gi, "-");
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function safeFilename(value: string, fallback: string, extension: string): string {
  const stem = (value || fallback).replace(/\.[^.]+$/, "").replace(/[^a-z0-9._-]+/gi, "-").replace(/^[.-]+|[.-]+$/g, "") || fallback;
  return `${stem.slice(0, 96)}.${extension}`;
}

function svgMarkupFromSource(source: string): string {
  if (!source.startsWith("data:image/svg+xml;charset=utf-8,")) return "";
  try { return decodeURIComponent(source.slice(source.indexOf(",") + 1)); } catch { return ""; }
}

function embeddedImageSource(source: string): string {
  return sanitizedSvgSource(source)
    || (/^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z0-9+/]+=*$/i.test(source) ? source : "");
}

function imageExportDetails(source: string): { content: string; mimeType: string; extension: string } | null {
  const svgMarkup = svgMarkupFromSource(sanitizedSvgSource(source));
  if (svgMarkup) return { content: svgMarkup, mimeType: "image/svg+xml", extension: "svg" };
  const embedded = embeddedImageSource(source);
  const match = embedded.match(/^data:image\/(png|jpeg|gif|webp|avif);base64,/i);
  if (!match) return null;
  return {
    content: embedded,
    mimeType: `image/${match[1].toLowerCase()}`,
    extension: match[1].toLowerCase() === "jpeg" ? "jpg" : match[1].toLowerCase(),
  };
}

function slideElementCss(element: SlideElement): string {
  const style = element.style;
  const declarations = [`left:${element.x}%`, `top:${element.y}%`, `width:${element.width}%`, `height:${element.height}%`];
  if (style.color) declarations.push(`color:${style.color}`);
  if (style.backgroundColor) declarations.push(`background:${style.backgroundColor}`);
  if (style.fontSize) declarations.push(`font-size:${style.fontSize}`);
  if (style.fontWeight) declarations.push(`font-weight:${style.fontWeight}`);
  if (style.textAlign) declarations.push(`text-align:${style.textAlign}`);
  if (style.objectFit) declarations.push(`object-fit:${style.objectFit}`);
  if (style.borderRadius) declarations.push(`border-radius:${style.borderRadius}`);
  return declarations.join(";");
}

function vttTimestamp(seconds: number): string {
  const milliseconds = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const remainderSeconds = Math.floor((milliseconds % 60_000) / 1000);
  const remainderMilliseconds = milliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainderSeconds).padStart(2, "0")}.${String(remainderMilliseconds).padStart(3, "0")}`;
}

function TextActionButton({ label, children, onClick, disabled = false }: { label: string; children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200 transition hover:border-zinc-700 hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function SurfaceToolbar({
  title,
  mode,
  onClose,
  onToolAction,
  playing = false,
}: {
  title: string;
  mode: ToolbarMode;
  onClose?: () => void;
  onToolAction?: (label: string) => void;
  playing?: boolean;
}) {
  const fire = (label: string) => () => onToolAction?.(label);
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-zinc-800/70 bg-[#111114] px-3">
      <div className="min-w-[92px] max-w-[220px] flex-none truncate text-sm font-medium text-zinc-200">{title}</div>
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        <IconButton label="Sync status" onClick={fire("Sync status")}><Cloud className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Undo" onClick={fire("Undo")}><Undo2 className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Redo" onClick={fire("Redo")}><Redo2 className="h-4 w-4" aria-hidden="true" /></IconButton>
        <div className="mx-1 h-5 w-px shrink-0 bg-zinc-800" />
        {mode === "write" ? (
          <>
            <button
              type="button"
              className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
            >
              Heading 1 <ChevronDown className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
            </button>
            <IconButton label="Bold" onClick={fire("Bold")}><Bold className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Italic" onClick={fire("Italic")}><Italic className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Bulleted list" onClick={fire("Bulleted list")}><List className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        ) : mode === "image" ? (
          <>
            <IconButton label="Generate" active onClick={fire("Generate")}><ImageIcon className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Crop" onClick={fire("Crop")}><Shapes className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Variants" onClick={fire("Variants")}><Layers3 className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Mask" onClick={fire("Mask")}><MousePointer2 className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        ) : mode === "slide" ? (
          <>
            <IconButton label="Select" active onClick={fire("Select")}><MousePointer2 className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Text" onClick={fire("Text")}><Type className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Shapes" onClick={fire("Shapes")}><Shapes className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Image" onClick={fire("Image")}><ImageIcon className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        ) : (
          <>
            <IconButton label="Play" active={playing} onClick={fire("Play")}><Play className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Split" onClick={fire("Split")}><Scissors className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Captions" onClick={fire("Captions")}><Subtitles className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Audio" onClick={fire("Audio")}><Volume2 className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        )}
        <div className="mx-1 h-5 w-px shrink-0 bg-zinc-800" />
        <IconButton label="Print" onClick={fire("Print")}><Printer className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Share" onClick={fire("Share")}><Share2 className="h-4 w-4" aria-hidden="true" /></IconButton>
      </div>
      {onClose ? <IconButton label="Close surface" onClick={onClose}><X className="h-4 w-4" aria-hidden="true" /></IconButton> : null}
    </div>
  );
}

function SendToComposerButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md bg-blue-500 px-3 text-xs font-semibold text-white shadow-sm shadow-blue-950/30 transition hover:bg-blue-400"
    >
      <Send className="h-3.5 w-3.5" aria-hidden="true" />
      Composer
    </button>
  );
}

function WriteSurface({ draft, onDraftChange, onAppendDraftToComposer, onClose }: Omit<WorkspaceSurfacePanelProps, "surface">) {
  const title = cleanTitle(draft, "Untitled document");

  return (
    <div data-surface-kind="write" className="flex h-full min-h-0 flex-col bg-[#0f0f10]">
      <SurfaceToolbar title={title} mode="write" onClose={onClose} />
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto flex min-h-full w-full max-w-[840px] gap-3">
          <main className="min-w-0 flex-1 rounded-lg border border-zinc-700/80 bg-[#1f1f20] shadow-2xl shadow-black/30">
            <div className="flex min-h-[560px] flex-col px-6 py-5 sm:px-8">
              <input
                aria-label="Document title"
                value={title}
                readOnly
                className="w-full bg-transparent text-2xl font-medium leading-tight text-zinc-100 outline-none sm:text-3xl"
              />
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                <span className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-300">Draft</span>
                <span>Local</span>
                <span>Rumi Canvas</span>
              </div>
              <textarea
                aria-label="Document body"
                value={draft}
                onChange={(event) => onDraftChange(event.target.value)}
                spellCheck={false}
                className="mt-5 min-h-[420px] flex-1 resize-none bg-transparent text-[15px] leading-7 text-zinc-200 outline-none placeholder:text-zinc-600"
                placeholder="Start writing..."
              />
            </div>
          </main>
          <aside className="hidden w-12 shrink-0 flex-col items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/90 py-3 shadow-xl shadow-black/20 min-[680px]:flex">
            <IconButton label="Document tools"><SlidersHorizontal className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Blocks"><Layers3 className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Outline"><AlignLeft className="h-4 w-4" aria-hidden="true" /></IconButton>
          </aside>
        </div>
      </div>
      <div className="flex h-12 shrink-0 items-center justify-between border-t border-zinc-800 bg-[#101012] px-3">
        <div className="min-w-0 truncate text-xs text-zinc-500">Words {draft.trim() ? draft.trim().split(/\s+/).length : 0}</div>
        <SendToComposerButton onClick={onAppendDraftToComposer} />
      </div>
    </div>
  );
}

function MediaPreview({
  source,
  kind,
  name,
  className,
  playing = false,
  sourceLabel = "",
  mediaTime,
}: {
  source: string;
  kind: string;
  name: string;
  className?: string;
  playing?: boolean;
  sourceLabel?: string;
  mediaTime?: number;
}) {
  const [failed, setFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  useEffect(() => setFailed(false), [source]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing) {
      void video.play().catch(() => undefined);
    } else {
      video.pause();
    }
  }, [playing, source]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video || mediaTime === undefined || !Number.isFinite(mediaTime)) return;
    if (Math.abs(video.currentTime - mediaTime) > 0.35) video.currentTime = Math.max(0, mediaTime);
  }, [mediaTime, source]);
  if (source && !failed && kind === "video") {
    return <video ref={videoRef} key={source} src={source} aria-label={name} className={cn("h-full w-full object-contain", className)} controls muted autoPlay={playing} playsInline onError={() => setFailed(true)} />;
  }
  if (source && !failed && kind === "image") {
    return <img src={source} alt={name} className={cn("h-full w-full object-contain", className)} onError={() => setFailed(true)} />;
  }
  return (
    <div className={cn("flex h-full w-full items-center justify-center border border-dashed border-zinc-600 bg-zinc-900/70 p-3 text-center", className)}>
      <div>
        <ImageIcon className="mx-auto h-6 w-6 text-zinc-500" aria-hidden="true" />
        <div className="mt-2 text-xs font-medium text-zinc-300">{name || "No renderable output"}</div>
        <div className="mt-1 text-[10px] text-zinc-500">{sourceLabel ? `Source: ${sourceLabel}` : failed ? "Media could not be loaded" : source ? "Source is not browser-renderable" : "No media source provided"}</div>
      </div>
    </div>
  );
}

function SlideCanvas({ slide, project }: { slide?: Slide; project: SlideProject }) {
  const linkedAssets = slide
    ? project.assets.filter((asset) => slide.assetIds.includes(asset.id))
    : [];
  if (slide?.elements.length) {
    return (
      <div className="relative h-full w-full overflow-hidden bg-[#f8fafc] text-zinc-950">
        {slide.elements.map((element) => {
          const asset = project.assets.find((candidate) => candidate.id === element.assetId);
          const elementStyle: CSSProperties = {
            position: "absolute",
            left: `${element.x}%`,
            top: `${element.y}%`,
            width: `${element.width}%`,
            height: `${element.height}%`,
            overflow: "hidden",
            ...element.style,
          };
          if (["image", "video", "asset", "media"].includes(element.type)) {
            return (
              <div key={element.id} style={elementStyle}>
                <MediaPreview
                  source={asset?.source ?? ""}
                  kind={asset?.kind ?? element.type}
                  name={asset?.name ?? element.text ?? "Slide asset"}
                  className="bg-zinc-100"
                  sourceLabel={asset?.rawSource}
                />
              </div>
            );
          }
          if (element.type === "shape") {
            return <div key={element.id} style={elementStyle} aria-label={element.text || "Shape"} />;
          }
          const lines = element.text.split(/\r?\n/).filter(Boolean);
          return (
            <div key={element.id} style={elementStyle} className="whitespace-pre-wrap leading-tight">
              {element.type === "bullets" ? (
                <ul className="list-disc space-y-1 pl-5">{lines.map((line) => <li key={line}>{line.replace(/^[-*]\s*/, "")}</li>)}</ul>
              ) : element.text}
            </div>
          );
        })}
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col justify-between bg-[#f8fafc] p-[6%] text-zinc-950">
      <div className="min-h-0">
        <div className={cn("h-1.5 w-16 rounded-full", slideAccentTone[slide?.accent ?? "blue"] ?? "bg-blue-500")} />
        <h2 className="mt-5 text-[26px] font-semibold leading-tight">{slide?.title ?? project.title}</h2>
        {slide?.subtitle ? <p className="mt-2 max-w-[82%] text-sm leading-5 text-zinc-700">{slide.subtitle}</p> : null}
        {slide?.bullets.length ? (
          <ul className="mt-4 max-w-[82%] space-y-1.5 text-sm leading-5 text-zinc-700">
            {slide.bullets.slice(0, 7).map((bullet) => (
              <li key={bullet} className="flex gap-2">
                <span className={cn("mt-2 h-1.5 w-1.5 shrink-0 rounded-full", slideAccentTone[slide.accent] ?? "bg-blue-500")} />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {linkedAssets.length ? (
        <div className="mt-3 grid min-h-16 grid-cols-3 gap-2">
          {linkedAssets.slice(0, 3).map((asset) => (
            <MediaPreview key={asset.id} source={asset.source} kind={asset.kind} name={asset.name} className="min-h-16 rounded bg-zinc-100" sourceLabel={asset.rawSource} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ImageSurface({ surface, draft, onDraftChange, onAppendDraftToComposer, onClose }: WorkspaceSurfacePanelProps) {
  const projectSyncKey = useMemo(() => imageProjectSyncKey(surface, draft), [surface.id, surface.resourceId, surface.payload, draft]);
  const initialProject = useMemo(() => imageProjectFromSurface(surface, draft), [projectSyncKey]);
  const [project, setProject] = useState(initialProject);
  const [selectedOutputId, setSelectedOutputId] = useState(initialProject.variants[0]?.id ?? initialProject.assets[0]?.id ?? "");
  const [status, setStatus] = useState("Structured image project ready");
  const title = cleanTitle(project.prompt, "Image project");
  const selectedVariant = project.variants.find((variant) => variant.id === selectedOutputId);
  const selectedAsset = project.assets.find((asset) => asset.id === (selectedVariant?.assetId || selectedOutputId));
  const outputSource = selectedVariant?.source || selectedAsset?.source || "";
  const outputKind = mediaKind(outputSource, selectedAsset?.kind, selectedVariant?.mimeType ?? selectedAsset?.mimeType);
  const outputName = selectedVariant?.label ?? selectedAsset?.name ?? "No image output";

  useEffect(() => {
    setProject(initialProject);
    setSelectedOutputId(initialProject.variants[0]?.id ?? initialProject.assets[0]?.id ?? "");
    setStatus("Structured image project ready");
  }, [initialProject]);

  const updatePrompt = (value: string) => {
    onDraftChange(value);
    setProject((current) => ({ ...current, prompt: value }));
  };
  const handleToolAction = (label: string) => {
    if (label === "Generate") {
      setStatus("No image was generated; generation requires an image tool result.");
    } else if (label === "Variants") {
      setStatus(`${project.variants.length} variants available`);
    } else if (label === "Crop" || label === "Mask") {
      setStatus(`${label} mode selected`);
    } else {
      setStatus(`${label} checked`);
    }
  };
  const exportImage = () => {
    const details = imageExportDetails(outputSource);
    if (!details || outputKind !== "image") {
      setStatus("Export unavailable: select sanitized SVG or embedded image data.");
      return;
    }
    const filename = safeFilename(outputName, "image", details.extension);
    downloadBlob(details.content, details.mimeType, filename);
    setStatus(`Export started: ${filename}`);
  };

  return (
    <div data-surface-kind="image" className="flex h-full min-h-0 flex-col bg-[#101012]">
      <SurfaceToolbar title={title} mode="image" onClose={onClose} onToolAction={handleToolAction} />
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] overflow-hidden">
        <div className="grid min-h-0 gap-3 overflow-auto p-3 min-[720px]:grid-cols-[minmax(0,1fr)_180px]">
          <main className="min-w-0 rounded-lg border border-zinc-800 bg-[#141416] p-3">
            <div className="relative aspect-square overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-2xl shadow-black/30">
              <MediaPreview source={outputSource} kind={outputKind} name={outputName} sourceLabel={selectedVariant?.rawSource ?? selectedAsset?.rawSource} />
              <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between bg-black/55 px-3 py-2 text-[11px] text-zinc-300">
                  <span>{project.mode}</span>
                  <span>{outputSource ? "Renderable output" : "No output"}</span>
              </div>
            </div>
          </main>
          <aside className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-950/80 p-3">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-zinc-200">
              <Layers3 className="h-4 w-4 text-zinc-500" aria-hidden="true" />
              Variants
            </div>
            <div className="space-y-2">
              {project.variants.map((variant) => (
                <button key={variant.id} type="button" onClick={() => setSelectedOutputId(variant.id)} aria-label={`Image variant ${variant.id}`} className={cn("w-full rounded-md border bg-zinc-900 px-2 py-2 text-left text-xs text-zinc-200", selectedOutputId === variant.id ? "border-blue-500" : "border-zinc-800")}>
                  <span className="block truncate">{variant.label}</span>
                  <span className="mt-0.5 block text-[10px] text-zinc-500">{variant.status}</span>
                </button>
              ))}
              {project.assets.map((asset) => (
                <button key={asset.id} type="button" onClick={() => setSelectedOutputId(asset.id)} aria-label={`Image asset ${asset.id}`} className={cn("w-full rounded-md border bg-zinc-900 px-2 py-2 text-left text-xs text-zinc-200", selectedOutputId === asset.id ? "border-blue-500" : "border-zinc-800")}>
                  <span className="block truncate">{asset.name}</span>
                  <span className="mt-0.5 block text-[10px] text-zinc-500">{asset.source ? asset.kind : "no output source"}</span>
                </button>
              ))}
              {!project.variants.length && !project.assets.length ? <div className="text-xs leading-5 text-zinc-500">No structured outputs yet.</div> : null}
            </div>
            <div className="mt-4 text-[11px] leading-5 text-zinc-500">{status}</div>
            <div className="mt-2"><TextActionButton label="Export selected image" onClick={exportImage} disabled={!imageExportDetails(outputSource) || outputKind !== "image"}><Share2 className="h-3.5 w-3.5" aria-hidden="true" />Export</TextActionButton></div>
          </aside>
        </div>
        <section className="border-t border-zinc-800 bg-[#101012] p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-medium text-zinc-300">Prompt</div>
            <SendToComposerButton onClick={onAppendDraftToComposer} />
          </div>
          <textarea
            aria-label="Image prompt"
            value={project.prompt}
            onChange={(event) => updatePrompt(event.target.value)}
            spellCheck={false}
            className="h-24 w-full resize-none rounded-md border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
          />
        </section>
      </div>
    </div>
  );
}

function SlideSurface({ surface, draft, onAppendDraftToComposer, onClose }: WorkspaceSurfacePanelProps) {
  const projectSyncKey = useMemo(() => slideProjectSyncKey(surface, draft), [surface.id, surface.resourceId, surface.payload, draft]);
  const initialProject = useMemo(() => slideProjectFromSurface(surface, draft), [projectSyncKey]);
  const [project, setProject] = useState(initialProject);
  const [selectedSlideId, setSelectedSlideId] = useState(initialProject.slides[0]?.id ?? "");
  const [status, setStatus] = useState("Editable deck ready");
  const selectedSlide = project.slides.find((slide) => slide.id === selectedSlideId) ?? project.slides[0];

  useEffect(() => {
    setProject(initialProject);
    setSelectedSlideId(initialProject.slides[0]?.id ?? "");
    setStatus("Editable deck ready");
  }, [initialProject]);

  const handleToolAction = (label: string) => {
    if (label === "Image") {
      setStatus(`${project.assets.length} deck assets linked`);
    } else if (label === "Text" || label === "Shapes" || label === "Select") {
      setStatus(`${label} tool selected`);
    } else {
      setStatus(`${label} checked`);
    }
  };
  const renameSelectedSlide = (title: string) => {
    if (!selectedSlide) return;
    setProject((current) => ({
      ...current,
      slides: current.slides.map((slide) => slide.id === selectedSlide.id ? { ...slide, title } : slide),
    }));
  };
  const updateSelectedNotes = (notes: string) => {
    if (!selectedSlide) return;
    setProject((current) => ({
      ...current,
      slides: current.slides.map((slide) => slide.id === selectedSlide.id ? { ...slide, notes } : slide),
    }));
  };
  const saveDeck = () => {
    downloadBlob(JSON.stringify(project, null, 2), "application/json", safeFilename(project.title, "deck", "rumislides.json"));
    setStatus("Saved editable slide project JSON.");
  };
  const exportDeck = () => {
    const escape = (value: string) => value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character] ?? character));
    const assets = new Map(project.assets.map((asset) => [asset.id, asset]));
    let omitted = 0;
    const sections = project.slides.map((slide) => {
      const elements = slide.elements.length ? slide.elements.map((element) => {
        const style = slideElementCss(element);
        if (["image", "asset"].includes(element.type)) {
          const asset = assets.get(element.assetId);
          const source = embeddedImageSource(asset?.source ?? "");
          if (!source) { omitted += 1; return ""; }
          return `<img style="${style}" src="${escape(source)}" alt="${escape(asset?.name ?? "")}">`;
        }
        if (element.type === "bullets") return `<ul style="${style}">${element.text.split(/\r?\n/).filter(Boolean).map((line) => `<li>${escape(line.replace(/^[-*]\s*/, ""))}</li>`).join("")}</ul>`;
        return `<div style="${style}">${escape(element.text)}</div>`;
      }).join("") : `<h1>${escape(slide.title)}</h1>${slide.subtitle ? `<p>${escape(slide.subtitle)}</p>` : ""}<ul>${slide.bullets.map((bullet) => `<li>${escape(bullet)}</li>`).join("")}</ul>`;
      return `<section class="slide">${elements}</section>`;
    }).join("");
    const projectJson = JSON.stringify(project).replace(/<\//g, "<\\/");
    const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>html,body{margin:0;background:#111;font-family:system-ui,sans-serif}.slide{position:relative;box-sizing:border-box;width:100vw;aspect-ratio:16/9;overflow:hidden;padding:6%;background:#f8fafc;color:#18181b;page-break-after:always}.slide>*{position:absolute}.slide>h1,.slide>p,.slide>ul{position:static}.slide h1{font-size:5vw}.slide p,.slide li{font-size:2.2vw;line-height:1.4}</style></head><body>${sections}<script type="application/json" id="rumi-slide-project">${projectJson}</script></body></html>`;
    downloadBlob(html, "text/html", safeFilename(project.title, "deck", "html"));
    setStatus(omitted ? `Exported HTML deck; omitted ${omitted} non-embedded asset(s).` : "Exported self-contained 16:9 HTML deck.");
  };

  return (
    <div data-surface-kind="slide" className="flex h-full min-h-0 flex-col bg-[#101012]">
      <SurfaceToolbar title={project.title} mode="slide" onClose={onClose} onToolAction={handleToolAction} />
      <div className="grid min-h-0 flex-1 grid-cols-[78px_minmax(0,1fr)] overflow-hidden">
        <aside className="min-h-0 overflow-y-auto border-r border-zinc-800 bg-[#141416] px-2 py-3">
          <div className="mb-2 flex h-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400">
            <Film className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="space-y-2">
            {project.slides.map((slide, index) => (
              <button
                key={slide.id}
                type="button"
                aria-label={`Slide ${index + 1}: ${slide.title}`}
                onClick={() => setSelectedSlideId(slide.id)}
                className={cn(
                  "group w-full rounded-md border p-1 text-left transition",
                  selectedSlide?.id === slide.id ? "border-blue-500/70 bg-blue-500/10" : "border-zinc-800 bg-zinc-950 hover:border-zinc-700",
                )}
              >
                <div className="aspect-video rounded bg-zinc-900 p-1">
                  <div className={cn("h-1.5 w-5 rounded-full", slideAccentTone[slide.accent] ?? "bg-blue-500")} />
                  <div className="mt-2 h-1 w-8 rounded bg-zinc-500/80" />
                  <div className="mt-1 h-1 w-5 rounded bg-zinc-700" />
                  {slide.assetIds.length ? <div className="mt-1 h-1 w-3 rounded bg-zinc-600" /> : null}
                </div>
                <div className="mt-1 truncate text-[10px] text-zinc-500">{index + 1}. {slide.title}</div>
              </button>
            ))}
          </div>
        </aside>
        <main className="min-h-0 overflow-auto bg-[#19191b] p-3">
          <div className="mx-auto flex min-h-full max-w-[760px] flex-col gap-3">
            <div className="rounded-lg border border-zinc-700 bg-[#2b2b2e] p-3 shadow-2xl shadow-black/30">
              <div className="aspect-video overflow-hidden rounded-md border border-zinc-600/80 shadow-inner">
                <SlideCanvas slide={selectedSlide} project={project} />
              </div>
            </div>
            <section className="grid gap-3 min-[680px]:grid-cols-[minmax(0,1fr)_220px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="text-xs font-medium text-zinc-300">Deck status</div>
                  <div className="flex items-center gap-1"><TextActionButton label="Save editable deck" onClick={saveDeck}><Cloud className="h-3.5 w-3.5" />Save</TextActionButton><TextActionButton label="Export HTML deck" onClick={exportDeck}><Share2 className="h-3.5 w-3.5" />Export</TextActionButton><span className="text-[11px] text-zinc-500">{project.themeName}</span></div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {project.statusCards.map((card) => (
                    <div key={`${card.label}-${card.status}`} className="min-w-0 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-2">
                      <div className="truncate text-[10px] uppercase tracking-wide text-zinc-500">{card.label}</div>
                      <div className="mt-1 truncate text-xs font-medium text-zinc-200">{card.value}</div>
                      <div className="mt-0.5 truncate text-[10px] text-zinc-500">{card.status}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 text-xs font-medium text-zinc-300">Assets / export</div>
                <div className="space-y-1.5 text-[11px] text-zinc-500">
                  {project.assets.slice(0, 3).map((asset) => (
                    <div key={asset.id} className="flex min-w-0 items-center justify-between gap-2">
                      <span className="truncate text-zinc-300">{asset.name}</span>
                      <span className="shrink-0">{asset.kind}</span>
                    </div>
                  ))}
                  {!project.assets.length ? <div>No linked assets</div> : null}
                  <div className="border-t border-zinc-800 pt-1.5">{project.exportFormat} / {project.exportFilename} / {project.exportStatus}</div>
                </div>
              </div>
            </section>
            <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-zinc-300">Speaker notes</div>
                <SendToComposerButton onClick={onAppendDraftToComposer} />
              </div>
              <input
                aria-label="Selected slide title"
                value={selectedSlide?.title ?? ""}
                onChange={(event) => renameSelectedSlide(event.target.value)}
                className="mb-2 h-8 w-full rounded-md border border-zinc-800 bg-[#111114] px-3 text-sm text-zinc-200 outline-none focus:border-zinc-600"
              />
              <textarea
                aria-label="Slide notes"
                value={selectedSlide?.notes ?? ""}
                onChange={(event) => updateSelectedNotes(event.target.value)}
                spellCheck={false}
                className="h-28 w-full resize-none rounded-md border border-zinc-800 bg-[#111114] p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
              />
              <div className="mt-2 text-[11px] text-zinc-500">{status}</div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

function MovieSurface({ surface, draft, onDraftChange, onAppendDraftToComposer, onClose }: WorkspaceSurfacePanelProps) {
  const projectSyncKey = useMemo(() => movieProjectSyncKey(surface, draft), [surface.id, surface.resourceId, surface.payload, draft]);
  const initialProject = useMemo(() => movieProjectFromSurface(surface, draft), [projectSyncKey]);
  const [project, setProject] = useState(initialProject);
  const [selectedClipId, setSelectedClipId] = useState(initialProject.clips[0]?.id ?? "");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [status, setStatus] = useState("Editable project ready");
  const frameRef = useRef<number | null>(null);
  const selectedClip = project.clips.find((clip) => clip.id === selectedClipId) ?? project.clips[0];
  const duration = Math.max(
    project.timelineDuration,
    ...project.clips.map((clip) => clip.start + clip.duration),
    ...project.captions.map((caption) => caption.start + caption.duration),
    ...project.assets.map((asset) => asset.start + asset.duration),
  );
  const displayDuration = Math.max(duration, 1);
  const timelineWidth = Math.max(640, displayDuration * 42);
  const clipTracks = Array.from(new Set([
    ...project.timelineTracks.filter((track) => track !== "captions" && track !== "assets"),
    ...project.clips.map((clip) => clip.track),
  ])).filter(Boolean);
  const activeClip = project.clips.find((clip) => currentTime >= clip.start && currentTime < clip.start + clip.duration) ?? selectedClip;
  const activeCaption = project.captions.find((caption) => currentTime >= caption.start && currentTime < caption.start + caption.duration);
  const activeAsset = project.assets.find((asset) => asset.id === activeClip?.assetId);
  const previewSource = activeAsset?.source || activeClip?.source || "";
  const previewKind = mediaKind(previewSource, activeAsset?.kind, activeAsset?.mimeType ?? activeClip?.mimeType);

  useEffect(() => {
    setProject(initialProject);
    setSelectedClipId(initialProject.clips[0]?.id ?? "");
    setIsPlaying(false);
    setCurrentTime(0);
    setStatus("Editable project ready");
  }, [initialProject]);

  useEffect(() => {
    if (!isPlaying || duration <= 0) return undefined;
    let previous = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - previous) / 1000;
      previous = now;
      setCurrentTime((current) => Math.min(duration, current + elapsed));
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [duration, isPlaying]);

  useEffect(() => {
    if (isPlaying && currentTime >= duration) setIsPlaying(false);
  }, [currentTime, duration, isPlaying]);

  useEffect(() => {
    if (isPlaying && activeClip) setSelectedClipId(activeClip.id);
  }, [activeClip?.id, isPlaying]);

  const updateProject = (updater: (current: MovieProject) => MovieProject) => {
    setProject((current) => updater({
      ...current,
      clips: current.clips.map((clip) => ({ ...clip })),
      captions: current.captions.map((caption) => ({ ...caption })),
      assets: current.assets.map((asset) => ({ ...asset })),
    }));
  };
  const updateBrief = (value: string) => {
    onDraftChange(value);
    updateProject((current) => ({ ...current, brief: value, title: cleanTitle(value, current.title) }));
  };
  const importMedia = () => {
    setStatus("No media selected. Import requires an attached file or movie_import_media result.");
  };
  const splitSelectedClip = () => {
    if (!selectedClip || selectedClip.duration <= 0.5) return;
    updateProject((current) => {
      const index = current.clips.findIndex((clip) => clip.id === selectedClip.id);
      if (index < 0) return current;
      const first = { ...current.clips[index], duration: Math.round((current.clips[index].duration / 2) * 100) / 100 };
      first.outPoint = first.inPoint + first.duration;
      const secondDuration = Math.max(0.25, Math.round((current.clips[index].duration - first.duration) * 100) / 100);
      const second = {
        ...current.clips[index],
        id: `${current.clips[index].id}-split`,
        name: `${current.clips[index].name} B`,
        inPoint: first.outPoint,
        start: first.start + first.duration,
        duration: secondDuration,
        outPoint: first.outPoint + secondDuration,
        color: "amber",
      };
      const clips = [...current.clips];
      clips.splice(index, 1, first, second);
      setSelectedClipId(second.id);
      return { ...current, clips };
    });
    setStatus("Split selected clip into two editable timeline clips");
  };
  const addCaption = () => {
    updateProject((current) => ({
      ...current,
      captions: [
        ...current.captions,
        {
          id: `caption-${current.captions.length + 1}`,
          text: `${selectedClip?.name ?? current.title} caption`,
          start: selectedClip?.start ?? 0,
          duration: Math.min(3, selectedClip?.duration ?? 3),
        },
      ],
    }));
    setStatus("Caption cue added at the selected clip");
  };
  const trimSelectedClip = (nextDuration: number) => {
    if (!selectedClip) return;
    updateProject((current) => ({
      ...current,
      clips: current.clips.map((clip) => clip.id === selectedClip.id
        ? { ...clip, duration: Math.max(0.25, nextDuration), outPoint: clip.inPoint + Math.max(0.25, nextDuration) }
        : clip),
    }));
    setStatus("Trim metadata updated");
  };
  const saveProject = () => {
    const payload = JSON.stringify({ ...project, timeline: { ...project.timelineMetadata, duration, tracks: project.timelineTracks } }, null, 2);
    downloadBlob(payload, "application/json", safeFilename(project.projectId, "movie", "rumimovie.json"));
    setStatus(`Saved editable movie project (${project.clips.length} clips).`);
  };
  const exportProject = () => {
    const payload = JSON.stringify({
      ...project,
      timeline: { ...project.timelineMetadata, duration, tracks: project.timelineTracks },
    }, null, 2);
    const stem = project.projectId.replace(/[^a-z0-9]+/gi, "-") || "movie";
    downloadBlob(payload, "application/json", `${stem}.json`);
    const captionsVtt = `WEBVTT\n\n${project.captions.map((caption, index) => `${index + 1}\n${vttTimestamp(caption.start)} --> ${vttTimestamp(caption.start + caption.duration)}\n${caption.text}\n`).join("\n")}`;
    downloadBlob(captionsVtt, "text/vtt", `${stem}-captions.vtt`);
    downloadBlob(project.clips.map((clip) => `${clip.start.toFixed(3)}\t${clip.duration.toFixed(3)}\t${clip.track}\t${clip.name}`).join("\n"), "text/plain", `${stem}-timeline.edl`);
    setStatus(`Exported project JSON, captions, and timeline/EDL for ${duration.toFixed(2)}s.`);
  };
  const renderProject = () => {
    setStatus("No safe local video render route is configured; project export remains available");
  };
  const handleToolAction = (label: string) => {
    if (label === "Play") {
      setIsPlaying((current) => {
        setStatus(current ? "Paused timeline playback" : "Playing local timeline preview");
        if (!current && currentTime >= duration) setCurrentTime(0);
        return !current;
      });
    } else if (label === "Split") {
      splitSelectedClip();
    } else if (label === "Captions") {
      addCaption();
    } else if (label === "Audio") {
      updateProject((current) => ({ ...current, audioGain: current.audioGain >= 1 ? 0.62 : Math.round((current.audioGain + 0.12) * 100) / 100 }));
      setStatus("Audio gain adjusted");
    } else {
      setStatus(`${label} checked`);
    }
  };
  const renameSelectedClip = (name: string) => {
    if (!selectedClip) return;
    updateProject((current) => ({ ...current, clips: current.clips.map((clip) => clip.id === selectedClip.id ? { ...clip, name } : clip) }));
  };
  const seek = (time: number, clipId?: string) => {
    setCurrentTime(Math.min(duration, Math.max(0, time)));
    if (clipId) setSelectedClipId(clipId);
  };
  const seekFromPointer = (event: ReactMouseEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    seek(((event.clientX - bounds.left) / bounds.width) * duration);
  };

  return (
    <div data-surface-kind="movie" className="flex h-full min-h-0 flex-col bg-[#0f1012]">
      <SurfaceToolbar title={project.title} mode="movie" onClose={onClose} onToolAction={handleToolAction} playing={isPlaying} />
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto flex min-h-full max-w-[820px] flex-col gap-3">
          <section className="grid gap-3 min-[620px]:grid-cols-[minmax(0,1fr)_190px]">
            <div className="rounded-lg border border-zinc-800 bg-black p-2 shadow-2xl shadow-black/30">
              <div className="relative aspect-video overflow-hidden rounded-md border border-zinc-800 bg-zinc-950">
                <MediaPreview
                  source={previewSource}
                  kind={previewKind}
                  name={activeClip?.name ?? project.title}
                  playing={isPlaying}
                  sourceLabel={activeAsset?.rawSource ?? activeClip?.rawSource}
                  mediaTime={activeClip ? currentTime - activeClip.start + activeClip.inPoint : currentTime}
                />
                <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-4">
                  <div className="flex items-center justify-between text-[11px] text-zinc-300 drop-shadow">
                    <span>{currentTime.toFixed(2)}s / {duration.toFixed(2)}s</span>
                    <span>{project.resolution}</span>
                  </div>
                  <button
                    type="button"
                    aria-label="Toggle preview"
                    onClick={() => handleToolAction("Play")}
                    className="pointer-events-auto mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-white/20 bg-black/45 text-white transition hover:bg-black/65"
                  >
                    <Play className="ml-0.5 h-6 w-6" aria-hidden="true" />
                  </button>
                  <div className="rounded border border-white/10 bg-black/45 px-3 py-2">
                    <div className="truncate text-sm font-medium text-white">{activeClip?.name ?? project.title}</div>
                    <div className="mt-1 truncate text-xs text-zinc-300">{activeCaption?.text ?? ""}</div>
                  </div>
                </div>
              </div>
            </div>
            <aside className="rounded-lg border border-zinc-800 bg-zinc-950/80 p-3">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-zinc-200">
                <PanelRight className="h-4 w-4 text-zinc-500" aria-hidden="true" />
                Inspector
              </div>
              <div className="space-y-3 text-xs text-zinc-500">
                <label className="block">
                  <span className="mb-1 block text-zinc-400">Clip name</span>
                  <input
                    aria-label="Selected clip name"
                    value={selectedClip?.name ?? ""}
                    onChange={(event) => renameSelectedClip(event.target.value)}
                    className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 text-zinc-200 outline-none focus:border-zinc-600"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-zinc-400">Duration</span>
                  <input
                    aria-label="Selected clip duration"
                    type="number"
                    min="0.25"
                    step="0.25"
                    value={selectedClip?.duration ?? 0}
                    onChange={(event) => trimSelectedClip(Number(event.target.value))}
                    className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 text-zinc-200 outline-none focus:border-zinc-600"
                  />
                </label>
                <div>
                  <div className="mb-1 flex items-center justify-between text-zinc-400">
                    <span>Voice</span>
                    <span>{Math.round(project.audioGain * 100)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-zinc-800">
                    <div className="h-full rounded-full bg-emerald-400" style={{ width: `${Math.min(100, project.audioGain * 100)}%` }} />
                  </div>
                </div>
              </div>
            </aside>
          </section>

          <section className="rounded-lg border border-zinc-800 bg-[#141416]">
            <div className="flex h-9 items-center justify-between border-b border-zinc-800 px-3">
              <div className="flex items-center gap-2 text-xs font-medium text-zinc-300">
                <MonitorPlay className="h-4 w-4 text-zinc-500" aria-hidden="true" />
                Timeline
                <span className="font-normal text-zinc-500">{duration.toFixed(2)}s · {project.fps} fps</span>
              </div>
              <div className="flex items-center gap-1">
                <TextActionButton label="Import media" onClick={importMedia}><ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />Import</TextActionButton>
                <TextActionButton label="Save project" onClick={saveProject}><Cloud className="h-3.5 w-3.5" aria-hidden="true" />Save</TextActionButton>
                <TextActionButton label="Export project" onClick={exportProject}><Share2 className="h-3.5 w-3.5" aria-hidden="true" />Export</TextActionButton>
                <TextActionButton label="Render movie" onClick={renderProject} disabled={!project.renderEnabled}><MonitorPlay className="h-3.5 w-3.5" aria-hidden="true" />Render</TextActionButton>
              </div>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[760px] p-3">
                <div className="mb-2 grid grid-cols-[72px_1fr] text-[10px] text-zinc-500">
                  <div />
                  <div className="relative h-4 cursor-pointer" style={{ width: `${timelineWidth}px` }} onClick={seekFromPointer}>
                    {[0, 0.25, 0.5, 0.75, 1].map((mark) => (
                      <span
                        key={mark}
                        className="absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
                        style={{ left: `${mark * 100}%` }}
                      >
                        {(duration * mark).toFixed(duration < 10 ? 2 : 1)}s
                      </span>
                    ))}
                    <span className="absolute inset-y-0 rumi-layer-local-popover w-px bg-red-400" style={{ left: `${(currentTime / displayDuration) * 100}%` }} />
                  </div>
                </div>
                <div className="space-y-2">
                  {clipTracks.map((track) => (
                    <TimelineRow key={track} label={track} icon={track === "audio" ? <Volume2 className="h-3.5 w-3.5" aria-hidden="true" /> : <Video className="h-3.5 w-3.5" aria-hidden="true" />}>
                      <div className="relative h-12 cursor-pointer" style={{ width: `${timelineWidth}px` }} onClick={seekFromPointer}>
                        <span className="pointer-events-none absolute inset-y-0 rumi-layer-local-popover w-px bg-red-400" style={{ left: `${(currentTime / displayDuration) * 100}%` }} />
                        {project.clips.filter((clip) => clip.track === track).map((clip) => (
                        <button
                          key={clip.id}
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            seek(clip.start, clip.id);
                          }}
                          style={{
                            left: `${(clip.start / displayDuration) * 100}%`,
                            width: `${Math.max(36, (clip.duration / displayDuration) * timelineWidth)}px`,
                          }}
                          className={cn(
                            "absolute top-0 h-12 min-w-[36px] rounded-md px-2 py-1 text-left text-xs font-medium text-zinc-950 ring-offset-2 ring-offset-zinc-950 transition",
                            clipTone[clip.color] ?? "bg-sky-500",
                            selectedClip?.id === clip.id && "ring-2 ring-white",
                          )}
                        >
                          <span className="block truncate">{clip.name}</span>
                          <span className="block text-[10px] opacity-70">{clip.start.toFixed(2)}–{(clip.start + clip.duration).toFixed(2)}s</span>
                        </button>
                        ))}
                      </div>
                    </TimelineRow>
                  ))}
                  <TimelineRow label="Assets" icon={<ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="relative h-9 cursor-pointer" style={{ width: `${timelineWidth}px` }} onClick={seekFromPointer}>
                      <span className="pointer-events-none absolute inset-y-0 rumi-layer-local-popover w-px bg-red-400" style={{ left: `${(currentTime / displayDuration) * 100}%` }} />
                      {project.assets.map((asset) => (
                        <div
                          key={asset.id}
                          className="absolute top-0 h-9 min-w-[42px] rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 text-[10px] text-cyan-100"
                          style={{ left: `${(asset.start / displayDuration) * 100}%`, width: `${Math.max(42, (asset.duration / displayDuration) * timelineWidth)}px` }}
                          title={`${asset.name} · ${asset.kind} · ${asset.start.toFixed(2)}–${(asset.start + asset.duration).toFixed(2)}s`}
                        >
                          <span className="block truncate">{asset.name}</span>
                          <span className="block truncate opacity-70">{asset.kind}</span>
                        </div>
                      ))}
                    </div>
                  </TimelineRow>
                  <TimelineRow label="Captions" icon={<Subtitles className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="relative h-8 cursor-pointer" style={{ width: `${timelineWidth}px` }} onClick={seekFromPointer}>
                      <span className="pointer-events-none absolute inset-y-0 rumi-layer-local-popover w-px bg-red-400" style={{ left: `${(currentTime / displayDuration) * 100}%` }} />
                      {project.captions.map((caption) => (
                        <button
                          key={caption.id}
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            seek(caption.start);
                          }}
                          className="absolute top-0 h-8 min-w-[42px] rounded-md border border-amber-300/40 bg-amber-300/15 px-2 py-1 text-left text-xs text-amber-100"
                          style={{ left: `${(caption.start / displayDuration) * 100}%`, width: `${Math.max(42, (caption.duration / displayDuration) * timelineWidth)}px` }}
                          title={`${caption.text} · ${caption.start.toFixed(2)}–${(caption.start + caption.duration).toFixed(2)}s`}
                        >
                          <span className="block truncate">{caption.text}</span>
                        </button>
                      ))}
                    </div>
                  </TimelineRow>
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-3 min-[700px]:grid-cols-[minmax(0,1fr)_220px]">
            <textarea
              aria-label="Movie brief"
              value={project.brief}
              onChange={(event) => updateBrief(event.target.value)}
              spellCheck={false}
              className="h-24 shrink-0 resize-none rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
            />
            <div className="flex min-h-24 flex-col justify-between rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <div className="text-xs leading-5 text-zinc-400">{status}</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-[11px] text-zinc-500">{project.clips.length} clips / {project.captions.length} captions</div>
                <SendToComposerButton onClick={onAppendDraftToComposer} />
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function TimelineRow({
  label,
  icon,
  children,
}: {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-2">
      <div className="flex h-full items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-[11px] text-zinc-400">
        {icon}
        {label}
      </div>
      <div className="rounded-md border border-zinc-800 bg-zinc-950/80 p-1">{children}</div>
    </div>
  );
}

function GenericDraftSurface({ draft, onDraftChange, onAppendDraftToComposer }: Omit<WorkspaceSurfacePanelProps, "surface">) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3">
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        className="min-h-0 flex-1 resize-none rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-zinc-600"
        spellCheck={false}
      />
      <div className="flex justify-end">
        <SendToComposerButton onClick={onAppendDraftToComposer} />
      </div>
    </div>
  );
}

export function WorkspaceSurfacePanel(props: WorkspaceSurfacePanelProps) {
  if (props.surface.kind === "write") return <WriteSurface {...props} />;
  if (props.surface.kind === "image") return <ImageSurface {...props} />;
  if (props.surface.kind === "slide") return <SlideSurface {...props} />;
  if (props.surface.kind === "movie") return <MovieSurface {...props} />;
  return <GenericDraftSurface {...props} />;
}
