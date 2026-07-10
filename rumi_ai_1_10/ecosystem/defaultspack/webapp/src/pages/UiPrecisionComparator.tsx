import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Columns3,
  CreditCard,
  GitBranch,
  HeartPulse,
  Inbox,
  LayoutDashboard,
  Mail,
  MessageSquare,
  Monitor,
  Play,
  Search,
  ShoppingCart,
  SlidersHorizontal,
  Smartphone,
  SplitSquareHorizontal,
  TableProperties,
  Tablet,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "../lib/cn";

export type PrecisionViewport = 390 | 768 | 1440;
type LeafStatus = "accepted" | "review" | "rejected";
type GateStatus = "pass" | "warn" | "fail";
type PreviewVariant = "raw" | "rumi";
type ScenarioId =
  | "ai-chat"
  | "support-inbox"
  | "analytics-console"
  | "kanban-planner"
  | "ecommerce-configurator"
  | "clinical-intake"
  | "fintech-approval"
  | "data-grid-admin";

type LeafNode = {
  id: string;
  label: string;
  purpose: string;
  status: LeafStatus;
  rawCompression: number;
  rumiCompression: number;
  rawActions: number;
  rumiActions: number;
  candidates: number;
  acceptedCandidate: string;
};

type Gate = {
  id: string;
  label: string;
  raw: GateStatus;
  rumi: GateStatus;
  detail: string;
};

type ViewportProof = {
  viewport: PrecisionViewport;
  label: string;
  rawIssues: string;
  rumiIssues: string;
  rawScore: number;
  rumiScore: number;
};

type PreviewSpec = {
  shellTitle: string;
  topTools: string[];
  listTitle: string;
  listItems: Array<{ title: string; meta: string; detail: string }>;
  mainTitle: string;
  mainBody: string;
  sideTitle: string;
  sideItems: string[];
  composerLabel: string;
  actions: string[];
  resultNotes: string[];
};

type Scenario = {
  id: ScenarioId;
  label: string;
  shortLabel: string;
  scoreLabel: string;
  request: string;
  description: string;
  leaves: LeafNode[];
  gates: Gate[];
  viewportProofs: ViewportProof[];
  rawPreview: PreviewSpec;
  rumiPreview: PreviewSpec;
  timeline: string[];
};

export const precisionViewports: PrecisionViewport[] = [390, 768, 1440];

const scenarioLibrary: Scenario[] = [
  {
    id: "ai-chat",
    label: "AI Chat App",
    shortLabel: "Chat",
    scoreLabel: "RAG chat with tools",
    description: "AI chatの生成精度を、message / source / tool / composer単位で比較。",
    request: `RAG対応のAI chat appを作る。
左にチャット履歴、中央に会話、右にToolsとSourcesを置く。
長い日本語質問、引用source、model設定、送信composerを含める。
390px / 768px / 1440pxで主要操作が読めること。`,
    leaves: [
      {
        id: "chat-shell",
        label: "ChatShell",
        purpose: "navigation, search, thread slots",
        status: "accepted",
        rawCompression: 0.52,
        rumiCompression: 0.16,
        rawActions: 10,
        rumiActions: 3,
        candidates: 3,
        acceptedCandidate: "B",
      },
      {
        id: "message-stream",
        label: "MessageStream",
        purpose: "long answer, citations, feedback",
        status: "accepted",
        rawCompression: 0.61,
        rumiCompression: 0.22,
        rawActions: 12,
        rumiActions: 4,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "tool-rail",
        label: "ToolRail",
        purpose: "docs, web, code, image tools",
        status: "accepted",
        rawCompression: 0.58,
        rumiCompression: 0.19,
        rawActions: 9,
        rumiActions: 4,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "source-stack",
        label: "SourceStack",
        purpose: "trustable evidence cards",
        status: "accepted",
        rawCompression: 0.49,
        rumiCompression: 0.18,
        rawActions: 7,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "chat-composer",
        label: "ChatComposer",
        purpose: "ask, attach, model, send",
        status: "review",
        rawCompression: 0.55,
        rumiCompression: 0.27,
        rawActions: 11,
        rumiActions: 4,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "chat-primary-flow",
        label: "Question -> cited answer flow",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は引用と回答が同じ泡に詰まり、source再確認ができない。",
      },
      {
        id: "tool-pressure",
        label: "Tool action pressure",
        raw: "fail",
        rumi: "pass",
        detail: "Rumi案はtool railを独立leafにして、composerの操作数を4以内に維持。",
      },
      {
        id: "mobile-chat-route",
        label: "Mobile route",
        raw: "warn",
        rumi: "pass",
        detail: "Raw案はdesktop列の縮小、Rumi案はThreads / Chat / Toolsをroute化。",
      },
      {
        id: "source-legibility",
        label: "Source legibility",
        raw: "fail",
        rumi: "pass",
        detail: "日本語の長いsource名をカード化し、page番号と信頼状態を分離。",
      },
      {
        id: "semantic-regions",
        label: "Semantic regions",
        raw: "warn",
        rumi: "pass",
        detail: "Shell、stream、tools、composerを別contractで採点。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile chat route",
        rawIssues: "three columns squeezed / source hidden",
        rumiIssues: "tabbed route / composer remains visible",
        rawScore: 0.68,
        rumiScore: 0.22,
      },
      {
        viewport: 768,
        label: "tablet source drawer",
        rawIssues: "tool buttons wrap to 4 rows",
        rumiIssues: "tools collapse into right drawer",
        rawScore: 0.51,
        rumiScore: 0.2,
      },
      {
        viewport: 1440,
        label: "desktop three-panel",
        rawIssues: "generic chat skeleton / weak source proof",
        rumiIssues: "all chat leaves accepted",
        rawScore: 0.43,
        rumiScore: 0.14,
      },
    ],
    rawPreview: {
      shellTitle: "AI Chat",
      topTools: ["New", "Search", "RAG", "Web", "Code", "Image", "DB", "Share", "Export"],
      listTitle: "Chats",
      listItems: [
        { title: "RAGとは何かを説明して", meta: "2:31 PM", detail: "履歴 / source / model を同じ行に表示" },
        { title: "transformerの注意機構を要約", meta: "1:45 PM", detail: "長い件名が省略される" },
        { title: "PDFから要点を抽出", meta: "11:02 AM", detail: "状態と操作が混在" },
      ],
      mainTitle: "How does RAG work?",
      mainBody:
        "RAG combines information retrieval with language generation... source, answer, feedback, tool results are compressed into one generic bubble.",
      sideTitle: "Tools / Sources",
      sideItems: ["Search Docs", "Web", "Code", "Image", "rag-overview.pdf page 3", "arxiv link"],
      composerLabel: "Type your message...",
      actions: ["Attach", "Model", "Tools", "Voice", "Save", "Send"],
      resultNotes: ["visual hierarchy weak", "source trust unclear", "hard gates 1 / 6"],
    },
    rumiPreview: {
      shellTitle: "AI Chat Pro",
      topTools: ["New chat", "Search", "Sources", "Tools"],
      listTitle: "Thread inbox",
      listItems: [
        { title: "RAGとは何かを説明して", meta: "source ready", detail: "回答 / 引用 / tool状態を分離" },
        { title: "社内PDFから請求条件を抽出", meta: "3 refs", detail: "source cardへ直接ジャンプ" },
        { title: "長い日本語質問の検証", meta: "draft", detail: "mobileでも全文入口を維持" },
      ],
      mainTitle: "RAG combines retrieval and generation",
      mainBody:
        "回答本文、引用source、tool result、feedback controlsを別leafで生成。視線は質問、回答、sourceの順に流れます。",
      sideTitle: "Tools and sources",
      sideItems: ["Search Docs / ready", "Web Search / optional", "Code Interpreter / off", "docs/rag-overview.pdf p.3", "社内FAQ: retrieval policy", "Top K: 5 / Temp: 0.2"],
      composerLabel: "Ask anything with sources...",
      actions: ["Attach", "Model", "Send"],
      resultNotes: ["sources readable", "composer <= 3 actions", "hard gates 6 / 6"],
    },
    timeline: [
      "ChatShell chooses three-region desktop and tabbed mobile routes",
      "MessageStream spawns answer, citations, and feedback as separate leaves",
      "ToolRail rejects overloaded toolbar candidate",
      "Composer keeps only attach, model, send visible",
    ],
  },
  {
    id: "support-inbox",
    label: "Support Inbox",
    shortLabel: "Inbox",
    scoreLabel: "Japanese support workflow",
    description: "未対応会話の処理画面を、toolbar / list / composer / context単位で比較。",
    request: `未対応会話を短時間で処理するInbox画面を作る。
日本語の長い件名、返信composer、顧客context、絞り込みtoolbarを含める。
390px / 768px / 1440pxで主要操作が読めること。`,
    leaves: [
      {
        id: "page-frame",
        label: "PageFrame",
        purpose: "macro layout and slot capacity",
        status: "accepted",
        rawCompression: 0.39,
        rumiCompression: 0.14,
        rawActions: 7,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "filter-toolbar",
        label: "FilterToolbar",
        purpose: "narrow conversation set",
        status: "accepted",
        rawCompression: 0.48,
        rumiCompression: 0.21,
        rawActions: 9,
        rumiActions: 4,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "conversation-list",
        label: "ConversationList",
        purpose: "find the next thread",
        status: "accepted",
        rawCompression: 0.44,
        rumiCompression: 0.18,
        rawActions: 6,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "reply-composer",
        label: "ReplyComposer",
        purpose: "draft, recover, send",
        status: "accepted",
        rawCompression: 0.57,
        rumiCompression: 0.24,
        rawActions: 11,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "customer-context",
        label: "CustomerContext",
        purpose: "read supporting context",
        status: "review",
        rawCompression: 0.36,
        rumiCompression: 0.29,
        rawActions: 5,
        rumiActions: 2,
        candidates: 1,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "primary-action",
        label: "Primary action visible",
        raw: "warn",
        rumi: "pass",
        detail: "Raw案は390pxで返信ボタンが折り返し後に沈む。",
      },
      {
        id: "action-budget",
        label: "Action budget",
        raw: "fail",
        rumi: "pass",
        detail: "ReplyComposer contractはvisible actions <= 3。",
      },
      {
        id: "arbitrary-token",
        label: "Foundation token lock",
        raw: "warn",
        rumi: "pass",
        detail: "Raw案はstatus colorを通常CTAにも使っている。",
      },
      {
        id: "responsive-topology",
        label: "Responsive topology",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案はdesktop列を縮小するだけでmobile routeへ変化しない。",
      },
      {
        id: "text-pressure",
        label: "Long Japanese text",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は長い会社名と件名でellipsisが連続する。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile route",
        rawIssues: "horizontal stress / 4 clipped labels",
        rumiIssues: "route split / no hard gate failure",
        rawScore: 0.62,
        rumiScore: 0.24,
      },
      {
        viewport: 768,
        label: "tablet split",
        rawIssues: "toolbar wraps to 3 rows",
        rumiIssues: "context as drawer",
        rawScore: 0.47,
        rumiScore: 0.21,
      },
      {
        viewport: 1440,
        label: "desktop frame",
        rawIssues: "surface pressure in every region",
        rumiIssues: "all primary leaves accepted",
        rawScore: 0.41,
        rumiScore: 0.17,
      },
    ],
    rawPreview: {
      shellTitle: "Support Desk",
      topTools: ["All", "Unread", "SLA", "Assign", "Tag", "Export", "Bulk", "Priority"],
      listTitle: "Conversation list",
      listItems: [
        { title: "請求書の宛名変更について至急確認したい", meta: "5 act", detail: "契約、添付、返信、担当、優先度を同じ行に表示" },
        { title: "長い会社名株式会社アルファベータ様", meta: "new", detail: "顧客contextが見つけにくい" },
        { title: "週次レポートの送付先追加", meta: "new", detail: "返信入口が下に沈む" },
      ],
      mainTitle: "長い件名でも返信の入口を失わない",
      mainBody: "先方から長い会社名と複数条件を含む返信依頼。操作、履歴、添付、承認が同じ領域に混在しています。",
      sideTitle: "Customer context",
      sideItems: ["Plan: Pro", "SLA: 4h", "Owner: Sales", "Contract: pending", "History: 12"],
      composerLabel: "返信、添付、AI、整形、要約、担当変更、タグ、承認、履歴、保存、送信...",
      actions: ["Attach", "AI", "Format", "Approve", "Save", "Send"],
      resultNotes: ["action overload", "mobile primary hidden", "hard gates 2 / 5"],
    },
    rumiPreview: {
      shellTitle: "Support Inbox",
      topTools: ["Unread", "SLA", "Owner", "More"],
      listTitle: "Next replies",
      listItems: [
        { title: "請求書の宛名変更について至急確認したい", meta: "open", detail: "primary textを残し、補助情報は次行へ分離" },
        { title: "長い会社名株式会社アルファベータ様", meta: "SLA 2h", detail: "会社名と担当者を別slotで保持" },
        { title: "週次レポートの送付先追加", meta: "draft", detail: "返信composerへ直接復帰" },
      ],
      mainTitle: "返信composerを常に主導線に固定",
      mainBody: "thread本文、顧客context、返信composerを別leafで生成。mobileではContextをdrawer化して本文と返信を守ります。",
      sideTitle: "Customer context",
      sideItems: ["Plan: Pro / renewal soon", "SLA: 2h remaining", "Owner: Haru", "Last invoice: #3028", "Risk: billing name mismatch"],
      composerLabel: "下書きを入力。補助操作は必要時だけ開きます。",
      actions: ["Attach", "Draft", "Send"],
      resultNotes: ["reply visible", "long Japanese safe", "hard gates 5 / 5"],
    },
    timeline: [
      "PageFrame fixes desktop and mobile information topology",
      "FilterToolbar rejects eight-button toolbar at 390px",
      "ReplyComposer caps visible actions at three",
      "CustomerContext moves to drawer on tablet and mobile",
    ],
  },
  {
    id: "analytics-console",
    label: "Analytics Console",
    shortLabel: "Analytics",
    scoreLabel: "Metric drill-down console",
    description: "KPI dashboardを、chart / filter / anomaly / table単位で比較。",
    request: `SaaSの利用状況を監視するanalytics consoleを作る。
KPIカード、時系列chart、異常値一覧、segment filter、drill-down tableを含める。
390px / 768px / 1440pxで数字と異常検知が読めること。`,
    leaves: [
      {
        id: "metric-header",
        label: "MetricHeader",
        purpose: "current KPI and date range",
        status: "accepted",
        rawCompression: 0.46,
        rumiCompression: 0.15,
        rawActions: 8,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "trend-chart",
        label: "TrendChart",
        purpose: "time-series focus",
        status: "accepted",
        rawCompression: 0.64,
        rumiCompression: 0.2,
        rawActions: 10,
        rumiActions: 3,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "anomaly-list",
        label: "AnomalyList",
        purpose: "triage unusual spikes",
        status: "accepted",
        rawCompression: 0.51,
        rumiCompression: 0.18,
        rawActions: 6,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "drilldown-table",
        label: "DrilldownTable",
        purpose: "compare segment rows",
        status: "review",
        rawCompression: 0.59,
        rumiCompression: 0.3,
        rawActions: 9,
        rumiActions: 4,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "number-legibility",
        label: "Number legibility",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案はKPIと凡例が同じ密度で、重要な数値が埋もれる。",
      },
      {
        id: "chart-axis",
        label: "Chart axis survives mobile",
        raw: "fail",
        rumi: "pass",
        detail: "Rumi案はmobileでchartとtableを別route化し、軸labelの欠落を防ぐ。",
      },
      {
        id: "filter-contract",
        label: "Segment filter contract",
        raw: "warn",
        rumi: "pass",
        detail: "filterをKPI headerから分離し、drill-downだけがfilter stateを受け取る。",
      },
      {
        id: "anomaly-priority",
        label: "Anomaly priority",
        raw: "warn",
        rumi: "pass",
        detail: "severity / owner / next actionを別slotで生成。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile metric route",
        rawIssues: "chart axis clipped / KPI wraps",
        rumiIssues: "KPI, chart, anomalies as separate routes",
        rawScore: 0.66,
        rumiScore: 0.25,
      },
      {
        viewport: 768,
        label: "tablet drill-down",
        rawIssues: "table loses 3 columns",
        rumiIssues: "table becomes prioritized rows",
        rawScore: 0.49,
        rumiScore: 0.22,
      },
      {
        viewport: 1440,
        label: "desktop console",
        rawIssues: "same card rhythm everywhere",
        rumiIssues: "chart, anomalies, table have distinct roles",
        rawScore: 0.4,
        rumiScore: 0.16,
      },
    ],
    rawPreview: {
      shellTitle: "Analytics",
      topTools: ["Today", "7d", "30d", "Segment", "Region", "CSV", "Alert", "Share"],
      listTitle: "Metrics",
      listItems: [
        { title: "Active users 128,482", meta: "+12%", detail: "KPI, filter, trendを同じcardに圧縮" },
        { title: "Conversion 4.8%", meta: "-1.2%", detail: "異常値の理由が見えない" },
        { title: "Revenue 21.4M", meta: "+8%", detail: "table列がmobileで欠落" },
      ],
      mainTitle: "Usage trend",
      mainBody: "A single generic dashboard with repeated cards. The line chart, segment filter, anomaly list, and table compete for the same visual priority.",
      sideTitle: "Drill down",
      sideItems: ["Plan", "Region", "Device", "Owner", "CSV", "Alert"],
      composerLabel: "Filter, export, compare, annotate, share...",
      actions: ["Filter", "Compare", "Export", "Alert", "Share"],
      resultNotes: ["weak metric hierarchy", "axis clipped", "hard gates 1 / 4"],
    },
    rumiPreview: {
      shellTitle: "Usage Console",
      topTools: ["7d", "Segment", "Compare", "Alert"],
      listTitle: "KPI strip",
      listItems: [
        { title: "Active users 128,482", meta: "+12.4%", detail: "primary metric + delta only" },
        { title: "Conversion 4.8%", meta: "watch", detail: "severity badge separated" },
        { title: "Revenue 21.4M", meta: "+8.1%", detail: "drilldown table owns details" },
      ],
      mainTitle: "Trend chart with anomaly focus",
      mainBody: "時系列chart、異常値list、drill-down tableを別leaf化。desktopでは比較、mobileではroute分割して数字を守ります。",
      sideTitle: "Anomalies",
      sideItems: ["Trial -> paid drop: -1.2%", "JP enterprise spike: +18%", "iOS activation lag: 6h", "Owner: Growth", "Next: inspect cohort"],
      composerLabel: "Ask an analytics question...",
      actions: ["Segment", "Ask", "Alert"],
      resultNotes: ["numbers readable", "axis preserved", "hard gates 4 / 4"],
    },
    timeline: [
      "MetricHeader locks number scale before chart generation",
      "TrendChart generates desktop and mobile chart contracts separately",
      "AnomalyList rejects low-priority card grid",
      "DrilldownTable switches to row summaries on 390px",
    ],
  },
  {
    id: "kanban-planner",
    label: "Kanban Planner",
    shortLabel: "Kanban",
    scoreLabel: "Team planning board",
    description: "タスクboardを、column / card / detail / quick action単位で比較。",
    request: `開発チーム向けのkanban plannerを作る。
Backlog / Doing / Review / Done、担当者、期限、blocked状態、詳細drawerを含める。
390px / 768px / 1440pxでカード移動と詳細確認が読めること。`,
    leaves: [
      {
        id: "board-shell",
        label: "BoardShell",
        purpose: "columns and swimlane scale",
        status: "accepted",
        rawCompression: 0.6,
        rumiCompression: 0.2,
        rawActions: 8,
        rumiActions: 3,
        candidates: 3,
        acceptedCandidate: "B",
      },
      {
        id: "task-card",
        label: "TaskCard",
        purpose: "owner, due, state, title",
        status: "accepted",
        rawCompression: 0.56,
        rumiCompression: 0.17,
        rawActions: 7,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "detail-drawer",
        label: "DetailDrawer",
        purpose: "selected task context",
        status: "accepted",
        rawCompression: 0.47,
        rumiCompression: 0.19,
        rawActions: 6,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "drag-affordance",
        label: "DragAffordance",
        purpose: "move card safely",
        status: "review",
        rawCompression: 0.5,
        rumiCompression: 0.28,
        rawActions: 5,
        rumiActions: 2,
        candidates: 1,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "column-overflow",
        label: "Column overflow",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は4列をmobileへそのまま縮小して、カードtitleが読めない。",
      },
      {
        id: "card-density",
        label: "Task card density",
        raw: "fail",
        rumi: "pass",
        detail: "Rumi案はcard summaryとdetail drawerを分離し、card内の表示数を制限。",
      },
      {
        id: "blocked-signal",
        label: "Blocked signal",
        raw: "warn",
        rumi: "pass",
        detail: "blocked状態を色だけでなく文言slotにも出す。",
      },
      {
        id: "quick-actions",
        label: "Quick action budget",
        raw: "warn",
        rumi: "pass",
        detail: "Add, Move, Assignだけを常時表示し、残りはdrawerへ送る。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile swimlane route",
        rawIssues: "4 columns squeezed / card text lost",
        rumiIssues: "single lane route + detail drawer",
        rawScore: 0.7,
        rumiScore: 0.26,
      },
      {
        viewport: 768,
        label: "tablet two-lane",
        rawIssues: "drag target ambiguity",
        rumiIssues: "two lanes with explicit move targets",
        rawScore: 0.52,
        rumiScore: 0.23,
      },
      {
        viewport: 1440,
        label: "desktop planning board",
        rawIssues: "card grid repetitive",
        rumiIssues: "board, drawer, status rail separated",
        rawScore: 0.44,
        rumiScore: 0.18,
      },
    ],
    rawPreview: {
      shellTitle: "Kanban",
      topTools: ["Add", "Assign", "Move", "Label", "Sprint", "Export", "Filter", "Archive"],
      listTitle: "Columns",
      listItems: [
        { title: "Backlog / Doing / Review / Done", meta: "4 cols", detail: "mobileでも全列を縮小" },
        { title: "UI compiler leaf contracts", meta: "blocked", detail: "状態が色だけに依存" },
        { title: "Viewport proof capture", meta: "due Fri", detail: "担当者と期限が詰まる" },
      ],
      mainTitle: "Board overview",
      mainBody: "All columns, card details, assignment, due dates, blocked states, and move actions are packed into the board surface.",
      sideTitle: "Task details",
      sideItems: ["Owner", "Due", "Labels", "Subtasks", "Comments", "History"],
      composerLabel: "Add task, assign, move, label, archive...",
      actions: ["Add", "Assign", "Move", "Label", "Archive"],
      resultNotes: ["mobile unreadable", "drag targets unclear", "hard gates 1 / 4"],
    },
    rumiPreview: {
      shellTitle: "Planner Board",
      topTools: ["Add", "Move", "Assign", "Filter"],
      listTitle: "Active lane",
      listItems: [
        { title: "UI compiler leaf contracts", meta: "blocked", detail: "blocked reason shown in card footer" },
        { title: "Viewport proof capture", meta: "due Fri", detail: "owner and due date stay visible" },
        { title: "Candidate tournament UI", meta: "review", detail: "details move into drawer" },
      ],
      mainTitle: "Board columns with detail drawer",
      mainBody: "columns、task card、detail drawer、drag affordanceを別leafで生成。mobileはlane route、desktopはboard + drawerへ合成。",
      sideTitle: "Selected task",
      sideItems: ["Owner: Aya", "Due: Friday", "Blocked by: API decision", "Next action: split ToolRail", "Move target: Review"],
      composerLabel: "Add a focused task...",
      actions: ["Add", "Assign", "Move"],
      resultNotes: ["card text readable", "drag intent clear", "hard gates 4 / 4"],
    },
    timeline: [
      "BoardShell picks lane route for mobile before card rendering",
      "TaskCard limits permanent fields to title, owner, due, state",
      "DetailDrawer receives comments and history instead of crowding cards",
      "DragAffordance records explicit move targets for touch screens",
    ],
  },
  {
    id: "ecommerce-configurator",
    label: "Ecommerce Configurator",
    shortLabel: "Commerce",
    scoreLabel: "B2B product configuration",
    description: "商品構成、在庫、価格、互換性警告を、gallery / option / quote / checkout単位で比較。",
    request: `B2B向けのproduct configuratorを作る。
商品gallery、構成option、互換性警告、価格見積、在庫、checkout CTAを含める。
390px / 768px / 1440pxで選択内容と価格変化が読めること。`,
    leaves: [
      {
        id: "product-gallery",
        label: "ProductGallery",
        purpose: "compare variants and availability",
        status: "accepted",
        rawCompression: 0.58,
        rumiCompression: 0.2,
        rawActions: 9,
        rumiActions: 3,
        candidates: 3,
        acceptedCandidate: "B",
      },
      {
        id: "option-matrix",
        label: "OptionMatrix",
        purpose: "configure model, color, storage, warranty",
        status: "accepted",
        rawCompression: 0.66,
        rumiCompression: 0.23,
        rawActions: 14,
        rumiActions: 4,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "compatibility-alerts",
        label: "CompatibilityAlerts",
        purpose: "explain impossible combinations",
        status: "accepted",
        rawCompression: 0.53,
        rumiCompression: 0.18,
        rawActions: 6,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "quote-summary",
        label: "QuoteSummary",
        purpose: "show price, lead time, and checkout readiness",
        status: "accepted",
        rawCompression: 0.49,
        rumiCompression: 0.16,
        rawActions: 8,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "checkout-cta",
        label: "CheckoutCTA",
        purpose: "primary purchase path and saved quote state",
        status: "review",
        rawCompression: 0.45,
        rumiCompression: 0.26,
        rawActions: 7,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "price-legibility",
        label: "Price delta legibility",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は価格、在庫、構成optionが同じカード内で競合する。",
      },
      {
        id: "compatibility-state",
        label: "Compatibility state",
        raw: "fail",
        rumi: "pass",
        detail: "互換性警告を専用leafにして、checkout CTAを警告文で押しつぶさない。",
      },
      {
        id: "mobile-configuration",
        label: "Mobile configuration route",
        raw: "warn",
        rumi: "pass",
        detail: "Rumi案はGallery / Configure / Quoteをroute化して、価格を常に読める。",
      },
      {
        id: "action-budget-commerce",
        label: "Commerce action budget",
        raw: "fail",
        rumi: "pass",
        detail: "Add、Save quote、Checkout以外の補助操作をMoreへ退避。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile configure route",
        rawIssues: "option grid collapses / price hidden",
        rumiIssues: "sticky quote summary remains visible",
        rawScore: 0.69,
        rumiScore: 0.24,
      },
      {
        viewport: 768,
        label: "tablet two-step quote",
        rawIssues: "compatibility alert pushes CTA below fold",
        rumiIssues: "alert leaf reserves its own region",
        rawScore: 0.54,
        rumiScore: 0.21,
      },
      {
        viewport: 1440,
        label: "desktop configurator",
        rawIssues: "repeated option cards flatten price hierarchy",
        rumiIssues: "gallery, options, quote have distinct emphasis",
        rawScore: 0.43,
        rumiScore: 0.15,
      },
    ],
    rawPreview: {
      shellTitle: "Product Configurator",
      topTools: ["Filter", "Compare", "Stock", "Warranty", "Save", "Share", "Quote", "Checkout"],
      listTitle: "Products",
      listItems: [
        { title: "Laptop Pro 14 / 32GB / 2TB", meta: "low", detail: "構成、在庫、警告、価格が同じ行へ圧縮" },
        { title: "Docking Station Enterprise", meta: "warn", detail: "互換性が色だけで示される" },
        { title: "3-year care pack", meta: "+¥42,000", detail: "価格差分が埋もれる" },
      ],
      mainTitle: "Configure bundle",
      mainBody: "Every product option, stock badge, warning, price delta, and checkout action is rendered inside a single generic commerce surface.",
      sideTitle: "Quote",
      sideItems: ["Subtotal", "Stock", "Lead time", "Warranty", "Approvals", "Tax"],
      composerLabel: "Select, compare, quote, save, share, checkout...",
      actions: ["Compare", "Warranty", "Save", "Share", "Checkout"],
      resultNotes: ["price hierarchy weak", "CTA below alert", "hard gates 2 / 4"],
    },
    rumiPreview: {
      shellTitle: "B2B Configurator",
      topTools: ["Compare", "Stock", "Save quote", "Checkout"],
      listTitle: "Recommended bundle",
      listItems: [
        { title: "Laptop Pro 14 / 32GB / 2TB", meta: "in stock", detail: "構成summaryと在庫を別slotに分離" },
        { title: "USB-C Dock Enterprise", meta: "compatible", detail: "警告はCompatibilityAlertsへ移動" },
        { title: "Care pack 3-year", meta: "+¥42,000", detail: "価格差分をQuoteSummaryへ同期" },
      ],
      mainTitle: "Configuration options with clear price deltas",
      mainBody: "gallery、option matrix、compatibility alerts、quote summaryを別leaf生成。選択状態と価格が同じ視線順で更新されます。",
      sideTitle: "Quote summary",
      sideItems: ["Subtotal: ¥428,000", "Lead time: 5 business days", "Stock: 12 reserved", "Approval: not required", "Compatibility: passed"],
      composerLabel: "保存済み見積に追加できます。",
      actions: ["Save", "Quote", "Checkout"],
      resultNotes: ["price visible", "alerts separated", "hard gates 4 / 4"],
    },
    timeline: [
      "ProductGallery owns image and availability rhythm",
      "OptionMatrix rejects eleven visible configuration controls",
      "CompatibilityAlerts isolates impossible combinations",
      "QuoteSummary keeps price and lead time visible on 390px",
    ],
  },
  {
    id: "clinical-intake",
    label: "Clinical Intake",
    shortLabel: "Clinical",
    scoreLabel: "Healthcare form and triage",
    description: "問診、症状triage、薬剤履歴、同意、次アクションを、安全なform flowとして比較。",
    request: `クリニック向けのclinical intake画面を作る。
患者基本情報、症状triage、服薬履歴、アレルギー、同意確認、次の予約導線を含める。
390px / 768px / 1440pxで必須項目と警告が見落とされないこと。`,
    leaves: [
      {
        id: "patient-summary",
        label: "PatientSummary",
        purpose: "identity, appointment, risk flags",
        status: "accepted",
        rawCompression: 0.5,
        rumiCompression: 0.17,
        rawActions: 5,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "symptom-triage",
        label: "SymptomTriage",
        purpose: "severity, duration, red flags",
        status: "accepted",
        rawCompression: 0.68,
        rumiCompression: 0.24,
        rawActions: 12,
        rumiActions: 4,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "medication-history",
        label: "MedicationHistory",
        purpose: "current meds and allergy warnings",
        status: "accepted",
        rawCompression: 0.57,
        rumiCompression: 0.2,
        rawActions: 8,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "consent-review",
        label: "ConsentReview",
        purpose: "consent, privacy, data sharing",
        status: "accepted",
        rawCompression: 0.46,
        rumiCompression: 0.18,
        rawActions: 6,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "appointment-action",
        label: "AppointmentAction",
        purpose: "next appointment and submit readiness",
        status: "review",
        rawCompression: 0.48,
        rumiCompression: 0.27,
        rawActions: 7,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "required-fields",
        label: "Required fields visible",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は必須項目と任意項目が同じ強さで、未入力が発見しづらい。",
      },
      {
        id: "clinical-warning",
        label: "Clinical warning separation",
        raw: "fail",
        rumi: "pass",
        detail: "アレルギーとred flagをMedicationHistory/SymptomTriageへ分離。",
      },
      {
        id: "consent-readability",
        label: "Consent readability",
        raw: "warn",
        rumi: "pass",
        detail: "同意文を長文formの末尾に詰め込まず、ConsentReviewとして独立採点。",
      },
      {
        id: "mobile-form-flow",
        label: "Mobile form flow",
        raw: "fail",
        rumi: "pass",
        detail: "390pxではSummary / Triage / Reviewの段階routeで入力負荷を分割。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile intake steps",
        rawIssues: "required markers buried / consent below long form",
        rumiIssues: "step route keeps warning and submit visible",
        rawScore: 0.71,
        rumiScore: 0.25,
      },
      {
        viewport: 768,
        label: "tablet triage split",
        rawIssues: "all fields become same-size rows",
        rumiIssues: "risk flags stay in left summary",
        rawScore: 0.52,
        rumiScore: 0.22,
      },
      {
        viewport: 1440,
        label: "desktop intake console",
        rawIssues: "form sections visually flatten",
        rumiIssues: "triage, meds, consent have separate contracts",
        rawScore: 0.42,
        rumiScore: 0.16,
      },
    ],
    rawPreview: {
      shellTitle: "Clinical Intake",
      topTools: ["Patient", "Symptoms", "Meds", "Allergy", "Consent", "Attach", "Save", "Submit"],
      listTitle: "Sections",
      listItems: [
        { title: "患者情報 / 症状 / 服薬 / 同意", meta: "long", detail: "一つのform surfaceに全項目を連結" },
        { title: "発熱と息苦しさの申告", meta: "risk", detail: "red flagが通常項目と同列" },
        { title: "薬剤アレルギーあり", meta: "warn", detail: "警告の根拠が追いづらい" },
      ],
      mainTitle: "Intake form",
      mainBody: "Patient identity, symptom triage, medication, allergy, consent, and appointment actions are squeezed into a single long form.",
      sideTitle: "Review",
      sideItems: ["Required", "Risk", "Consent", "Files", "Appointment"],
      composerLabel: "Save, submit, attach, notify, schedule...",
      actions: ["Attach", "Notify", "Save", "Schedule", "Submit"],
      resultNotes: ["required unclear", "warning buried", "hard gates 2 / 4"],
    },
    rumiPreview: {
      shellTitle: "Clinical Intake",
      topTools: ["Summary", "Triage", "Review", "Submit"],
      listTitle: "Patient summary",
      listItems: [
        { title: "山田 花子 / 初診", meta: "today", detail: "本人確認と予約contextを固定" },
        { title: "息苦しさあり", meta: "red flag", detail: "SymptomTriageへ優先表示" },
        { title: "ペニシリン allergy", meta: "critical", detail: "MedicationHistoryが根拠を保持" },
      ],
      mainTitle: "Triage first, consent last with explicit review",
      mainBody: "患者summary、症状triage、服薬履歴、同意reviewを別leaf化。必須入力と警告が視線順で確認できます。",
      sideTitle: "Readiness",
      sideItems: ["Required fields: 8 / 8", "Red flags: reviewed", "Allergy: acknowledged", "Consent: pending signature", "Next: schedule nurse call"],
      composerLabel: "レビュー後に送信できます。",
      actions: ["Review", "Save", "Submit"],
      resultNotes: ["warnings visible", "required clear", "hard gates 4 / 4"],
    },
    timeline: [
      "PatientSummary fixes identity and appointment context",
      "SymptomTriage owns severity and red flag semantics",
      "MedicationHistory separates allergy evidence from generic notes",
      "ConsentReview keeps legal text readable before submit",
    ],
  },
  {
    id: "fintech-approval",
    label: "Fintech Approval",
    shortLabel: "Fintech",
    scoreLabel: "Risk decision workflow",
    description: "送金/与信approvalを、risk signal / ledger / exception / approval CTA単位で比較。",
    request: `金融オペレーション向けのapproval consoleを作る。
取引詳細、risk score、KYC status、例外理由、監査ログ、承認/差戻し導線を含める。
390px / 768px / 1440pxで判断根拠と承認操作が混ざらないこと。`,
    leaves: [
      {
        id: "transaction-summary",
        label: "TransactionSummary",
        purpose: "amount, party, payment rail, deadline",
        status: "accepted",
        rawCompression: 0.47,
        rumiCompression: 0.15,
        rawActions: 4,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "risk-signal-stack",
        label: "RiskSignalStack",
        purpose: "KYC, sanctions, velocity, anomaly evidence",
        status: "accepted",
        rawCompression: 0.69,
        rumiCompression: 0.24,
        rawActions: 11,
        rumiActions: 4,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "exception-review",
        label: "ExceptionReview",
        purpose: "operator notes and policy mismatch",
        status: "accepted",
        rawCompression: 0.56,
        rumiCompression: 0.19,
        rawActions: 7,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "audit-ledger",
        label: "AuditLedger",
        purpose: "immutable history and evidence trail",
        status: "accepted",
        rawCompression: 0.52,
        rumiCompression: 0.18,
        rawActions: 5,
        rumiActions: 1,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "approval-actions",
        label: "ApprovalActions",
        purpose: "approve, request info, reject",
        status: "review",
        rawCompression: 0.44,
        rumiCompression: 0.26,
        rawActions: 8,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "risk-evidence",
        label: "Risk evidence hierarchy",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案はrisk scoreと監査ログが同じ密度で、判断根拠が埋もれる。",
      },
      {
        id: "approval-separation",
        label: "Approval action separation",
        raw: "fail",
        rumi: "pass",
        detail: "承認CTAをRiskSignalStackから分離し、誤操作を防ぐ。",
      },
      {
        id: "audit-readability",
        label: "Audit readability",
        raw: "warn",
        rumi: "pass",
        detail: "監査履歴はAuditLedgerへ移し、primary decision面を軽くする。",
      },
      {
        id: "mobile-risk-review",
        label: "Mobile risk review",
        raw: "fail",
        rumi: "pass",
        detail: "390pxではRisk / Exception / Actionの順に段階表示。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile approval route",
        rawIssues: "approve CTA near unresolved exception",
        rumiIssues: "action route requires evidence review",
        rawScore: 0.73,
        rumiScore: 0.26,
      },
      {
        viewport: 768,
        label: "tablet evidence stack",
        rawIssues: "audit log steals primary space",
        rumiIssues: "ledger becomes secondary drawer",
        rawScore: 0.51,
        rumiScore: 0.22,
      },
      {
        viewport: 1440,
        label: "desktop risk console",
        rawIssues: "risk cards and actions visually merge",
        rumiIssues: "signals, exceptions, actions are isolated",
        rawScore: 0.41,
        rumiScore: 0.15,
      },
    ],
    rawPreview: {
      shellTitle: "Approval Console",
      topTools: ["Risk", "KYC", "Ledger", "Notes", "Request", "Reject", "Approve", "Export"],
      listTitle: "Transactions",
      listItems: [
        { title: "¥18,400,000 wire transfer", meta: "high", detail: "risk signalと承認CTAが同じカード" },
        { title: "KYC document mismatch", meta: "warn", detail: "例外理由が監査ログに混ざる" },
        { title: "Sanctions check cleared", meta: "ok", detail: "重要度が区別されない" },
      ],
      mainTitle: "Risk decision",
      mainBody: "Transaction details, KYC, sanctions checks, ledger history, notes, and approval controls compete inside one dense risk dashboard.",
      sideTitle: "Audit",
      sideItems: ["Created", "KYC checked", "Policy exception", "Ops note", "Escalation"],
      composerLabel: "Approve, reject, request info, add note, export...",
      actions: ["Note", "Request", "Export", "Reject", "Approve"],
      resultNotes: ["decision evidence weak", "CTA too close", "hard gates 2 / 4"],
    },
    rumiPreview: {
      shellTitle: "Risk Approval",
      topTools: ["Risk", "Exception", "Ledger", "Actions"],
      listTitle: "Decision queue",
      listItems: [
        { title: "¥18,400,000 wire transfer", meta: "review", detail: "TransactionSummary owns amount and rail" },
        { title: "KYC mismatch", meta: "exception", detail: "ExceptionReview owns policy mismatch" },
        { title: "Sanctions clear", meta: "verified", detail: "RiskSignalStack preserves evidence order" },
      ],
      mainTitle: "Evidence before approval",
      mainBody: "risk signal、exception review、audit ledger、approval actionsを別leaf化。承認前に根拠と未解決例外が明確に残ります。",
      sideTitle: "Action readiness",
      sideItems: ["KYC: needs secondary review", "Sanctions: clear", "Velocity: elevated", "Exception note: required", "Approval: locked until review"],
      composerLabel: "レビュー完了後に操作可能。",
      actions: ["Request", "Reject", "Approve"],
      resultNotes: ["evidence readable", "CTA separated", "hard gates 4 / 4"],
    },
    timeline: [
      "TransactionSummary fixes amount and counterparty hierarchy",
      "RiskSignalStack rejects mixed CTA plus evidence candidate",
      "ExceptionReview owns policy mismatch and operator notes",
      "ApprovalActions remains locked until review evidence is visible",
    ],
  },
  {
    id: "data-grid-admin",
    label: "Data Grid Admin",
    shortLabel: "Admin",
    scoreLabel: "Dense enterprise table",
    description: "高密度table、filter builder、bulk action、row detail、audit stateを、admin UIとして比較。",
    request: `エンタープライズ管理者向けのdata gridを作る。
10列以上の表、filter builder、bulk action、row detail drawer、権限status、audit stateを含める。
390px / 768px / 1440pxで横overflowとbulk誤操作を避けること。`,
    leaves: [
      {
        id: "grid-shell",
        label: "GridShell",
        purpose: "table topology and sticky regions",
        status: "accepted",
        rawCompression: 0.7,
        rumiCompression: 0.24,
        rawActions: 9,
        rumiActions: 3,
        candidates: 3,
        acceptedCandidate: "B",
      },
      {
        id: "filter-builder",
        label: "FilterBuilder",
        purpose: "compound filters without toolbar overload",
        status: "accepted",
        rawCompression: 0.62,
        rumiCompression: 0.21,
        rawActions: 13,
        rumiActions: 4,
        candidates: 3,
        acceptedCandidate: "C",
      },
      {
        id: "bulk-action-bar",
        label: "BulkActionBar",
        purpose: "selection count and guarded mutation",
        status: "accepted",
        rawCompression: 0.55,
        rumiCompression: 0.19,
        rawActions: 10,
        rumiActions: 3,
        candidates: 2,
        acceptedCandidate: "A",
      },
      {
        id: "row-detail-drawer",
        label: "RowDetailDrawer",
        purpose: "inspect selected record safely",
        status: "accepted",
        rawCompression: 0.49,
        rumiCompression: 0.18,
        rawActions: 6,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "B",
      },
      {
        id: "audit-state-rail",
        label: "AuditStateRail",
        purpose: "permission and audit status",
        status: "review",
        rawCompression: 0.46,
        rumiCompression: 0.27,
        rawActions: 5,
        rumiActions: 2,
        candidates: 2,
        acceptedCandidate: "pending",
      },
    ],
    gates: [
      {
        id: "horizontal-overflow",
        label: "Horizontal overflow",
        raw: "fail",
        rumi: "pass",
        detail: "Raw案は10列を390pxへ縮小し、横scrollと読めない列を作る。",
      },
      {
        id: "bulk-guard",
        label: "Bulk mutation guard",
        raw: "fail",
        rumi: "pass",
        detail: "BulkActionBarがselection countと危険操作を独立管理。",
      },
      {
        id: "filter-builder-density",
        label: "Filter builder density",
        raw: "warn",
        rumi: "pass",
        detail: "filter chip群をtoolbarではなくbuilder leafへ逃がす。",
      },
      {
        id: "row-detail-mobile",
        label: "Row detail mobile",
        raw: "fail",
        rumi: "pass",
        detail: "mobileはtable全列ではなくrow summary + detail drawerへ変形。",
      },
    ],
    viewportProofs: [
      {
        viewport: 390,
        label: "mobile row summary",
        rawIssues: "10 columns overflow / bulk action clipped",
        rumiIssues: "row summaries plus guarded action sheet",
        rawScore: 0.76,
        rumiScore: 0.27,
      },
      {
        viewport: 768,
        label: "tablet filter drawer",
        rawIssues: "filter toolbar wraps to 4 rows",
        rumiIssues: "filter builder becomes drawer",
        rawScore: 0.56,
        rumiScore: 0.22,
      },
      {
        viewport: 1440,
        label: "desktop admin grid",
        rawIssues: "all admin controls compete above table",
        rumiIssues: "grid, filters, bulk, audit have bounded roles",
        rawScore: 0.44,
        rumiScore: 0.16,
      },
    ],
    rawPreview: {
      shellTitle: "Admin Grid",
      topTools: ["Search", "Filter", "Columns", "Export", "Delete", "Role", "Audit", "Bulk"],
      listTitle: "Records",
      listItems: [
        { title: "Enterprise account permissions table", meta: "12 cols", detail: "全列を縮小してmobileへ押し込む" },
        { title: "7 rows selected", meta: "bulk", detail: "危険操作が通常toolbarに混在" },
        { title: "Audit pending", meta: "warn", detail: "権限状態が表の隅に沈む" },
      ],
      mainTitle: "User permissions",
      mainBody: "A dense table, filter builder, column controls, export, bulk mutation, row detail, permission status, and audit state share one crowded admin surface.",
      sideTitle: "Details",
      sideItems: ["Role", "Team", "Policy", "Last login", "Audit", "History"],
      composerLabel: "Filter, export, delete, role, audit, notify...",
      actions: ["Filter", "Export", "Delete", "Role", "Audit"],
      resultNotes: ["horizontal overflow", "bulk risk", "hard gates 2 / 4"],
    },
    rumiPreview: {
      shellTitle: "Enterprise Admin",
      topTools: ["Search", "Filter", "Columns", "Bulk"],
      listTitle: "Row summaries",
      listItems: [
        { title: "Account: Northstar Operations", meta: "admin", detail: "mobileでは主要列だけsummary化" },
        { title: "7 rows selected", meta: "guarded", detail: "BulkActionBarが確認状態を保持" },
        { title: "Audit pending", meta: "review", detail: "AuditStateRailで状態を分離" },
      ],
      mainTitle: "Dense grid with bounded controls",
      mainBody: "grid shell、filter builder、bulk action bar、row detail drawer、audit state railを別leaf化。table密度を保ちながら誤操作を抑えます。",
      sideTitle: "Selected row",
      sideItems: ["Role: Admin", "Policy: Finance Ops", "Audit: pending", "Last login: 09:24", "Risk: external share disabled"],
      composerLabel: "選択行に対して安全な操作だけ表示。",
      actions: ["Filter", "Review", "Bulk"],
      resultNotes: ["no overflow", "bulk guarded", "hard gates 4 / 4"],
    },
    timeline: [
      "GridShell chooses row-summary route before table rendering",
      "FilterBuilder moves compound conditions out of the toolbar",
      "BulkActionBar rejects destructive action crowding",
      "RowDetailDrawer preserves dense data without mobile overflow",
    ],
  },
];

export const uiPrecisionScenarioLibrary = scenarioLibrary;

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function compressionDelta(leaf: LeafNode): number {
  return Number((leaf.rawCompression - leaf.rumiCompression).toFixed(2));
}

export function proofForViewport(
  viewport: PrecisionViewport,
  proofs: ViewportProof[] = scenarioLibrary[0].viewportProofs,
): ViewportProof {
  return proofs.find((proof) => proof.viewport === viewport) ?? proofs[0];
}

export function gateSummary(items: Gate[]): { rawFailed: number; rumiFailed: number } {
  return {
    rawFailed: items.filter((gate) => gate.raw === "fail").length,
    rumiFailed: items.filter((gate) => gate.rumi === "fail").length,
  };
}

export function promptFingerprint(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `prompt-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function scenarioIcon(id: ScenarioId, className?: string) {
  const props = { size: 17, className, "aria-hidden": true as const };
  if (id === "ai-chat") return <Bot {...props} />;
  if (id === "support-inbox") return <Inbox {...props} />;
  if (id === "analytics-console") return <BarChart3 {...props} />;
  if (id === "kanban-planner") return <Columns3 {...props} />;
  if (id === "ecommerce-configurator") return <ShoppingCart {...props} />;
  if (id === "clinical-intake") return <HeartPulse {...props} />;
  if (id === "fintech-approval") return <CreditCard {...props} />;
  return <TableProperties {...props} />;
}

function statusTone(status: LeafStatus): string {
  if (status === "accepted") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (status === "review") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-red-500/25 bg-red-500/10 text-red-100";
}

function gateTone(status: GateStatus): string {
  if (status === "pass") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (status === "warn") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-red-500/25 bg-red-500/10 text-red-100";
}

function gateIcon(status: GateStatus) {
  if (status === "pass") return <CheckCircle2 size={14} aria-hidden="true" />;
  if (status === "warn") return <AlertTriangle size={14} aria-hidden="true" />;
  return <XCircle size={14} aria-hidden="true" />;
}

function ScoreBar({ label, value, tone }: { label: string; value: number; tone: PreviewVariant }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-[11px] font-medium text-zinc-400">
        <span>{label}</span>
        <span className={tone === "raw" ? "text-amber-200" : "text-emerald-200"}>{percent(value)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-zinc-900">
        <div
          className={cn("h-full rounded-full", tone === "raw" ? "bg-amber-400" : "bg-emerald-400")}
          style={{ width: percent(value) }}
        />
      </div>
    </div>
  );
}

function ScenarioRail({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
}: {
  scenarios: Scenario[];
  selectedScenarioId: ScenarioId;
  onSelectScenario: (id: ScenarioId) => void;
}) {
  return (
    <div className="space-y-2" aria-label="App scenarios">
      {scenarios.map((scenario) => {
        const active = scenario.id === selectedScenarioId;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() => onSelectScenario(scenario.id)}
            className={cn(
              "grid w-full grid-cols-[auto_1fr] gap-3 rounded-lg border px-3 py-3 text-left transition",
              active
                ? "border-cyan-400/50 bg-cyan-400/12 text-zinc-50"
                : "border-zinc-800 bg-zinc-950/70 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900/80",
            )}
          >
            <span
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg border",
                active ? "border-cyan-300/45 bg-cyan-300/15 text-cyan-100" : "border-zinc-800 bg-black/20 text-zinc-500",
              )}
            >
              {scenarioIcon(scenario.id)}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{scenario.label}</span>
              <span className="mt-0.5 block truncate text-[11px] text-zinc-500">{scenario.scoreLabel}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function LeafTree({
  leaves,
  selectedLeafId,
  onSelectLeaf,
}: {
  leaves: LeafNode[];
  selectedLeafId: string;
  onSelectLeaf: (id: string) => void;
}) {
  return (
    <nav className="space-y-2" aria-label="Recursive UI leaf nodes">
      {leaves.map((leaf) => {
        const active = leaf.id === selectedLeafId;
        return (
          <button
            key={leaf.id}
            type="button"
            onClick={() => onSelectLeaf(leaf.id)}
            className={cn(
              "grid w-full grid-cols-[1fr_auto] gap-3 rounded-lg border px-3 py-2.5 text-left transition",
              active
                ? "border-cyan-400/45 bg-cyan-400/10 text-zinc-50"
                : "border-zinc-800 bg-zinc-950/70 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900/80",
            )}
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{leaf.label}</span>
              <span className="mt-0.5 block truncate text-[11px] text-zinc-500">{leaf.purpose}</span>
            </span>
            <span className={cn("self-start rounded-md border px-1.5 py-0.5 text-[10px] font-semibold", statusTone(leaf.status))}>
              {leaf.status}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function RequestPanel({
  scenarios,
  scenario,
  request,
  onRequestChange,
  selectedLeafId,
  onSelectLeaf,
  onSelectScenario,
}: {
  scenarios: Scenario[];
  scenario: Scenario;
  request: string;
  onRequestChange: (value: string) => void;
  selectedLeafId: string;
  onSelectLeaf: (id: string) => void;
  onSelectScenario: (id: ScenarioId) => void;
}) {
  return (
    <aside className="flex min-h-0 flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">App presets</h2>
          <p className="mt-1 text-xs leading-5 text-zinc-500">別タイプのUIを同じ比較器で生成します。</p>
        </div>
        <GitBranch size={18} className="mt-0.5 shrink-0 text-cyan-300" aria-hidden="true" />
      </div>
      <ScenarioRail scenarios={scenarios} selectedScenarioId={scenario.id} onSelectScenario={onSelectScenario} />
      <div>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase text-zinc-500">Request brief</h3>
          <span className="text-[11px] text-cyan-200">{scenario.shortLabel}</span>
        </div>
        <textarea
          value={request}
          onChange={(event) => onRequestChange(event.target.value)}
          className="min-h-40 w-full resize-y rounded-lg border border-zinc-800 bg-black/30 px-3 py-2.5 text-sm leading-6 text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-cyan-400/50"
          aria-label="UI generation request"
        />
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase text-zinc-500">Recursive split tree</h3>
          <span className="text-[11px] text-zinc-600">leaves {scenario.leaves.length}</span>
        </div>
        <LeafTree leaves={scenario.leaves} selectedLeafId={selectedLeafId} onSelectLeaf={onSelectLeaf} />
      </div>
    </aside>
  );
}

function PreviewToolbar({ spec, variant }: { spec: PreviewSpec; variant: PreviewVariant }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-zinc-800 px-3 py-2">
      {spec.topTools.map((tool) => (
        <span
          key={tool}
          className={cn(
            "rounded-md border px-2 py-1 text-[10px] font-semibold",
            variant === "raw"
              ? "border-amber-400/20 bg-amber-400/10 text-amber-100"
              : "border-zinc-700 bg-zinc-900 text-zinc-300",
          )}
        >
          {tool}
        </span>
      ))}
    </div>
  );
}

function PreviewList({ spec, variant }: { spec: PreviewSpec; variant: PreviewVariant }) {
  return (
    <section className="min-w-0 overflow-hidden border-zinc-800 lg:border-r">
      <div className="border-b border-zinc-800 px-3 py-2">
        <p className="text-[11px] font-semibold uppercase text-zinc-500">{spec.listTitle}</p>
      </div>
      {spec.listItems.map((item, index) => (
        <div key={item.title} className={cn("border-b border-zinc-900 px-3 py-2.5", index === 0 ? "bg-cyan-400/10" : "")}>
          <div className="flex items-center justify-between gap-2">
            <p className="min-w-0 truncate text-xs font-semibold text-zinc-100">{item.title}</p>
            <span
              className={cn(
                "shrink-0 rounded px-1.5 py-0.5 text-[10px]",
                variant === "raw" && index === 0 ? "bg-red-500/20 text-red-100" : "bg-zinc-800 text-zinc-400",
              )}
            >
              {item.meta}
            </span>
          </div>
          <p className={cn("mt-1 text-[11px] leading-4", variant === "raw" ? "line-clamp-1 text-zinc-500" : "text-zinc-500")}>
            {item.detail}
          </p>
        </div>
      ))}
    </section>
  );
}

function PreviewMain({
  spec,
  variant,
  viewport,
}: {
  spec: PreviewSpec;
  variant: PreviewVariant;
  viewport: PrecisionViewport;
}) {
  const isRaw = variant === "raw";
  const isMobile = viewport === 390;
  return (
    <section className="min-w-0 overflow-hidden">
      <div className="border-b border-zinc-800 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs font-semibold text-zinc-100">{spec.mainTitle}</p>
          <span
            className={cn(
              "rounded-md border px-1.5 py-0.5 text-[10px] font-semibold",
              isRaw ? "border-red-500/30 text-red-100" : "border-emerald-500/30 text-emerald-100",
            )}
          >
            {isRaw ? "reject" : "accepted"}
          </span>
        </div>
      </div>
      <div className="space-y-2 px-3 py-3">
        <div className={cn("rounded-lg border border-zinc-800 bg-zinc-900/50 p-2.5", isRaw ? "opacity-85" : "")}>
          <p className="text-xs leading-5 text-zinc-300">{spec.mainBody}</p>
        </div>
        {!isRaw && (
          <div className={cn("grid gap-2", isMobile ? "grid-cols-1" : "grid-cols-3")}>
            {spec.resultNotes.map((note) => (
              <div key={note} className="rounded-lg border border-emerald-400/20 bg-emerald-400/8 px-2.5 py-2 text-[11px] leading-4 text-emerald-100">
                {note}
              </div>
            ))}
          </div>
        )}
        <div className={cn("rounded-lg border p-2.5", isRaw ? "border-amber-400/25 bg-amber-400/10" : "border-zinc-800 bg-zinc-900/40")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-zinc-400">{spec.composerLabel}</span>
            <span className={cn("text-[10px]", isRaw ? "text-amber-100" : "text-emerald-100")}>
              {isRaw ? `${spec.actions.length + 4} visible actions` : `${spec.actions.length} visible actions`}
            </span>
          </div>
          <div className="min-h-18 rounded-md border border-zinc-800 bg-black/25 px-2 py-2 text-xs leading-5 text-zinc-400">
            {isRaw ? spec.actions.join(", ") : spec.composerLabel}
          </div>
          <div className="mt-2 flex flex-wrap justify-end gap-1.5">
            {spec.actions.map((action, index) => (
              <span
                key={action}
                className={cn(
                  "rounded-md px-2 py-1 text-[10px] font-semibold",
                  index === spec.actions.length - 1
                    ? "bg-cyan-400 text-zinc-950"
                    : "border border-zinc-800 bg-zinc-950 text-zinc-400",
                )}
              >
                {action}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function PreviewSidePanel({ spec, variant }: { spec: PreviewSpec; variant: PreviewVariant }) {
  return (
    <section className={cn("min-w-0 overflow-hidden border-t border-zinc-800 lg:border-l lg:border-t-0", variant === "raw" ? "bg-black/12" : "")}>
      <div className="border-b border-zinc-800 px-3 py-2">
        <p className="text-[11px] font-semibold uppercase text-zinc-500">{spec.sideTitle}</p>
      </div>
      <div className="space-y-1.5 p-3">
        {spec.sideItems.map((item) => (
          <div
            key={item}
            className={cn(
              "rounded-md border px-2 py-1.5 text-[11px] leading-4",
              variant === "raw" ? "border-zinc-800 bg-zinc-950 text-zinc-500" : "border-zinc-800 bg-zinc-900/70 text-zinc-300",
            )}
          >
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}

function AppPreview({
  scenario,
  spec,
  variant,
  viewport,
}: {
  scenario: Scenario;
  spec: PreviewSpec;
  variant: PreviewVariant;
  viewport: PrecisionViewport;
}) {
  const isRaw = variant === "raw";
  const isMobile = viewport === 390;
  return (
    <div
      className={cn(
        "min-w-0 max-w-full overflow-hidden rounded-lg border bg-zinc-950 text-zinc-100",
        isRaw ? "border-amber-400/30" : "border-emerald-400/30",
      )}
      data-rumi-node={variant === "raw" ? "raw-static-preview" : "structured-static-preview"}
      data-rumi-scenario={scenario.id}
      data-rumi-density={isRaw ? "over-compressed" : "recursive-detail"}
      data-rumi-role="static-demo-render"
    >
      <div className="flex min-h-10 items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {scenarioIcon(scenario.id, isRaw ? "text-amber-200" : "text-cyan-200")}
          <span className="truncate text-xs font-semibold text-zinc-100">{spec.shellTitle}</span>
        </div>
        <span className={cn("shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold", isRaw ? "border-red-500/30 text-red-100" : "border-emerald-500/30 text-emerald-100")}>
          {isRaw ? "static raw fixture" : `static structured fixture · ${scenario.leaves.length} leaves`}
        </span>
      </div>
      <PreviewToolbar spec={spec} variant={variant} />
      <div
        className={cn(
          "grid min-h-[390px] min-w-0",
          isMobile
            ? "grid-cols-1"
            : isRaw
              ? "lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]"
              : "lg:grid-cols-[minmax(0,0.72fr)_minmax(0,1.2fr)_minmax(190px,0.68fr)]",
        )}
      >
        <PreviewList spec={spec} variant={variant} />
        <PreviewMain spec={spec} variant={variant} viewport={viewport} />
        {(!isRaw || !isMobile) && <PreviewSidePanel spec={spec} variant={variant} />}
      </div>
      {isRaw && (
        <div className="border-t border-zinc-800 px-3 py-2">
          <div className="grid gap-2 sm:grid-cols-3">
            {spec.resultNotes.map((note) => (
              <span key={note} className="rounded-md border border-red-500/20 bg-red-500/8 px-2 py-1 text-[11px] text-red-100">
                {note}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RenderPreviewPanel({ scenario, variant, viewport }: { scenario: Scenario; variant: PreviewVariant; viewport: PrecisionViewport }) {
  const title = variant === "raw" ? "Illustrative raw layout" : "Illustrative structured layout";
  const subtitle = "hand-authored static fixture; no model invocation";
  const summary = gateSummary(scenario.gates);
  const spec = variant === "raw" ? scenario.rawPreview : scenario.rumiPreview;
  return (
    <section className="min-w-0 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-zinc-100">{title}</h2>
          <p className="mt-1 truncate text-xs text-zinc-500">
            {scenario.label} / {subtitle}
          </p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-cyan-200">Static example data. Editing the brief does not regenerate this preview.</p>
        </div>
        <span
          className={cn(
            "rounded-md border px-2 py-1 text-[11px] font-semibold",
            variant === "raw" ? "border-amber-500/25 bg-amber-500/10 text-amber-100" : "border-emerald-500/25 bg-emerald-500/10 text-emerald-100",
          )}
        >
          {variant === "raw" ? `${summary.rawFailed} illustrative flags` : `${summary.rumiFailed} illustrative flags`}
        </span>
      </div>
      <AppPreview scenario={scenario} spec={spec} variant={variant} viewport={viewport} />
    </section>
  );
}

function FairnessLedger({ request }: { request: string }) {
  const fingerprint = promptFingerprint(request);
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Static scenario disclosure</h2>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            この画面は手作業で作成した説明用fixtureです。モデル実行、候補生成、採点、再現実験は行いません。
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-zinc-800 bg-black/25 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase text-zinc-500">Prompt</p>
            <p className="mt-1 truncate text-xs font-semibold text-cyan-100">{fingerprint}</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-black/25 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase text-zinc-500">Runtime calls</p>
            <p className="mt-1 text-xs font-semibold text-emerald-100">0</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-black/25 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase text-zinc-500">Generated artifacts</p>
            <p className="mt-1 text-xs font-semibold text-emerald-100">0</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function InspectorPanel({
  scenario,
  selectedLeaf,
  viewport,
}: {
  scenario: Scenario;
  selectedLeaf: LeafNode;
  viewport: PrecisionViewport;
}) {
  const proof = proofForViewport(viewport, scenario.viewportProofs);
  const summary = gateSummary(scenario.gates);
  return (
    <aside className="flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div>
        <h2 className="text-sm font-semibold text-zinc-100">Illustrative layout inspector</h2>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          選択中: {selectedLeaf.label} / {scenario.label} / viewport {viewport}px
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
        <div className="rounded-lg border border-zinc-800 bg-black/25 p-3">
          <p className="text-[11px] font-semibold uppercase text-zinc-500">Raw fixture</p>
          <p className="mt-1 text-lg font-semibold text-amber-100">{selectedLeaf.rawActions} actions</p>
          <p className="text-[11px] text-zinc-500">single prompt pressure</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-black/25 p-3">
          <p className="text-[11px] font-semibold uppercase text-zinc-500">Structured fixture</p>
          <p className="mt-1 text-lg font-semibold text-emerald-100">{selectedLeaf.rumiActions} actions</p>
          <p className="text-[11px] text-zinc-500">accepted leaf budget</p>
        </div>
      </div>
      <div className="space-y-3">
        <ScoreBar label="Illustrative raw density" value={selectedLeaf.rawCompression} tone="raw" />
        <ScoreBar label="Illustrative structured density" value={selectedLeaf.rumiCompression} tone="rumi" />
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-xs leading-5 text-cyan-50">
          改善差分 {percent(compressionDelta(selectedLeaf))} / visible actions {selectedLeaf.rawActions}{" -> "}
          {selectedLeaf.rumiActions}
        </div>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-zinc-400">
          <span>Illustrative review flags</span>
          <span>
            {summary.rawFailed}
            {" -> "}
            {summary.rumiFailed} fail
          </span>
        </div>
        <div className="space-y-2">
          {scenario.gates.map((gate) => (
            <div key={gate.id} className="rounded-lg border border-zinc-800 bg-black/25 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-200">{gate.label}</span>
                <span className="flex shrink-0 items-center gap-1">
                  <span className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold", gateTone(gate.raw))}>
                    {gateIcon(gate.raw)} raw
                  </span>
                  <span className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold", gateTone(gate.rumi))}>
                    {gateIcon(gate.rumi)} rumi
                  </span>
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-4 text-zinc-500">{gate.detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-black/25 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-zinc-200">Viewport note</span>
          <span className="text-[11px] text-zinc-500">{proof.label}</span>
        </div>
        <p className="text-[11px] leading-5 text-amber-100">Raw: {proof.rawIssues}</p>
        <p className="text-[11px] leading-5 text-emerald-100">Rumi: {proof.rumiIssues}</p>
      </div>
    </aside>
  );
}

function CandidateTournament({ selectedLeaf }: { selectedLeaf: LeafNode }) {
  const rows = [
    { name: "Candidate A", result: selectedLeaf.acceptedCandidate === "A" ? "accepted" : "rejected", score: selectedLeaf.rumiCompression },
    {
      name: "Candidate B",
      result: selectedLeaf.acceptedCandidate === "B" ? "accepted" : selectedLeaf.candidates > 1 ? "rejected" : "not spawned",
      score: Math.min(0.64, selectedLeaf.rumiCompression + 0.12),
    },
    {
      name: "Candidate C",
      result: selectedLeaf.acceptedCandidate === "C" ? "accepted" : selectedLeaf.candidates > 2 ? "rejected" : "not spawned",
      score: Math.min(0.72, selectedLeaf.rumiCompression + 0.2),
    },
  ];
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Candidate layout examples</h2>
          <p className="mt-1 text-xs text-zinc-500">候補名・状態・数値は説明用の静的サンプルで、生成結果ではありません。</p>
        </div>
        <SplitSquareHorizontal size={18} className="text-cyan-300" aria-hidden="true" />
      </div>
      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <div className="grid grid-cols-[1.1fr_0.8fr_0.8fr] border-b border-zinc-800 bg-zinc-900/70 px-3 py-2 text-[11px] font-semibold uppercase text-zinc-500">
          <span>bundle</span>
          <span>result</span>
          <span>score</span>
        </div>
        {rows.map((row) => (
          <div key={row.name} className="grid grid-cols-[1.1fr_0.8fr_0.8fr] border-b border-zinc-900 px-3 py-2 text-xs last:border-b-0">
            <span className="font-medium text-zinc-200">{row.name}</span>
            <span className={row.result === "accepted" ? "text-emerald-200" : "text-zinc-500"}>{row.result}</span>
            <span className="text-zinc-400">{row.result === "not spawned" ? "-" : percent(row.score)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProofStrip({
  scenario,
  viewport,
  onViewportChange,
}: {
  scenario: Scenario;
  viewport: PrecisionViewport;
  onViewportChange: (value: PrecisionViewport) => void;
}) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Viewport example strip</h2>
          <p className="mt-1 text-xs text-zinc-500">390 / 768 / 1440px向けに用意した静的なレイアウト例を切り替えます。</p>
        </div>
        <LayoutDashboard size={18} className="text-cyan-300" aria-hidden="true" />
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {scenario.viewportProofs.map((proof) => {
          const active = proof.viewport === viewport;
          const Icon = proof.viewport === 390 ? Smartphone : proof.viewport === 768 ? Tablet : Monitor;
          return (
            <button
              key={proof.viewport}
              type="button"
              onClick={() => onViewportChange(proof.viewport)}
              className={cn(
                "rounded-lg border p-3 text-left transition",
                active ? "border-cyan-400/45 bg-cyan-400/10" : "border-zinc-800 bg-black/25 hover:border-zinc-700",
              )}
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-sm font-semibold text-zinc-100">
                  <Icon size={15} aria-hidden="true" />
                  {proof.viewport}px
                </span>
                <ChevronRight size={14} className={active ? "text-cyan-200" : "text-zinc-600"} aria-hidden="true" />
              </div>
              <ScoreBar label="raw" value={proof.rawScore} tone="raw" />
              <div className="mt-2">
                <ScoreBar label="rumi" value={proof.rumiScore} tone="rumi" />
              </div>
              <p className="mt-3 text-[11px] leading-4 text-zinc-500">{proof.label}</p>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceTimeline({ scenario, selectedLeaf, viewport }: { scenario: Scenario; selectedLeaf: LeafNode; viewport: PrecisionViewport }) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-zinc-100">Design rationale timeline</h2>
        <p className="mt-1 text-xs text-zinc-500">このfixtureを作成した際の設計意図をnode単位で示します。</p>
      </div>
      <ol className="space-y-3">
        {[
          "foundation tokens locked before leaf generation",
          `${selectedLeaf.label} contract rendered at ${viewport}px`,
          ...scenario.timeline,
        ].map((item, index) => (
          <li key={`${item}-${index}`} className="grid grid-cols-[auto_1fr] gap-3 text-xs">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-[11px] font-semibold text-zinc-300">
              {index + 1}
            </span>
            <span className="pt-1 text-zinc-400">{item}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function UiPrecisionComparator() {
  const [selectedScenarioId, setSelectedScenarioId] = useState<ScenarioId>("ai-chat");
  const scenario = useMemo(
    () => scenarioLibrary.find((item) => item.id === selectedScenarioId) ?? scenarioLibrary[0],
    [selectedScenarioId],
  );
  const [request, setRequest] = useState(scenarioLibrary[0].request);
  const [selectedLeafId, setSelectedLeafId] = useState(scenarioLibrary[0].leaves[1].id);
  const [viewport, setViewport] = useState<PrecisionViewport>(1440);
  const selectedLeaf = useMemo(
    () => scenario.leaves.find((leaf) => leaf.id === selectedLeafId) ?? scenario.leaves[0],
    [scenario, selectedLeafId],
  );

  const selectScenario = (id: ScenarioId) => {
    const nextScenario = scenarioLibrary.find((item) => item.id === id) ?? scenarioLibrary[0];
    setSelectedScenarioId(id);
    setSelectedLeafId(nextScenario.leaves[1]?.id ?? nextScenario.leaves[0].id);
    setRequest(nextScenario.request);
  };

  const resetDemo = () => {
    setRequest(scenario.request);
    setSelectedLeafId(scenario.leaves[1]?.id ?? scenario.leaves[0].id);
    setViewport(1440);
  };

  return (
    <div className="min-h-screen overflow-auto bg-[#0a0d10] text-zinc-100">
      <header className="sticky top-0 rumi-layer-panel border-b border-zinc-800 bg-[#0a0d10]/94 px-4 py-3 backdrop-blur">
        <div className="mx-auto grid max-w-[1680px] gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-cyan-400/30 bg-cyan-400/10 text-cyan-200">
              <SplitSquareHorizontal size={18} aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold text-zinc-50">Rumi UI Design Scenario Demo</h1>
              <p className="truncate text-xs text-zinc-500">Static illustrative fixtures / {scenario.label}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:justify-end">
            <div className="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs font-semibold text-zinc-200">
              <CircleDashed size={14} className="text-emerald-300" aria-hidden="true" />
              Static fixtures
            </div>
            <div className="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs font-semibold text-zinc-200">
              <MessageSquare size={14} className="text-cyan-300" aria-hidden="true" />
              {scenario.shortLabel}
            </div>
            <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-1">
              {precisionViewports.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setViewport(item)}
                  className={cn(
                    "h-7 rounded-md px-2.5 text-xs font-semibold transition",
                    viewport === item ? "bg-cyan-400 text-zinc-950" : "text-zinc-400 hover:text-zinc-100",
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={resetDemo}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 transition hover:bg-white"
            >
              <Play size={14} aria-hidden="true" />
              Reset demo view
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1680px] gap-4 px-4 py-4 xl:grid-cols-[315px_minmax(0,1fr)_360px]">
        <section role="note" className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 xl:col-span-3">
          <h2 className="text-sm font-semibold text-amber-100">Static demonstration data</h2>
          <p className="mt-1 text-xs leading-5 text-amber-50/80">These previews, scores, candidates, flags, and timelines are hand-authored examples. This page does not invoke MiMo, Rumi, or any other model, and editing the brief does not recompute the fixtures.</p>
        </section>
        <RequestPanel
          scenarios={scenarioLibrary}
          scenario={scenario}
          request={request}
          onRequestChange={setRequest}
          selectedLeafId={selectedLeaf.id}
          onSelectLeaf={setSelectedLeafId}
          onSelectScenario={selectScenario}
        />
        <div className="flex min-w-0 flex-col gap-4">
          <FairnessLedger request={request} />
          <section className="rounded-xl border border-zinc-800 bg-zinc-950/82 p-4">
            <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <h2 className="text-sm font-semibold text-zinc-100">{scenario.label} static design contract</h2>
                <p className="mt-1 text-xs leading-5 text-zinc-500">{scenario.description}</p>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { icon: Search, label: "split", value: `${scenario.leaves.length} leaves` },
                  { icon: SlidersHorizontal, label: "flags", value: `${gateSummary(scenario.gates).rawFailed} → ${gateSummary(scenario.gates).rumiFailed}` },
                  { icon: Mail, label: "example", value: `${viewport}px` },
                ].map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.label} className="rounded-lg border border-zinc-800 bg-black/25 px-3 py-2">
                      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase text-zinc-500">
                        <Icon size={12} aria-hidden="true" />
                        {item.label}
                      </div>
                      <p className="mt-1 text-xs font-semibold text-zinc-100">{item.value}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
          <div className="grid gap-4 2xl:grid-cols-2">
            <RenderPreviewPanel scenario={scenario} variant="raw" viewport={viewport} />
            <RenderPreviewPanel scenario={scenario} variant="rumi" viewport={viewport} />
          </div>
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
            <CandidateTournament selectedLeaf={selectedLeaf} />
            <EvidenceTimeline scenario={scenario} selectedLeaf={selectedLeaf} viewport={viewport} />
          </div>
          <ProofStrip scenario={scenario} viewport={viewport} onViewportChange={setViewport} />
        </div>
        <InspectorPanel scenario={scenario} selectedLeaf={selectedLeaf} viewport={viewport} />
      </main>
    </div>
  );
}
