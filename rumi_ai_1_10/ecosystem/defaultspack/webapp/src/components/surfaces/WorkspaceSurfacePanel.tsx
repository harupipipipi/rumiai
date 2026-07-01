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
import { useMemo, useState, type ReactNode } from "react";

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
  track: "video" | "audio";
  start: number;
  duration: number;
  inPoint: number;
  outPoint: number;
  color: string;
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
};

type ImageProject = {
  projectId: string;
  prompt: string;
  mode: string;
  assets: MovieAsset[];
  variants: { id: string; label: string; status: string }[];
};

const slideThumbs = [
  { id: "1", title: "Title", tone: "bg-blue-500" },
  { id: "2", title: "Agenda", tone: "bg-emerald-400" },
  { id: "3", title: "Close", tone: "bg-amber-300" },
];

const clipTone: Record<string, string> = {
  sky: "bg-sky-500",
  violet: "bg-violet-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-300",
  rose: "bg-rose-400",
  cyan: "bg-cyan-400",
};

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayValue<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function stringValue(value: unknown, fallback = ""): string {
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

function bodyPreview(text: string, fallback: string): string {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.replace(/^[-*#]\s*/, "").trim())
    .filter(Boolean);
  return (lines[1] ?? lines[0] ?? fallback).slice(0, 120);
}

function normalizeClip(raw: unknown, index: number, fallbackStart: number): MovieClip {
  const item = recordValue(raw);
  const inPoint = numberValue(item.in, 0);
  const duration = numberValue(item.duration, numberValue(item.out, inPoint + 4) - inPoint, 0.25);
  return {
    id: stringValue(item.id, `clip-${index}`),
    name: stringValue(item.name ?? item.label, `Clip ${index}`),
    assetId: stringValue(item.asset_id ?? item.assetId, `asset-${index}`),
    track: stringValue(item.track, "video") === "audio" ? "audio" : "video",
    start: numberValue(item.start, fallbackStart),
    duration,
    inPoint,
    outPoint: numberValue(item.out, inPoint + duration, inPoint + 0.25),
    color: stringValue(item.color, ["sky", "violet", "emerald", "amber"][index % 4]),
  };
}

function normalizeCaption(raw: unknown, index: number): MovieCaption {
  const item = recordValue(raw);
  return {
    id: stringValue(item.id, `caption-${index}`),
    text: stringValue(item.text, "Caption line"),
    start: numberValue(item.start, (index - 1) * 4),
    duration: numberValue(item.duration, 3, 0.25),
  };
}

function normalizeAsset(raw: unknown, index: number): MovieAsset {
  const item = recordValue(raw);
  return {
    id: stringValue(item.id, `asset-${index}`),
    name: stringValue(item.name, `Asset ${index}`),
    kind: stringValue(item.kind, "video"),
    duration: numberValue(item.duration, 4, 0.25),
  };
}

function resequenceMovieProject(project: MovieProject): MovieProject {
  let cursor = 0;
  const clips = project.clips.map((clip) => {
    const next = { ...clip, start: cursor };
    cursor = Math.round((cursor + clip.duration) * 100) / 100;
    return next;
  });
  return { ...project, clips };
}

function defaultMovieProject(draft: string): MovieProject {
  const title = cleanTitle(draft, "Untitled movie");
  return resequenceMovieProject({
    projectId: "movie:scratch",
    title,
    brief: draft,
    format: "16:9 / H.264",
    resolution: "1920x1080",
    fps: 30,
    renderEnabled: false,
    audioGain: 0.82,
    assets: [
      { id: "asset-1", name: "Opening card", kind: "video", duration: 4 },
      { id: "asset-2", name: "Product demo", kind: "video", duration: 6 },
      { id: "asset-3", name: "End slate", kind: "video", duration: 3 },
    ],
    clips: [
      { id: "clip-1", name: title, assetId: "asset-1", track: "video", start: 0, duration: 4, inPoint: 0, outPoint: 4, color: "sky" },
      { id: "clip-2", name: "Demo", assetId: "asset-2", track: "video", start: 4, duration: 6, inPoint: 0, outPoint: 6, color: "violet" },
      { id: "clip-3", name: "Call to action", assetId: "asset-3", track: "video", start: 10, duration: 3, inPoint: 0, outPoint: 3, color: "emerald" },
    ],
    captions: [
      { id: "caption-1", text: title, start: 0.4, duration: 3.2 },
      { id: "caption-2", text: "Show the product benefit clearly.", start: 5, duration: 3.6 },
    ],
  });
}

function movieProjectFromSurface(surface: SurfaceDescriptor, draft: string): MovieProject {
  const payload = recordValue(surface.payload);
  const rawProject = recordValue(payload.movie_project ?? payload.project);
  if (!Object.keys(rawProject).length) return defaultMovieProject(draft);
  const fallback = defaultMovieProject(stringValue(rawProject.brief, draft));
  const rawClips = arrayValue(rawProject.clips);
  const rawAssets = arrayValue(rawProject.assets);
  const rawCaptions = arrayValue(rawProject.captions);
  const project: MovieProject = {
    projectId: stringValue(rawProject.project_id ?? rawProject.projectId, surface.resourceId ?? surface.id),
    title: stringValue(rawProject.title, cleanTitle(draft, fallback.title)),
    brief: stringValue(rawProject.brief, draft),
    format: stringValue(rawProject.format, fallback.format),
    resolution: stringValue(rawProject.resolution, fallback.resolution),
    fps: numberValue(rawProject.fps, fallback.fps, 1),
    audioGain: numberValue(recordValue(rawProject.audio).voice_gain, fallback.audioGain),
    renderEnabled: recordValue(rawProject.render).enabled === true,
    assets: rawAssets.length ? rawAssets.map(normalizeAsset) : fallback.assets,
    clips: rawClips.length ? rawClips.map((clip, index) => normalizeClip(clip, index + 1, index * 4)) : fallback.clips,
    captions: rawCaptions.length ? rawCaptions.map(normalizeCaption) : fallback.captions,
  };
  return resequenceMovieProject(project);
}

function imageProjectFromSurface(surface: SurfaceDescriptor, draft: string): ImageProject {
  const payload = recordValue(surface.payload);
  const rawProject = recordValue(payload.image_project ?? payload.project);
  const assets = arrayValue(rawProject.assets ?? payload.attached_files).map(normalizeAsset);
  const rawVariants = arrayValue<Record<string, unknown>>(rawProject.variants);
  return {
    projectId: stringValue(rawProject.project_id ?? rawProject.projectId, surface.resourceId ?? surface.id),
    prompt: stringValue(rawProject.prompt ?? payload.initial_text, draft),
    mode: stringValue(rawProject.mode, "compose"),
    assets,
    variants: rawVariants.length
      ? rawVariants.map((variant, index) => ({
        id: stringValue(variant.id, `variant-${index + 1}`),
        label: stringValue(variant.label, `Variant ${index + 1}`),
        status: stringValue(variant.status, "editable"),
      }))
      : [
        { id: "variant-1", label: "Draft", status: "editable" },
        { id: "variant-2", label: "Mask", status: "ready" },
      ],
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

function TextActionButton({ label, children, onClick }: { label: string; children: ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200 transition hover:border-zinc-700 hover:bg-zinc-900"
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

function ImageSurface({ surface, draft, onDraftChange, onAppendDraftToComposer, onClose }: WorkspaceSurfacePanelProps) {
  const initialProject = useMemo(() => imageProjectFromSurface(surface, draft), [surface.id]);
  const [project, setProject] = useState(initialProject);
  const [status, setStatus] = useState("Ready");
  const title = cleanTitle(project.prompt, "Image project");

  const updatePrompt = (value: string) => {
    onDraftChange(value);
    setProject((current) => ({ ...current, prompt: value }));
  };
  const handleToolAction = (label: string) => {
    if (label === "Generate") {
      setProject((current) => ({
        ...current,
        variants: [...current.variants, { id: `variant-${current.variants.length + 1}`, label: `Variant ${current.variants.length + 1}`, status: "generated" }],
      }));
      setStatus("Generated a local editable variant");
    } else if (label === "Variants") {
      setStatus(`${project.variants.length} variants available`);
    } else if (label === "Crop" || label === "Mask") {
      setStatus(`${label} mode selected`);
    } else {
      setStatus(`${label} checked`);
    }
  };

  return (
    <div data-surface-kind="image" className="flex h-full min-h-0 flex-col bg-[#101012]">
      <SurfaceToolbar title={title} mode="image" onClose={onClose} onToolAction={handleToolAction} />
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] overflow-hidden">
        <div className="grid min-h-0 gap-3 overflow-auto p-3 min-[720px]:grid-cols-[minmax(0,1fr)_180px]">
          <main className="min-w-0 rounded-lg border border-zinc-800 bg-[#141416] p-3">
            <div className="aspect-square rounded-lg border border-zinc-700 bg-[radial-gradient(circle_at_32%_24%,rgba(59,130,246,0.55),transparent_28%),linear-gradient(135deg,#111827,#020617_58%,#172554)] p-4 shadow-2xl shadow-black/30">
              <div className="flex h-full flex-col justify-between">
                <div className="flex items-center justify-between text-[11px] text-blue-100/80">
                  <span>{project.mode}</span>
                  <span>1024 x 1024</span>
                </div>
                <div className="rounded-md border border-white/15 bg-black/35 px-3 py-2 text-sm font-medium leading-5 text-white">
                  {title}
                </div>
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
                <button key={variant.id} type="button" aria-label={`Image variant ${variant.id}`} className="w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 py-2 text-left text-xs text-zinc-200">
                  <span className="block truncate">{variant.label}</span>
                  <span className="mt-0.5 block text-[10px] text-zinc-500">{variant.status}</span>
                </button>
              ))}
            </div>
            <div className="mt-4 text-[11px] leading-5 text-zinc-500">{status}</div>
          </aside>
        </div>
        <section className="border-t border-zinc-800 bg-[#101012] p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-medium text-zinc-300">Prompt</div>
            <SendToComposerButton onClick={onAppendDraftToComposer} />
          </div>
          <textarea
            aria-label="Image prompt"
            value={draft}
            onChange={(event) => updatePrompt(event.target.value)}
            spellCheck={false}
            className="h-24 w-full resize-none rounded-md border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
          />
        </section>
      </div>
    </div>
  );
}

function SlideSurface({ draft, onDraftChange, onAppendDraftToComposer, onClose }: Omit<WorkspaceSurfacePanelProps, "surface">) {
  const title = cleanTitle(draft, "Untitled deck");
  const summary = bodyPreview(draft, "A focused opening slide for the current conversation.");

  return (
    <div data-surface-kind="slide" className="flex h-full min-h-0 flex-col bg-[#101012]">
      <SurfaceToolbar title={title} mode="slide" onClose={onClose} />
      <div className="grid min-h-0 flex-1 grid-cols-[68px_minmax(0,1fr)] overflow-hidden">
        <aside className="min-h-0 overflow-y-auto border-r border-zinc-800 bg-[#141416] px-2 py-3">
          <div className="mb-2 flex h-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400">
            <Film className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="space-y-2">
            {slideThumbs.map((slide, index) => (
              <button
                key={slide.id}
                type="button"
                className={cn(
                  "group w-full rounded-md border p-1 text-left transition",
                  index === 0 ? "border-blue-500/70 bg-blue-500/10" : "border-zinc-800 bg-zinc-950 hover:border-zinc-700",
                )}
              >
                <div className="aspect-video rounded bg-zinc-900 p-1">
                  <div className={cn("h-1.5 w-5 rounded-full", slide.tone)} />
                  <div className="mt-2 h-1 w-8 rounded bg-zinc-500/80" />
                  <div className="mt-1 h-1 w-5 rounded bg-zinc-700" />
                </div>
                <div className="mt-1 truncate text-[10px] text-zinc-500">{slide.id}. {slide.title}</div>
              </button>
            ))}
          </div>
        </aside>
        <main className="min-h-0 overflow-auto bg-[#19191b] p-3">
          <div className="mx-auto flex min-h-full max-w-[760px] flex-col gap-3">
            <div className="rounded-lg border border-zinc-700 bg-[#2b2b2e] p-3 shadow-2xl shadow-black/30">
              <div className="aspect-video rounded-md border border-zinc-600/80 bg-[#f8fafc] p-[6%] text-zinc-950 shadow-inner">
                <div className="flex h-full flex-col justify-between">
                  <div>
                    <div className="h-1.5 w-16 rounded-full bg-blue-500" />
                    <h2 className="mt-5 text-[26px] font-semibold leading-tight text-zinc-950">{title}</h2>
                    <p className="mt-3 max-w-[78%] text-sm leading-5 text-zinc-700">{summary}</p>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="h-10 rounded bg-blue-100" />
                    <div className="h-10 rounded bg-emerald-100" />
                    <div className="h-10 rounded bg-amber-100" />
                  </div>
                </div>
              </div>
            </div>
            <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-zinc-300">Speaker notes</div>
                <SendToComposerButton onClick={onAppendDraftToComposer} />
              </div>
              <textarea
                aria-label="Slide notes"
                value={draft}
                onChange={(event) => onDraftChange(event.target.value)}
                spellCheck={false}
                className="h-28 w-full resize-none rounded-md border border-zinc-800 bg-[#111114] p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
              />
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

function MovieSurface({ surface, draft, onDraftChange, onAppendDraftToComposer, onClose }: WorkspaceSurfacePanelProps) {
  const initialProject = useMemo(() => movieProjectFromSurface(surface, draft), [surface.id]);
  const [project, setProject] = useState(initialProject);
  const [selectedClipId, setSelectedClipId] = useState(initialProject.clips[0]?.id ?? "");
  const [isPlaying, setIsPlaying] = useState(false);
  const [status, setStatus] = useState("Editable project ready");
  const selectedClip = project.clips.find((clip) => clip.id === selectedClipId) ?? project.clips[0];
  const duration = project.clips.reduce((sum, clip) => sum + clip.duration, 0);
  const activeCaption = project.captions.find((caption) => selectedClip && caption.start >= selectedClip.start && caption.start <= selectedClip.start + selectedClip.duration) ?? project.captions[0];

  const updateProject = (updater: (current: MovieProject) => MovieProject) => {
    setProject((current) => resequenceMovieProject(updater({
      ...current,
      clips: current.clips.map((clip) => ({ ...clip })),
      captions: current.captions.map((caption) => ({ ...caption })),
      assets: current.assets.map((asset) => ({ ...asset })),
    })));
  };
  const updateBrief = (value: string) => {
    onDraftChange(value);
    updateProject((current) => ({ ...current, brief: value, title: cleanTitle(value, current.title) }));
  };
  const importMedia = () => {
    updateProject((current) => {
      const index = current.assets.length + 1;
      const asset = { id: `asset-${index}`, name: `Imported media ${index}`, kind: "video", duration: 4 };
      return {
        ...current,
        assets: [...current.assets, asset],
        clips: [...current.clips, { id: `clip-${current.clips.length + 1}`, name: asset.name, assetId: asset.id, track: "video", start: duration, duration: asset.duration, inPoint: 0, outPoint: asset.duration, color: "cyan" }],
      };
    });
    setStatus("Imported media and appended it to the timeline");
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
    setStatus(`Saved local project JSON with ${project.clips.length} clips`);
  };
  const exportProject = () => {
    setStatus(`Exported project JSON and timeline EDL (${Math.round(duration)}s)`);
  };
  const renderProject = () => {
    setStatus(project.renderEnabled ? "Render plan ready for ffmpeg" : "ffmpeg render disabled; export is still available");
  };
  const handleToolAction = (label: string) => {
    if (label === "Play") {
      setIsPlaying((current) => {
        setStatus(current ? "Paused timeline playback" : "Playing local timeline preview");
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

  return (
    <div data-surface-kind="movie" className="flex h-full min-h-0 flex-col bg-[#0f1012]">
      <SurfaceToolbar title={project.title} mode="movie" onClose={onClose} onToolAction={handleToolAction} playing={isPlaying} />
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto flex min-h-full max-w-[820px] flex-col gap-3">
          <section className="grid gap-3 min-[620px]:grid-cols-[minmax(0,1fr)_190px]">
            <div className="rounded-lg border border-zinc-800 bg-black p-2 shadow-2xl shadow-black/30">
              <div className="aspect-video rounded-md border border-zinc-800 bg-gradient-to-br from-zinc-900 via-zinc-950 to-black p-4">
                <div className="flex h-full flex-col justify-between">
                  <div className="flex items-center justify-between text-[11px] text-zinc-500">
                    <span>{selectedClip ? `${selectedClip.start.toFixed(2)}s` : "00:00"}</span>
                    <span>{project.resolution}</span>
                  </div>
                  <button
                    type="button"
                    aria-label="Toggle preview"
                    onClick={() => handleToolAction("Play")}
                    className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white transition hover:bg-white/20"
                  >
                    <Play className="ml-0.5 h-6 w-6" aria-hidden="true" />
                  </button>
                  <div className="rounded border border-white/10 bg-black/45 px-3 py-2">
                    <div className="truncate text-sm font-medium text-white">{selectedClip?.name ?? project.title}</div>
                    <div className="mt-1 truncate text-xs text-zinc-400">{activeCaption?.text ?? "No caption selected"}</div>
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
              </div>
              <div className="flex items-center gap-1">
                <TextActionButton label="Import media" onClick={importMedia}><ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />Import</TextActionButton>
                <TextActionButton label="Save project" onClick={saveProject}><Cloud className="h-3.5 w-3.5" aria-hidden="true" />Save</TextActionButton>
                <TextActionButton label="Export project" onClick={exportProject}><Share2 className="h-3.5 w-3.5" aria-hidden="true" />Export</TextActionButton>
                <TextActionButton label="Render movie" onClick={renderProject}><MonitorPlay className="h-3.5 w-3.5" aria-hidden="true" />Render</TextActionButton>
              </div>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[560px] p-3">
                <div className="mb-2 grid grid-cols-[72px_1fr] text-[10px] text-zinc-500">
                  <div />
                  <div className="grid grid-cols-5">
                    {[0, 0.25, 0.5, 0.75, 1].map((mark) => <span key={mark}>{Math.round(duration * mark)}s</span>)}
                  </div>
                </div>
                <div className="space-y-2">
                  <TimelineRow label="Video" icon={<Video className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex gap-1">
                      {project.clips.filter((clip) => clip.track === "video").map((clip) => (
                        <button
                          key={clip.id}
                          type="button"
                          onClick={() => setSelectedClipId(clip.id)}
                          className={cn(
                            "h-12 min-w-[64px] rounded-md px-2 py-1 text-left text-xs font-medium text-zinc-950 ring-offset-2 ring-offset-zinc-950 transition",
                            clipTone[clip.color] ?? "bg-sky-500",
                            selectedClip?.id === clip.id && "ring-2 ring-white",
                          )}
                          style={{ width: `${Math.max(72, clip.duration * 26)}px` }}
                        >
                          <span className="block truncate">{clip.name}</span>
                          <span className="block text-[10px] opacity-70">{clip.duration.toFixed(2)}s</span>
                        </button>
                      ))}
                    </div>
                  </TimelineRow>
                  <TimelineRow label="Audio" icon={<Volume2 className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex h-9 items-end gap-1 rounded-md bg-emerald-500/20 px-2 py-1">
                      {Array.from({ length: 32 }, (_, index) => (
                        <span
                          key={index}
                          className="w-1 rounded-full bg-emerald-300"
                          style={{ height: `${8 + ((index + project.clips.length) % 5) * 5}px` }}
                        />
                      ))}
                    </div>
                  </TimelineRow>
                  <TimelineRow label="Captions" icon={<Subtitles className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex gap-1">
                      {project.captions.map((caption) => (
                        <button
                          key={caption.id}
                          type="button"
                          className="h-8 min-w-[112px] rounded-md border border-amber-300/40 bg-amber-300/15 px-2 py-1 text-left text-xs text-amber-100"
                          style={{ width: `${Math.max(112, caption.duration * 42)}px` }}
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
              value={draft}
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
