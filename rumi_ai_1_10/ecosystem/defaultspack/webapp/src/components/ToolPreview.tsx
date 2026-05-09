import React, { useState, useEffect, useMemo } from 'react';
import {
  X, Globe, Terminal, FileText, Image, ExternalLink,
  ChevronLeft, ChevronRight,
  Eye, EyeOff, Code, NotebookPen
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ============================================================
// Types
// ============================================================

export type PreviewType = 'web' | 'code' | 'file' | 'image';

export type WebPreview = {
  type: 'web';
  url: string;
  title: string;
  favicon?: string;
  screenshot?: string;
  snippet?: string;
};

export type CodePreview = {
  type: 'code';
  filename: string;
  language: string;
  diff?: string;
  content?: string;
  additions?: number;
  deletions?: number;
};

export type FilePreview = {
  type: 'file';
  filename: string;
  size: string;
  content?: string;
  url?: string;
  path?: string;
  downloadName?: string;
};

export type ImagePreview = {
  type: 'image';
  url: string;
  alt: string;
  prompt?: string;
  path?: string;
};

export type ToolPreviewData = WebPreview | CodePreview | FilePreview | ImagePreview;

export type ToolPreviewItem = {
  id: string;
  toolStepId: string;
  timestamp: number;
  data: ToolPreviewData;
};

export type ToolPreviewMode = 'auto' | 'manual';

export const MEMO_PREVIEW_ID = '__memo__';

function matchesPreviewId(item: ToolPreviewItem, previewId?: string | null) {
  return Boolean(previewId && (item.id === previewId || item.toolStepId === previewId));
}

export function hasCanvasItems(previews: ToolPreviewItem[], memo?: string | null) {
  return previews.length > 0 || Boolean(memo?.trim());
}

export function buildToolPreviewDisplayItems(
  previews: ToolPreviewItem[],
  memo?: string,
  activePreviewId?: string | null,
): ToolPreviewItem[] {
  const shouldShowMemo = Boolean(memo?.trim()) || activePreviewId === MEMO_PREVIEW_ID || activePreviewId === 'memo';
  const memoPreview: ToolPreviewItem | null = shouldShowMemo
    ? {
        id: MEMO_PREVIEW_ID,
        toolStepId: 'memo',
        timestamp: 0,
        data: {
          type: 'file',
          filename: 'memo.md',
          size: 'local memo',
          content: memo ?? '',
        },
      }
    : null;
  const items = memoPreview ? [memoPreview, ...previews] : [...previews];
  if (!activePreviewId) return items;

  const active = items.find((item) => matchesPreviewId(item, activePreviewId));
  if (!active) return items;
  return [active, ...items.filter((item) => item.id !== active.id)];
}

// ============================================================
// Mock preview data
// ============================================================

export const MOCK_PREVIEWS: ToolPreviewItem[] = [
  {
    id: 'prev-1',
    toolStepId: 's1',
    timestamp: Date.now() - 50000,
    data: {
      type: 'web',
      url: 'https://glassnode.com/metrics/btc',
      title: 'Glassnode - On-Chain Market Intelligence',
      snippet: 'Glassnode provides on-chain data and intelligence for Bitcoin and digital assets. Track exchange flows, miner activity, and whale movements.',
      screenshot: '',
    },
  },
  {
    id: 'prev-2',
    toolStepId: 's3',
    timestamp: Date.now() - 40000,
    data: {
      type: 'web',
      url: 'https://cryptoquant.com/asset/btc/chart/exchange-flows',
      title: 'CryptoQuant - Exchange Netflow',
      snippet: 'Exchange Netflow shows the net amount of BTC flowing in/out of exchanges. Positive values indicate potential selling pressure.',
      screenshot: '',
    },
  },
  {
    id: 'prev-3',
    toolStepId: 's7',
    timestamp: Date.now() - 35000,
    data: {
      type: 'web',
      url: 'https://coinglass.com/bitcoin-exchange-flow',
      title: 'Coinglass - BTC Exchange Flow',
      snippet: 'Real-time Bitcoin exchange flow data including inflows, outflows and net flows across major exchanges.',
      screenshot: '',
    },
  },
  {
    id: 'prev-4',
    toolStepId: 's11',
    timestamp: Date.now() - 30000,
    data: {
      type: 'web',
      url: 'https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html',
      title: 'BitInfoCharts - Top 100 Richest Bitcoin Addresses',
      snippet: 'Bitcoin distribution among addresses. Top 2,000 addresses hold approximately 40% of all BTC.',
      screenshot: '',
    },
  },
  {
    id: 'prev-5',
    toolStepId: 'c1',
    timestamp: Date.now() - 25000,
    data: {
      type: 'file',
      filename: 'package.json',
      size: '1.2KB',
      content: `{
  "name": "dashboard-app",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "typescript": "^5.8.0",
    "vite": "^6.0.0"
  }
}`,
    },
  },
  {
    id: 'prev-6',
    toolStepId: 'c2',
    timestamp: Date.now() - 20000,
    data: {
      type: 'code',
      filename: 'terminal',
      language: 'bash',
      content: `$ npm install recharts date-fns

added 12 packages in 2.4s

4 packages are looking for funding
  run \`npm fund\` for details`,
    },
  },
  {
    id: 'prev-7',
    toolStepId: 'c4',
    timestamp: Date.now() - 15000,
    data: {
      type: 'code',
      filename: 'src/types/sales.ts',
      language: 'typescript',
      additions: 18,
      deletions: 0,
      diff: `+export type SalesRecord = {
+  id: string;
+  date: string;
+  amount: number;
+  category: "electronics" | "clothing" | "food";
+  region: "tokyo" | "osaka" | "fukuoka";
+};
+
+export type DashboardFilter = {
+  period: "7d" | "30d" | "90d";
+  category?: string;
+  region?: string;
+};
+
+export type AggregatedData = {
+  date: string;
+  total: number;
+  count: number;
+};`,
    },
  },
  {
    id: 'prev-8',
    toolStepId: 'c5',
    timestamp: Date.now() - 10000,
    data: {
      type: 'code',
      filename: 'src/components/Dashboard.tsx',
      language: 'typescript',
      additions: 58,
      deletions: 0,
      diff: `+import { useMemo, useState } from "react";
+import {
+  LineChart, Line, XAxis, YAxis,
+  Tooltip, ResponsiveContainer
+} from "recharts";
+import type { SalesRecord, DashboardFilter } from "../types/sales";
+
+type Props = {
+  data: SalesRecord[];
+};
+
+export function Dashboard({ data }: Props) {
+  const [filter, setFilter] = useState<DashboardFilter>({
+    period: "30d",
+  });
+
+  const filtered = useMemo(() => {
+    const days =
+      filter.period === "7d" ? 7 :
+      filter.period === "30d" ? 30 : 90;
+    return data.slice(-days);
+  }, [data, filter]);
+
+  const aggregated = useMemo(() => {
+    const map = new Map<string, number>();
+    for (const r of filtered) {
+      map.set(r.date, (map.get(r.date) || 0) + r.amount);
+    }
+    return Array.from(map.entries()).map(
+      ([date, total]) => ({ date, total })
+    );
+  }, [filtered]);
+
+  return (
+    <div className="p-6 bg-zinc-950 rounded-xl border border-zinc-800">
+      <div className="flex justify-between items-center mb-6">
+        <h2 className="text-lg font-bold text-white">
+          売上推移
+        </h2>
+        <PeriodSelector
+          value={filter.period}
+          onChange={(p) => setFilter(f => ({ ...f, period: p }))}
+        />
+      </div>
+      <ResponsiveContainer width="100%" height={300}>
+        <LineChart data={aggregated}>
+          <XAxis dataKey="date" stroke="#52525b" />
+          <YAxis stroke="#52525b" />
+          <Tooltip />
+          <Line
+            type="monotone"
+            dataKey="total"
+            stroke="#10b981"
+            strokeWidth={2}
+            dot={false}
+          />
+        </LineChart>
+      </ResponsiveContainer>
+    </div>
+  );
+}`,
    },
  },
  {
    id: 'prev-9',
    toolStepId: 'c6',
    timestamp: Date.now() - 5000,
    data: {
      type: 'code',
      filename: 'src/components/FilterBar.tsx',
      language: 'typescript',
      additions: 32,
      deletions: 0,
      diff: `+import type { DashboardFilter } from "../types/sales";
+
+type Props = {
+  filter: DashboardFilter;
+  onChange: (f: DashboardFilter) => void;
+};
+
+const CATEGORIES = ["all", "electronics", "clothing", "food"];
+const REGIONS = ["all", "tokyo", "osaka", "fukuoka"];
+
+export function FilterBar({ filter, onChange }: Props) {
+  return (
+    <div className="flex gap-3 items-center">
+      <select
+        value={filter.category || "all"}
+        onChange={(e) =>
+          onChange({
+            ...filter,
+            category: e.target.value === "all"
+              ? undefined
+              : e.target.value,
+          })
+        }
+        className="bg-zinc-800 text-zinc-200 text-sm
+                   rounded-lg px-3 py-1.5 border border-zinc-700"
+      >
+        {CATEGORIES.map((c) => (
+          <option key={c} value={c}>
+            {c === "all" ? "全カテゴリ" : c}
+          </option>
+        ))}
+      </select>
+    </div>
+  );
+}`,
    },
  },
  {
    id: 'prev-10',
    toolStepId: 'c8',
    timestamp: Date.now() - 2000,
    data: {
      type: 'code',
      filename: 'src/index.css',
      language: 'css',
      additions: 8,
      deletions: 2,
      diff: `@import "tailwindcss";
 
-:root {
-  color-scheme: light;
+:root {
+  color-scheme: dark;
 }
 
+body {
+  background-color: #09090b;
+  color: #fafafa;
+  -webkit-font-smoothing: antialiased;
+}
+
+.dark-chart .recharts-cartesian-grid line {
+  stroke: #27272a;
+}`,
    },
  },
];

// ============================================================
// Preview Content Renderers
// ============================================================

function WebPreviewContent({ data }: { data: WebPreview }) {
  return (
    <div className="flex flex-col h-full">
      {/* Browser chrome */}
      <div className="flex items-center gap-2 px-3 py-2 bg-zinc-900 border-b border-zinc-800/60 flex-shrink-0">
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-zinc-700" />
          <div className="w-2 h-2 rounded-full bg-zinc-700" />
          <div className="w-2 h-2 rounded-full bg-zinc-700" />
        </div>
        <div className="flex-1 flex items-center gap-2 bg-zinc-800 rounded px-2.5 py-1 text-[10px] text-zinc-500 font-mono truncate">
          <Globe size={10} className="flex-shrink-0 text-zinc-600" />
          <span className="truncate">{data.url}</span>
        </div>
        <a
          href={data.url}
          target="_blank"
          rel="noreferrer"
          className="text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <ExternalLink size={12} />
        </a>
      </div>

      {/* Page content */}
      <div className="flex-1 p-4 overflow-y-auto">
        {data.screenshot ? (
          <img
            src={data.screenshot}
            alt={data.title}
            className="w-full rounded border border-zinc-800"
          />
        ) : (
          <div className="space-y-4">
            {/* Mock page screenshot placeholder */}
            <div className="w-full aspect-[16/10] bg-zinc-800/30 rounded-lg border border-zinc-800 flex flex-col items-center justify-center relative overflow-hidden">
              {/* Mock browser content */}
              <div className="absolute inset-0 p-4 space-y-3">
                <div className="h-6 w-3/4 bg-zinc-800/60 rounded" />
                <div className="h-3 w-full bg-zinc-800/40 rounded" />
                <div className="h-3 w-5/6 bg-zinc-800/40 rounded" />
                <div className="h-3 w-4/6 bg-zinc-800/40 rounded" />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="h-16 bg-zinc-800/30 rounded" />
                  <div className="h-16 bg-zinc-800/30 rounded" />
                  <div className="h-16 bg-zinc-800/30 rounded" />
                </div>
                <div className="h-3 w-full bg-zinc-800/40 rounded" />
                <div className="h-3 w-2/3 bg-zinc-800/40 rounded" />
              </div>
              <div className="relative z-10 text-center">
                <Globe size={28} className="text-zinc-700 mx-auto mb-1" />
                <p className="text-[10px] text-zinc-600">Preview</p>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium text-zinc-200 mb-1">{data.title}</h3>
              <p className="text-[10px] text-emerald-600 font-mono mb-2 truncate">{data.url}</p>
              {data.snippet && (
                <p className="text-xs text-zinc-500 leading-relaxed">{data.snippet}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CodePreviewContent({ data }: { data: CodePreview }) {
  return (
    <div className="flex flex-col h-full">
      {/* File tab */}
      <div className="flex items-center justify-between px-3 py-2 bg-zinc-900 border-b border-zinc-800/60 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={12} className="text-zinc-500 flex-shrink-0" />
          <span className="text-[11px] font-mono text-zinc-300 truncate">{data.filename}</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono flex-shrink-0 ml-2">
          {data.additions !== undefined && (
            <span className="text-emerald-500">+{data.additions}</span>
          )}
          {data.deletions !== undefined && data.deletions > 0 && (
            <span className="text-red-400">-{data.deletions}</span>
          )}
          <span className="text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">{data.language}</span>
        </div>
      </div>

      {/* Code / Diff */}
      <div className="flex-1 overflow-y-auto">
        <pre className="text-[11px] font-mono leading-[1.6]">
          {(data.diff || data.content || '').split('\n').map((line, i) => {
            const isAdd = line.startsWith('+') && !line.startsWith('+++');
            const isDel = line.startsWith('-') && !line.startsWith('---');
            return (
              <div
                key={i}
                className={cn(
                  'px-3 min-h-[1.6em]',
                  isAdd && 'bg-emerald-500/8 text-emerald-400',
                  isDel && 'bg-red-500/8 text-red-400',
                  !isAdd && !isDel && 'text-zinc-400'
                )}
              >
                <span className="inline-block w-7 text-right mr-3 text-zinc-700 select-none text-[10px]">
                  {i + 1}
                </span>
                <span>{line}</span>
              </div>
            );
          })}
        </pre>
      </div>
    </div>
  );
}

function FilePreviewContent({ data }: { data: FilePreview }) {
  const looksLikeJson = data.filename.toLowerCase().endsWith('.json') || String(data.content ?? '').trimStart().startsWith('{');
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 bg-zinc-900 border-b border-zinc-800/60 flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText size={12} className="text-zinc-500" />
          <span className="text-[11px] font-mono text-zinc-300">{data.filename}</span>
        </div>
        <div className="flex items-center gap-2">
          {data.url && (
            <a
              href={data.url}
              download={data.downloadName ?? data.filename}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-[10px] text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
            >
              <ExternalLink size={11} />
              開く
            </a>
          )}
          <span className="text-[10px] text-zinc-600">{data.size}</span>
        </div>
      </div>
      {data.path && (
        <div className="border-b border-zinc-800/60 bg-zinc-950/60 px-3 py-2 font-mono text-[10px] text-zinc-600">
          {data.path}
        </div>
      )}
      {looksLikeJson && (
        <div className="border-b border-zinc-800/60 bg-zinc-950/60 px-3 py-2 text-[10px] text-zinc-500">
          JSON の詳細です。必要なときだけ内容を確認してください。
        </div>
      )}
      <div className="flex-1 overflow-y-auto">
        <pre className="text-[11px] font-mono leading-[1.6]">
          {(data.content || '').split('\n').map((line, i) => (
            <div key={i} className="px-3 text-zinc-400 min-h-[1.6em]">
              <span className="inline-block w-7 text-right mr-3 text-zinc-700 select-none text-[10px]">
                {i + 1}
              </span>
              {line}
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

function MemoPreviewContent({
  value,
  onChange,
}: {
  value: string;
  onChange?: (value: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800/60 bg-zinc-900 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <NotebookPen size={12} className="flex-shrink-0 text-zinc-500" />
          <span className="truncate text-[11px] font-medium text-zinc-300">memo.md</span>
        </div>
        <span className="text-[10px] text-zinc-600">local</span>
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder="ここに作業メモを書けます。AI が見ていた path、HTML preview、ブラウザ操作のスクショなどを開いた横で残しておけます。"
        className="h-full flex-1 resize-none border-none bg-[#0a0a0c] p-4 text-[13px] leading-6 text-zinc-200 outline-none placeholder:text-zinc-700"
      />
    </div>
  );
}

function ImagePreviewContent({ data }: { data: ImagePreview }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 bg-zinc-900 border-b border-zinc-800/60 flex-shrink-0">
        <Image size={12} className="text-zinc-500" />
        <span className="text-[11px] text-zinc-300">{data.alt}</span>
      </div>
      <div className="flex-1 p-4 flex items-center justify-center overflow-y-auto">
        {data.url ? (
          <img
            src={data.url}
            alt={data.alt}
            className="max-w-full max-h-full rounded-lg border border-zinc-800"
          />
        ) : (
          <div className="w-full aspect-square max-w-[200px] bg-zinc-800/30 rounded-lg border border-zinc-800 flex items-center justify-center">
            <Image size={32} className="text-zinc-700" />
          </div>
        )}
      </div>
      {data.prompt && (
        <div className="px-3 py-2 border-t border-zinc-800/60 flex-shrink-0">
          <p className="text-[10px] text-zinc-600">
            <span className="text-zinc-500">Prompt:</span> {data.prompt}
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Bottom tab navigation
// ============================================================

function PreviewNav({
  items,
  currentIndex,
  onSelect,
}: {
  items: ToolPreviewItem[];
  currentIndex: number;
  onSelect: (i: number) => void;
}) {
  const navRef = React.useRef<HTMLDivElement>(null);

  // Auto-scroll to active tab
  useEffect(() => {
    if (navRef.current) {
      const activeTab = navRef.current.children[currentIndex] as HTMLElement;
      if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    }
  }, [currentIndex]);

  return (
    <div
      ref={navRef}
      className="flex items-center gap-0.5 px-2 py-1.5 bg-zinc-900/80 border-t border-zinc-800/60 flex-shrink-0 overflow-x-auto"
    >
      {items.map((item, i) => {
        const icon =
          item.data.type === 'web' ? <Globe size={10} /> :
          item.data.type === 'code' ? <Code size={10} /> :
          item.data.type === 'file' ? <FileText size={10} /> :
          <Image size={10} />;

        let label = '';
        switch (item.data.type) {
          case 'web':
            label = (item.data as WebPreview).title;
            break;
          case 'code':
            label = (item.data as CodePreview).filename;
            break;
          case 'file':
            label = (item.data as FilePreview).filename;
            break;
          case 'image':
            label = (item.data as ImagePreview).alt;
            break;
        }

        return (
          <button
            key={item.id}
            onClick={() => onSelect(i)}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded text-[10px] whitespace-nowrap transition-colors flex-shrink-0',
              i === currentIndex
                ? 'bg-zinc-800 text-zinc-200'
                : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/50'
            )}
          >
            {icon}
            <span className="max-w-[80px] truncate">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ============================================================
// ToolPreviewPanel (main export)
// ============================================================

interface ToolPreviewPanelProps {
  previews: ToolPreviewItem[];
  isVisible: boolean;
  onClose: () => void;
  mode: ToolPreviewMode;
  onModeChange: (mode: ToolPreviewMode) => void;
  activePreviewId?: string | null;
  memo?: string;
  onMemoChange?: (value: string) => void;
}

export function ToolPreviewPanel({
  previews,
  isVisible,
  onClose,
  mode,
  onModeChange,
  activePreviewId,
  memo,
  onMemoChange,
}: ToolPreviewPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const displayItems = useMemo(
    () => buildToolPreviewDisplayItems(previews, memo, activePreviewId),
    [activePreviewId, memo, previews],
  );

  // Jump to active preview when it changes (auto mode)
  useEffect(() => {
    if (mode === 'auto' && activePreviewId) {
      const idx = displayItems.findIndex(
        p => matchesPreviewId(p, activePreviewId)
      );
      if (idx !== -1) setCurrentIndex(idx);
    }
  }, [activePreviewId, mode, displayItems]);

  // Also jump when clicked in manual mode
  useEffect(() => {
    if (mode === 'manual' && activePreviewId) {
      const idx = displayItems.findIndex(
        p => matchesPreviewId(p, activePreviewId)
      );
      if (idx !== -1) setCurrentIndex(idx);
    }
  }, [activePreviewId, mode, displayItems]);

  useEffect(() => {
    if (currentIndex >= displayItems.length) {
      setCurrentIndex(0);
    }
  }, [currentIndex, displayItems.length]);

  if (!isVisible || displayItems.length === 0) return null;

  const current = displayItems[Math.min(currentIndex, displayItems.length - 1)];
  const isMemo = current.id === MEMO_PREVIEW_ID;

  const renderContent = () => {
    if (isMemo) return <MemoPreviewContent value={memo ?? ''} onChange={onMemoChange} />;
    switch (current.data.type) {
      case 'web':
        return <WebPreviewContent data={current.data} />;
      case 'code':
        return <CodePreviewContent data={current.data} />;
      case 'file':
        return <FilePreviewContent data={current.data} />;
      case 'image':
        return <ImagePreviewContent data={current.data} />;
    }
  };

  const typeLabel =
    isMemo ? 'Memo' :
    current.data.type === 'web' ? 'Web' :
    current.data.type === 'code' ? 'Code' :
    current.data.type === 'file' ? 'File' : 'Image';

  const typeIcon =
    isMemo ? <NotebookPen size={12} className="text-zinc-300" /> :
    current.data.type === 'web' ? <Globe size={12} className="text-emerald-400" /> :
    current.data.type === 'code' ? <Code size={12} className="text-amber-400" /> :
    current.data.type === 'file' ? <FileText size={12} className="text-violet-400" /> :
    <Image size={12} className="text-blue-400" />;

  return (
    <div className="flex flex-col h-full border-l border-zinc-800/60 bg-[#0a0a0c] w-full">
      {/* Header */}
      <div className="h-10 flex items-center justify-between px-3 border-b border-zinc-800/60 flex-shrink-0">
        <div className="flex items-center gap-2">
          {typeIcon}
          <span className="text-[11px] font-medium text-zinc-400">{typeLabel}</span>
          <span className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">
            {currentIndex + 1}/{displayItems.length}
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          {/* Auto/Manual toggle */}
          <button
            onClick={() => onModeChange(mode === 'auto' ? 'manual' : 'auto')}
            className={cn(
              'flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium transition-colors border',
              mode === 'auto'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : 'bg-zinc-800 text-zinc-500 border-zinc-800'
            )}
            title={
              mode === 'auto'
                ? 'Auto: ツール使用時に自動切替'
                : 'Manual: クリックで表示'
            }
          >
            {mode === 'auto' ? <Eye size={10} /> : <EyeOff size={10} />}
            {mode === 'auto' ? 'Auto' : 'Manual'}
          </button>

          {/* Navigation arrows */}
          <button
            onClick={() => setCurrentIndex(i => Math.max(0, i - 1))}
            disabled={currentIndex === 0}
            className="p-1 text-zinc-600 hover:text-zinc-300 disabled:opacity-20 transition-colors"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            onClick={() => setCurrentIndex(i => Math.min(displayItems.length - 1, i + 1))}
            disabled={currentIndex === displayItems.length - 1}
            className="p-1 text-zinc-600 hover:text-zinc-300 disabled:opacity-20 transition-colors"
          >
            <ChevronRight size={14} />
          </button>

          {/* Close */}
          <button
            onClick={onClose}
            className="p-1 text-zinc-600 hover:text-zinc-300 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">{renderContent()}</div>

      {/* Bottom tab nav */}
      <PreviewNav
        items={displayItems}
        currentIndex={currentIndex}
        onSelect={setCurrentIndex}
      />
    </div>
  );
}
