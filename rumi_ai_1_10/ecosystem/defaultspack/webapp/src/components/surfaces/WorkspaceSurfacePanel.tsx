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
import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import type { SurfaceDescriptor } from "../../lib/api";

type WorkspaceSurfacePanelProps = {
  surface: SurfaceDescriptor;
  draft: string;
  onDraftChange: (value: string) => void;
  onAppendDraftToComposer: () => void;
  onClose?: () => void;
};

type IconButtonProps = {
  label: string;
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
};

const slideThumbs = [
  { id: "1", title: "Title", tone: "bg-blue-500" },
  { id: "2", title: "Agenda", tone: "bg-emerald-400" },
  { id: "3", title: "Close", tone: "bg-amber-300" },
];

const movieClips = [
  { label: "Intro", color: "bg-sky-500", width: "w-[118px]" },
  { label: "Demo", color: "bg-violet-400", width: "w-[158px]" },
  { label: "End", color: "bg-emerald-400", width: "w-[92px]" },
];

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

function SurfaceToolbar({
  title,
  mode,
  onClose,
}: {
  title: string;
  mode: "write" | "slide" | "movie";
  onClose?: () => void;
}) {
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-zinc-800/70 bg-[#111114] px-3">
      <div className="min-w-[92px] max-w-[220px] flex-none truncate text-sm font-medium text-zinc-200">{title}</div>
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        <IconButton label="Sync status"><Cloud className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Undo"><Undo2 className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Redo"><Redo2 className="h-4 w-4" aria-hidden="true" /></IconButton>
        <div className="mx-1 h-5 w-px shrink-0 bg-zinc-800" />
        {mode === "write" ? (
          <>
            <button
              type="button"
              className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
            >
              Heading 1 <ChevronDown className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
            </button>
            <IconButton label="Bold"><Bold className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Italic"><Italic className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Bulleted list"><List className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        ) : mode === "slide" ? (
          <>
            <IconButton label="Select" active><MousePointer2 className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Text"><Type className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Shapes"><Shapes className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Image"><ImageIcon className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        ) : (
          <>
            <IconButton label="Play" active><Play className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Split"><Scissors className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Captions"><Subtitles className="h-4 w-4" aria-hidden="true" /></IconButton>
            <IconButton label="Audio"><Volume2 className="h-4 w-4" aria-hidden="true" /></IconButton>
          </>
        )}
        <div className="mx-1 h-5 w-px shrink-0 bg-zinc-800" />
        <IconButton label="Print"><Printer className="h-4 w-4" aria-hidden="true" /></IconButton>
        <IconButton label="Share"><Share2 className="h-4 w-4" aria-hidden="true" /></IconButton>
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
                    <h2 className="mt-5 text-[clamp(20px,4vw,34px)] font-semibold leading-tight text-zinc-950">{title}</h2>
                    <p className="mt-3 max-w-[78%] text-[clamp(10px,1.6vw,14px)] leading-5 text-zinc-700">{summary}</p>
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

function MovieSurface({ draft, onDraftChange, onAppendDraftToComposer, onClose }: Omit<WorkspaceSurfacePanelProps, "surface">) {
  const title = cleanTitle(draft, "Untitled movie");

  return (
    <div data-surface-kind="movie" className="flex h-full min-h-0 flex-col bg-[#0f1012]">
      <SurfaceToolbar title={title} mode="movie" onClose={onClose} />
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto flex min-h-full max-w-[820px] flex-col gap-3">
          <section className="grid gap-3 min-[620px]:grid-cols-[minmax(0,1fr)_180px]">
            <div className="rounded-lg border border-zinc-800 bg-black p-2 shadow-2xl shadow-black/30">
              <div className="aspect-video rounded-md border border-zinc-800 bg-gradient-to-br from-zinc-900 via-zinc-950 to-black p-4">
                <div className="flex h-full flex-col justify-between">
                  <div className="flex items-center justify-between text-[11px] text-zinc-500">
                    <span>00:00:12:08</span>
                    <span>1080p</span>
                  </div>
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white">
                    <Play className="ml-0.5 h-6 w-6" aria-hidden="true" />
                  </div>
                  <div className="rounded border border-white/10 bg-black/40 px-3 py-2 text-sm font-medium text-white">{title}</div>
                </div>
              </div>
            </div>
            <aside className="rounded-lg border border-zinc-800 bg-zinc-950/80 p-3">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-zinc-200">
                <PanelRight className="h-4 w-4 text-zinc-500" aria-hidden="true" />
                Inspector
              </div>
              <div className="space-y-3 text-xs text-zinc-500">
                <div>
                  <div className="mb-1 text-zinc-400">Format</div>
                  <div className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-zinc-200">16:9 / H.264</div>
                </div>
                <div>
                  <div className="mb-1 text-zinc-400">Voice</div>
                  <div className="h-2 rounded-full bg-zinc-800">
                    <div className="h-full w-2/3 rounded-full bg-emerald-400" />
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
              <SendToComposerButton onClick={onAppendDraftToComposer} />
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[560px] p-3">
                <div className="mb-2 grid grid-cols-[72px_1fr] text-[10px] text-zinc-500">
                  <div />
                  <div className="grid grid-cols-5">
                    {["00:00", "00:05", "00:10", "00:15", "00:20"].map((mark) => <span key={mark}>{mark}</span>)}
                  </div>
                </div>
                <div className="space-y-2">
                  <TimelineRow label="Video" icon={<Video className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex gap-1">
                      {movieClips.map((clip) => (
                        <div key={clip.label} className={cn("h-12 rounded-md px-2 py-1 text-xs font-medium text-zinc-950", clip.color, clip.width)}>
                          {clip.label}
                        </div>
                      ))}
                    </div>
                  </TimelineRow>
                  <TimelineRow label="Audio" icon={<Volume2 className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex h-9 items-end gap-1 rounded-md bg-emerald-500/20 px-2 py-1">
                      {Array.from({ length: 32 }, (_, index) => (
                        <span
                          key={index}
                          className="w-1 rounded-full bg-emerald-300"
                          style={{ height: `${8 + (index % 5) * 5}px` }}
                        />
                      ))}
                    </div>
                  </TimelineRow>
                  <TimelineRow label="Captions" icon={<Subtitles className="h-3.5 w-3.5" aria-hidden="true" />}>
                    <div className="flex gap-1">
                      <div className="h-8 w-[168px] rounded-md border border-amber-300/40 bg-amber-300/15 px-2 py-1 text-xs text-amber-100">Opening line</div>
                      <div className="h-8 w-[206px] rounded-md border border-amber-300/40 bg-amber-300/15 px-2 py-1 text-xs text-amber-100">Demo narration</div>
                    </div>
                  </TimelineRow>
                </div>
              </div>
            </div>
          </section>

          <textarea
            aria-label="Movie brief"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            spellCheck={false}
            className="h-24 shrink-0 resize-none rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-200 outline-none focus:border-zinc-600"
          />
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
  if (props.surface.kind === "slide") return <SlideSurface {...props} />;
  if (props.surface.kind === "movie") return <MovieSurface {...props} />;
  return <GenericDraftSurface {...props} />;
}
