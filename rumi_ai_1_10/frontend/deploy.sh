#!/usr/bin/env bash
set -euo pipefail

echo "=== Rumi AI — deploy.sh (files 12-15) ==="
echo ""

# ─────────────────────────────────────────────
# 12. src/pages/PackDetail.tsx — トースト追加
# ─────────────────────────────────────────────
echo "[12/15] Patching src/pages/PackDetail.tsx ..."

cat > src/pages/PackDetail.tsx << 'PACKDETAIL_EOF'
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import { Switch } from '@/src/components/ui/Switch';
import { ArrowLeft, Play, Loader2 } from 'lucide-react';

export function PackDetail() {
  const t = useT();
  const { id } = useParams();
  const navigate = useNavigate();
  const packs = useAppStore(state => state.packs);
  const togglePack = useAppStore(state => state.togglePack);
  const addToast = useAppStore(state => state.addToast);
  const [isLoading, setIsLoading] = useState(true);

  const pack = packs.find(p => p.id === id);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 500);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('pack.loading')}</span>
        </div>
      </div>
    );
  }

  if (!pack) {
    return <div className="p-8 text-center text-text-muted">Pack not found</div>;
  }

  const handleToggle = () => {
    const key = pack.enabled ? 'packs.toggle_off' : 'packs.toggle_on';
    togglePack(pack.id);
    addToast(t(key, { name: pack.name }), 'success');
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate('/panel/packs')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <h1 className="text-3xl font-bold tracking-tight text-text-main">{pack.name}</h1>
        <Badge variant="outline">{pack.version}</Badge>
        <Badge variant={pack.type === 'core' ? 'default' : 'secondary'}>{pack.type}</Badge>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm font-medium text-text-muted">{pack.enabled ? t('packs.enabled') : t('packs.disabled')}</span>
          <Switch checked={pack.enabled} onCheckedChange={handleToggle} />
        </div>
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.basic_info')}</h3>
            <p className="text-sm text-text-muted">{pack.description}</p>
          </div>

          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.capabilities')}</h3>
            {pack.capabilities.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <ul className="space-y-3">
                {pack.capabilities.map((cap, i) => (
                  <li key={i} className="flex flex-col gap-1">
                    <span className="text-sm font-medium text-text-main">{cap.name}</span>
                    <span className="text-xs text-text-muted">{cap.description}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.flows')}</h3>
            {pack.flows.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <ul className="space-y-3">
                {pack.flows.map((flow, i) => (
                  <li key={i} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <span className="text-sm font-medium text-text-main">{flow}</span>
                    <Button size="sm" variant="outline" onClick={() => {
                      setTimeout(() => navigate('/panel/flows'), 1000);
                    }}>
                      <Play className="mr-2 h-4 w-4" />
                      {t('pack.run')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-text-main">{t('pack.dependencies')}</h3>
            {pack.dependencies.length === 0 ? (
              <p className="text-sm text-text-muted">{t('pack.none')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {pack.dependencies.map((dep, i) => (
                  <Badge key={i} variant="secondary">{dep}</Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
PACKDETAIL_EOF

echo "  ✓ PackDetail.tsx"

# ─────────────────────────────────────────────
# 13. src/pages/Settings.tsx — トースト追加, テーマ名変更
# ─────────────────────────────────────────────
echo "[13/15] Patching src/pages/Settings.tsx ..."

cat > src/pages/Settings.tsx << 'SETTINGS_EOF'
import { useState, useEffect } from 'react';
import { useAppStore, Theme, ColorMode, AVATAR_OPTIONS } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { Badge } from '@/src/components/ui/Badge';
import { User, Settings as SettingsIcon, Globe, Briefcase, Palette, Moon, Sun, LogIn, Loader2, CheckCircle2, ChevronDown } from 'lucide-react';

export function Settings() {
  const t = useT();
  const profile = useAppStore(state => state.profile);
  const updateProfile = useAppStore(state => state.updateProfile);
  const connectAccount = useAppStore(state => state.connectAccount);
  const version = useAppStore(state => state.version);
  const theme = useAppStore(state => state.theme);
  const setTheme = useAppStore(state => state.setTheme);
  const colorMode = useAppStore(state => state.colorMode);
  const setColorMode = useAppStore(state => state.setColorMode);
  const addToast = useAppStore(state => state.addToast);

  const [activeTab, setActiveTab] = useState<'profile' | 'version'>('profile');
  const [formData, setFormData] = useState(profile);
  const [isConnecting, setIsConnecting] = useState(false);
  const [showAvatarPicker, setShowAvatarPicker] = useState(false);

  useEffect(() => {
    setFormData(profile);
  }, [profile]);

  const handleSave = () => {
    updateProfile(formData);
    addToast(t('settings.saved'), 'success');
  };

  const handleConnect = () => {
    setIsConnecting(true);
    setTimeout(() => {
      connectAccount();
      setIsConnecting(false);
      addToast(t('settings.connect_success'), 'success');
    }, 2000);
  };

  const themes: Theme[] = ['Claude', 'ChatGPT', 'Gemini', 'Rumi'];

  return (
    <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight text-text-main">{t('settings.title')}</h1>
      </div>

      <div className="flex gap-4 border-b border-border pb-4">
        <Button
          variant={activeTab === 'profile' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('profile')}
          className="gap-2"
        >
          <User className="h-4 w-4" /> {t('settings.profile')}
        </Button>
        <Button
          variant={activeTab === 'version' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('version')}
          className="gap-2"
        >
          <SettingsIcon className="h-4 w-4" /> {t('settings.version_tab')}
        </Button>
      </div>

      {activeTab === 'profile' ? (
        <div className="grid gap-6 md:grid-cols-2">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            {/* Rumi Account Card */}
            <Card>
              <CardHeader>
                <CardTitle>{t('settings.rumi_account')}</CardTitle>
                <CardDescription>{t('settings.rumi_account_desc')}</CardDescription>
              </CardHeader>
              <CardContent>
                {profile.connected ? (
                  <div className="flex items-center justify-between rounded-[var(--radius)] border border-border p-4">
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="h-5 w-5 text-green-500" />
                      <div>
                        <p className="text-sm font-medium text-text-main">{profile.username}</p>
                        <p className="text-xs text-text-muted">{t('settings.connected')}</p>
                      </div>
                    </div>
                    <Button variant="outline" size="sm">{t('settings.reconnect')}</Button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-4 py-6">
                    <LogIn className="h-12 w-12 text-text-muted opacity-30" />
                    <p className="text-sm text-text-muted text-center">{t('settings.login_required')}</p>
                    <Button onClick={handleConnect} disabled={isConnecting}>
                      {isConnecting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {isConnecting ? t('settings.connecting') : t('settings.connect')}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Profile Card  connected only */}
            {profile.connected && (
              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.basic_info')}</CardTitle>
                  <CardDescription>{t('settings.basic_info_desc')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Avatar  button to expand picker */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-text-main">{t('settings.select_icon')}</label>
                    <div className="flex items-center gap-4">
                      <img
                        src={formData.avatar}
                        alt=""
                        className="h-16 w-16 rounded-full object-cover border border-border"
                        referrerPolicy="no-referrer"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowAvatarPicker(!showAvatarPicker)}
                        className="gap-1"
                      >
                        {t('settings.change_icon')}
                        <ChevronDown className={cn("h-3 w-3 transition-transform", showAvatarPicker && "rotate-180")} />
                      </Button>
                    </div>
                    {showAvatarPicker && (
                      <div className="flex gap-3 mt-2 p-3 border border-border rounded-lg bg-bg-main animate-in fade-in slide-in-from-top-2">
                        {AVATAR_OPTIONS.map((av) => (
                          <button
                            key={av}
                            onClick={() => {
                              setFormData({ ...formData, avatar: av });
                              setShowAvatarPicker(false);
                            }}
                            className={cn(
                              "rounded-full border-2 p-0.5 transition-all",
                              formData.avatar === av
                                ? "border-accent scale-110 shadow-md"
                                : "border-transparent opacity-60 hover:opacity-100"
                            )}
                          >
                            <img
                              src={av}
                              alt=""
                              className="h-12 w-12 rounded-full object-cover"
                              referrerPolicy="no-referrer"
                            />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Username */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-text-main">{t('settings.username')}</label>
                    <Input
                      value={formData.username}
                      onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    />
                  </div>

                  {/* Language  10 languages */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-text-main flex items-center gap-2">
                      <Globe className="h-4 w-4" /> {t('settings.language')}
                    </label>
                    <select
                      className="flex h-10 w-full rounded-[var(--radius)] border border-border bg-bg-main px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                    >
                      <option value="en">English</option>
                      <option value="ja">日本語</option>
                      <option value="zh">中文</option>
                      <option value="ko">한국어</option>
                      <option value="es">Español</option>
                      <option value="fr">Français</option>
                      <option value="de">Deutsch</option>
                      <option value="pt">Português</option>
                      <option value="ru">Русский</option>
                      <option value="ar">العربية</option>
                    </select>
                  </div>

                  {/* Job */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-text-main flex items-center gap-2">
                      <Briefcase className="h-4 w-4" /> {t('settings.job')}
                    </label>
                    <Input
                      value={formData.job}
                      onChange={(e) => setFormData({ ...formData, job: e.target.value })}
                    />
                  </div>

                  <Button onClick={handleSave} className="w-full mt-4">{t('settings.save')}</Button>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-6">
            {/* Theme Card */}
            <Card>
              <CardHeader>
                <CardTitle>{t('settings.theme')}</CardTitle>
                <CardDescription>{t('settings.theme_desc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-3">
                  <label className="text-sm font-medium text-text-main">{t('settings.color_mode')}</label>
                  <div className="grid grid-cols-2 gap-4">
                    <Button
                      variant={colorMode === 'light' ? 'default' : 'outline'}
                      className="justify-start gap-2"
                      onClick={() => {
                        setColorMode('light');
                      }}
                    >
                      <Sun className="h-4 w-4" /> Light
                    </Button>
                    <Button
                      variant={colorMode === 'dark' ? 'default' : 'outline'}
                      className="justify-start gap-2"
                      onClick={() => {
                        setColorMode('dark');
                      }}
                    >
                      <Moon className="h-4 w-4" /> Dark
                    </Button>
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-medium text-text-main">{t('settings.style_theme')}</label>
                  <div className="grid grid-cols-2 gap-4">
                    {themes.map((th) => (
                      <Button
                        key={th}
                        variant={theme === th ? 'default' : 'outline'}
                        className="justify-start gap-2"
                        onClick={() => {
                          setTheme(th);
                        }}
                      >
                        <Palette className="h-4 w-4" /> {th}
                      </Button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{t('settings.version')}</CardTitle>
            <CardDescription>{t('settings.version_desc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              {[
                ['App Version', version.app],
                ['Kernel Version', version.kernel],
                ['Python Version', version.python],
                ['Launcher Version', version.launcher],
              ].map(([label, val]) => (
                <div key={label} className="flex items-center justify-between rounded-[var(--radius)] border border-border p-4">
                  <span className="text-sm font-medium text-text-main">{label}</span>
                  <Badge variant="secondary">{val}</Badge>
                </div>
              ))}
              <div className="flex items-center justify-between rounded-[var(--radius)] border border-border p-4">
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-text-main">Docker</span>
                  <span className="text-xs text-text-muted">{version.docker.type}</span>
                </div>
                <Badge variant={version.docker.installed ? 'secondary' : 'destructive'}>
                  {version.docker.installed ? version.docker.version : t('settings.not_installed')}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
SETTINGS_EOF

echo "  ✓ Settings.tsx"

# ─────────────────────────────────────────────
# 14. src/components/layout/Sidebar.tsx — テーマ名マップ化
# ─────────────────────────────────────────────
echo "[14/15] Patching src/components/layout/Sidebar.tsx ..."

cat > src/components/layout/Sidebar.tsx << 'SIDEBAR_EOF'
import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { Folder, LayoutGrid, Settings, PanelLeft, Home } from 'lucide-react';

export function Sidebar() {
  const t = useT();
  const location = useLocation();
  const profile = useAppStore(state => state.profile);
  const theme = useAppStore(state => state.theme);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  const links = [
    { to: '/panel', icon: Home, label: t('nav.home') },
    { to: '/panel/packs', icon: Folder, label: t('nav.packs') },
    { to: '/panel/flows', icon: LayoutGrid, label: t('nav.flows') },
    { to: '/panel/settings', icon: Settings, label: t('nav.settings') },
  ];

  const themeLogoStyles: Record<string, string> = {
    Claude: 'font-medium text-lg tracking-wide',
    ChatGPT: 'font-serif text-lg font-medium tracking-wide',
    Gemini: 'text-xl font-medium',
    Rumi: 'font-bold text-lg tracking-wide',
  };

  const logoText = theme === 'Rumi' ? 'Rumi AI' : 'Rumi';
  const logoStyle = themeLogoStyles[theme] || themeLogoStyles.Rumi;

  return (
    <aside
      className={cn(
        "flex-shrink-0 flex flex-col bg-bg-sidebar border-r border-border transition-all duration-300 overflow-hidden",
        isSidebarOpen ? "w-[260px]" : "w-0 border-r-0"
      )}
    >
      {/* Logo Area */}
      <div className="p-3 flex items-center justify-between">
        <div className="flex items-center gap-2 px-2">
          <span className={cn(logoStyle, "text-text-main")}>{logoText}</span>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-1.5 hover:bg-bg-hover rounded-md text-text-muted transition-colors"
          title="Close sidebar"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation Links */}
      <div className="px-3 py-2 space-y-1 mt-2 flex-1 overflow-y-auto">
        {links.map((link: any) => {
          const isActive = location.pathname === link.to || (link.to !== '/panel' && location.pathname.startsWith(link.to));
          return (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors font-medium text-sm",
                isActive ? "bg-accent text-accent-fg shadow-sm" : "text-text-muted hover:bg-bg-hover hover:text-text-main"
              )}
            >
              <link.icon className="w-5 h-5" /> {link.label}
            </Link>
          );
        })}
      </div>

      {/* Profile Area */}
      <div className="p-3 border-t border-border mt-auto">
        <Link to="/panel/settings" className="w-full flex items-center justify-between hover:bg-bg-hover p-2 rounded-lg transition-colors">
          <div className="flex items-center gap-3">
            {profile.avatar ? (
              <img src={profile.avatar} alt="User" className="w-8 h-8 rounded-full object-cover border border-border" referrerPolicy="no-referrer" />
            ) : (
              <div className="w-8 h-8 rounded-full bg-gradient-to-r from-green-400 to-blue-500 flex items-center justify-center text-white font-bold text-sm">
                {profile.username.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="text-left leading-tight">
              <div className="text-[13px] font-medium text-text-main">{profile.username}</div>
              <div className="text-[11px] text-text-muted">{t('nav.admin')}</div>
            </div>
          </div>
          <Settings className="w-4 h-4 text-text-muted" />
        </Link>
      </div>
    </aside>
  );
}
SIDEBAR_EOF

echo "  ✓ Sidebar.tsx"

# ─────────────────────────────────────────────
# 15. src/pages/Flows.tsx — 全面リファクタリング
# ─────────────────────────────────────────────
echo "[15/15] Patching src/pages/Flows.tsx ..."

cat > src/pages/Flows.tsx << 'FLOWS_EOF'
/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { Plus, Play, Save, Trash2, FileText, CheckCircle2, Clock, Workflow, X, Box, Loader2 } from 'lucide-react';
import CodeMirror from '@uiw/react-codemirror';
import { yaml } from '@codemirror/lang-yaml';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  SelectionMode,
} from '@xyflow/react';
import type { Node, Edge, ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { nodeTypes } from '@/src/components/flow/CustomNodes';
import { nodesToYaml, yamlToNodes } from '@/src/lib/flowUtils';
import { useFlowHistory } from '@/src/hooks/useFlowHistory';
import { useFlowExecution } from '@/src/hooks/useFlowExecution';
import { useFlowKeyboard } from '@/src/hooks/useFlowKeyboard';
import { useFlowDragDrop } from '@/src/hooks/useFlowDragDrop';
import { useFlowEditor } from '@/src/hooks/useFlowEditor';
import type { AvailableStep } from '@/src/lib/types';

const AVAILABLE_STEPS: AvailableStep[] = [
  { id: 'mounts.init', name: 'mounts.init', pack: 'core', description: 'Initialize mounts' },
  { id: 'registry.load', name: 'registry.load', pack: 'core', description: 'Load registry' },
  { id: 'check_profile', name: 'check_profile', pack: 'utils', description: 'Check user profile' },
  { id: 'emit', name: 'emit', pack: 'core', description: 'Emit an event' },
  { id: 'exec_py', name: 'exec_py', pack: 'python', description: 'Execute Python script' },
  { id: 'http.get', name: 'http.get', pack: 'network', description: 'Make an HTTP GET request' },
  { id: 'http.post', name: 'http.post', pack: 'network', description: 'Make an HTTP POST request' },
  { id: 'log.info', name: 'log.info', pack: 'utils', description: 'Log info message' },
];

/** Inner component that has access to ReactFlow hooks via provider */
function FlowEditorInner() {
  const t = useT();
  const flows = useAppStore(state => state.flows);
  const addFlow = useAppStore(state => state.addFlow);
  const updateFlow = useAppStore(state => state.updateFlow);
  const deleteFlow = useAppStore(state => state.deleteFlow);
  const showDialog = useAppStore(state => state.showDialog);
  const addToast = useAppStore(state => state.addToast);
  const colorMode = useAppStore(state => state.colorMode);

  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(flows[0]?.id || null);
  const [isCreating, setIsCreating] = useState(false);
  const [newFlowName, setNewFlowName] = useState('');
  const [activeTab, setActiveTab] = useState<'yaml' | 'result'>('yaml');
  const [selectedPack, setSelectedPack] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(true);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  const selectedFlow = flows.find(f => f.id === selectedFlowId);
  const packs = ['all', ...Array.from(new Set(AVAILABLE_STEPS.map(s => s.pack)))];
  const filteredSteps = selectedPack === 'all' ? AVAILABLE_STEPS : AVAILABLE_STEPS.filter(s => s.pack === selectedPack);

  // Custom hooks
  const history = useFlowHistory(nodes, edges, setNodes, setEdges);
  const execution = useFlowExecution(nodes, setNodes);

  // Break circular dep: keyboard needs setMenuPos, editor needs pressedKeys
  const menuPosRef = useRef<((pos: { x: number; y: number } | null) => void) | null>(null);

  const keyboard = useFlowKeyboard({
    nodes,
    setNodes,
    saveHistory: history.saveHistory,
    undo: history.undo,
    redo: history.redo,
    execute: execution.execute,
    reactFlowInstance,
    setMenuPos: (pos) => { menuPosRef.current?.(pos); },
  });

  const editorHook = useFlowEditor({
    nodes,
    setNodes,
    edges,
    setEdges,
    saveHistory: history.saveHistory,
    reactFlowInstance,
    pressedKeys: keyboard.pressedKeys,
  });

  // Wire up the ref after editorHook is created
  menuPosRef.current = editorHook.setMenuPos;

  const dragDrop = useFlowDragDrop({
    nodes,
    setNodes,
    setEdges,
    saveHistory: history.saveHistory,
    reactFlowInstance,
    reactFlowWrapper,
  });

  // Pointer tracking
  useEffect(() => {
    return dragDrop.setupPointerTracking();
  }, [dragDrop.setupPointerTracking]);

  // Loading
  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 700);
    return () => clearTimeout(timer);
  }, []);

  // Load flow data
  useEffect(() => {
    if (selectedFlowId && selectedFlow) {
      const { nodes: newNodes, edges: newEdges } = yamlToNodes(selectedFlow.content);
      setNodes(newNodes);
      setEdges(newEdges);
      editorHook.setSelectedNode(null);
      execution.clearResult();
    }
  }, [selectedFlowId]);

  const handleSelectFlow = (id: string) => {
    setSelectedFlowId(id);
    setIsCreating(false);
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setSelectedFlowId(null);
    setNewFlowName('');
    execution.clearResult();

    // M-5: Include Trigger + End node in new flow
    setNodes([
      { id: 'trigger-1', type: 'trigger', position: { x: 250, y: 50 }, data: { type: 'on_setup' } },
      { id: 'end-1', type: 'end', position: { x: 250, y: 150 }, data: {} },
    ]);
    setEdges([
      { id: 'e-trigger-1-end-1', source: 'trigger-1', target: 'end-1', animated: true },
    ]);
  };

  const handleSave = () => {
    const generatedYaml = nodesToYaml(nodes, edges);

    if (isCreating) {
      if (!newFlowName.trim()) {
        addToast(t('flows.name_required'), 'error');
        return;
      }
      const newId = Math.random().toString(36).substring(2, 9);
      addFlow({ id: newId, name: newFlowName.endsWith('.yaml') ? newFlowName : `${newFlowName}.yaml`, content: generatedYaml });
      setSelectedFlowId(newId);
      setIsCreating(false);
      addToast(t('flows.created'), 'success');
    } else if (selectedFlowId) {
      updateFlow(selectedFlowId, generatedYaml);
      addToast(t('flows.saved'), 'success');
    }
  };

  const handleDelete = () => {
    if (!selectedFlowId) return;
    showDialog({
      title: t('flows.delete_title'),
      message: t('flows.delete_message'),
      confirmText: t('flows.delete_confirm'),
      onConfirm: () => {
        deleteFlow(selectedFlowId);
        setSelectedFlowId(null);
        setNodes([]);
        setEdges([]);
        addToast(t('flows.deleted'), 'success');
      },
    });
  };

  const handleExecute = async () => {
    if (!selectedFlowId) return;
    setActiveTab('result');
    const result = await execution.execute();
    if (result) {
      addToast(t('flows.executed'), result.status === 'success' ? 'success' : 'error');
    }
  };

  const onDragStart = (event: React.DragEvent, nodeType: string, stepId: string) => {
    const ghost = new Image();
    ghost.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
    event.dataTransfer.setDragImage(ghost, 0, 0);
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('stepId', stepId);
    event.dataTransfer.effectAllowed = 'move';
  };

  const handleStepMiddleClick = useCallback(
    (event: React.MouseEvent, step: AvailableStep) => {
      if (event.button !== 1) return;
      event.preventDefault();
      if (!reactFlowInstance) return;

      const wrapper = reactFlowWrapper.current;
      if (!wrapper) return;
      const bounds = wrapper.getBoundingClientRect();

      const position = reactFlowInstance.screenToFlowPosition({
        x: bounds.left + bounds.width / 2,
        y: bounds.top + bounds.height / 2,
      });

      history.saveHistory();
      setNodes(nds =>
        nds.concat({
          id: `step-${Date.now()}`,
          type: 'step',
          position,
          data: { id: step.id, type: 'action' },
        })
      );
    },
    [reactFlowInstance, history.saveHistory, setNodes]
  );

  const generatedYaml = nodesToYaml(nodes, edges);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('flows.loading')}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full p-8 flex gap-6 animate-in fade-in slide-in-from-bottom-4">
      {/* Left Pane: Flow List */}
      <div className="flex w-64 flex-col gap-4 rounded-xl border border-border bg-bg-card p-4 shadow-sm shrink-0">
        <Button size="sm" onClick={handleCreateNew} variant={isCreating ? 'default' : 'outline'} className="w-full">
          <Plus className="mr-2 h-4 w-4" />
          {t('flows.new')}
        </Button>
        <div className="flex flex-col gap-2 overflow-y-auto mt-2">
          {flows.map(flow => (
            <div
              key={flow.id}
              onClick={() => handleSelectFlow(flow.id)}
              className={`flex cursor-pointer items-center gap-3 rounded-lg p-3 transition-colors ${selectedFlowId === flow.id && !isCreating ? 'bg-accent text-accent-fg' : 'hover:bg-bg-hover text-text-main'}`}
            >
              <FileText className="h-4 w-4 shrink-0" />
              <span className="truncate text-sm font-medium">{flow.name}</span>
            </div>
          ))}
          {flows.length === 0 && !isCreating && (
            <div className="p-4 text-center text-sm text-text-muted">{t('flows.no_flows')}</div>
          )}
        </div>
      </div>

      {/* Right Pane: Editor */}
      <div className="flex flex-1 flex-col gap-4 rounded-xl border border-border bg-bg-card p-4 shadow-sm overflow-hidden relative">
        {isCreating || selectedFlowId ? (
          <>
            {/* Header */}
            <div className="flex items-center justify-between shrink-0">
              {isCreating ? (
                <Input
                  placeholder={t('flows.name_placeholder')}
                  value={newFlowName}
                  onChange={(e) => setNewFlowName(e.target.value)}
                  className="max-w-xs"
                />
              ) : (
                <h2 className="text-xl font-bold text-text-main">{selectedFlow?.name}</h2>
              )}
              <div className="flex items-center gap-2">
                {!isCreating && (
                  <Button variant="outline" onClick={handleExecute} disabled={execution.isExecuting} className="gap-2">
                    <Play className="h-4 w-4" />
                    {t('flows.execute')}
                  </Button>
                )}
                <Button variant="outline" onClick={handleSave} className="gap-2">
                  <Save className="h-4 w-4" />
                  {t('flows.save')}
                </Button>
                {!isCreating && (
                  <Button variant="destructive" onClick={handleDelete} className="gap-2">
                    <Trash2 className="h-4 w-4" />
                    {t('flows.delete')}
                  </Button>
                )}
              </div>
            </div>

            {/* Block Bar */}
            <div className="flex items-center gap-4 p-2 border border-border rounded-md bg-bg-main shrink-0">
              <select
                value={selectedPack}
                onChange={(e) => setSelectedPack(e.target.value)}
                className="h-8 rounded-md border border-border bg-bg-card px-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {packs.map(p => <option key={p} value={p}>{p === 'all' ? 'All Packs' : p}</option>)}
              </select>
              <div className="flex-1 overflow-x-auto flex gap-2 pb-1 items-center scrollbar-thin">
                {filteredSteps.map(step => (
                  <div
                    key={step.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-card border border-border rounded-full text-xs font-medium cursor-grab hover:border-accent hover:text-accent transition-colors shrink-0 shadow-sm"
                    draggable
                    onDragStart={(e) => onDragStart(e, 'step', step.id)}
                    onMouseDown={(e) => handleStepMiddleClick(e, step)}
                    onAuxClick={(e) => e.preventDefault()}
                    title={`${step.description} (Pack: ${step.pack})`}
                  >
                    <Box className="w-3.5 h-3.5" />
                    {step.name}
                  </div>
                ))}
              </div>
            </div>

            {/* Main Area: Node Editor */}
            <div ref={reactFlowWrapper} className={`flex-1 relative border border-border rounded-md overflow-hidden ${colorMode === 'dark' ? 'bg-[#1a1a1a]' : 'bg-gray-50'}`}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={editorHook.onConnect}
                onNodeClick={editorHook.onNodeClick}
                onNodeDragStart={dragDrop.onNodeDragStart}
                onNodeDrag={dragDrop.onNodeDrag}
                onNodeDragStop={dragDrop.onNodeDragStop}
                onPaneClick={editorHook.onPaneClick}
                onPaneContextMenu={editorHook.onPaneContextMenu}
                onConnectEnd={editorHook.onConnectEnd}
                onEdgeClick={editorHook.onEdgeClick}
                onReconnect={editorHook.onReconnect}
                onEdgeDoubleClick={editorHook.onEdgeDoubleClick}
                onNodesDelete={editorHook.onNodesDelete}
                onEdgesDelete={editorHook.onEdgesDelete}
                onInit={setReactFlowInstance}
                onDrop={dragDrop.onDrop}
                onDragOver={dragDrop.onDragOver}
                nodeTypes={nodeTypes}
                panOnDrag={[1, 2]}
                selectionOnDrag={true}
                selectionMode={SelectionMode.Partial}
                fitView
                className={colorMode === 'dark' ? 'bg-[#1a1a1a]' : 'bg-gray-50'}
              >
                <Background color={colorMode === 'dark' ? '#333' : '#ccc'} gap={16} />
                <Controls className="bg-bg-card border-border fill-text-main" />
              </ReactFlow>

              {/* Delete Drop Zone */}
              <div
                className={cn(
                  "absolute bottom-0 left-0 right-0 flex items-center justify-center z-50 pointer-events-none border-t-2 border-dashed transition-all duration-200",
                  dragDrop.isDraggingNode ? "h-20 opacity-100" : "h-0 opacity-0",
                  dragDrop.isOverDeleteZone
                    ? "bg-red-500/30 border-red-500 backdrop-blur-sm"
                    : "bg-red-500/10 border-red-400/50"
                )}
              >
                <div
                  className={cn(
                    "flex items-center gap-2 font-medium text-sm transition-transform duration-150",
                    dragDrop.isOverDeleteZone ? "text-red-300 scale-110" : "text-red-400"
                  )}
                >
                  <Trash2 className="w-5 h-5" />
                  {dragDrop.isOverDeleteZone ? t('flows.release_to_delete') : t('flows.drop_to_delete')}
                </div>
              </div>

              {/* Context Menu */}
              {editorHook.menuPos && (
                <div
                  className="fixed z-50 bg-bg-card border border-border shadow-xl rounded-lg w-64 p-2 flex flex-col"
                  style={{ top: editorHook.menuPos.y, left: editorHook.menuPos.x }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-text-muted px-1">Add Node</span>
                    <button onClick={() => editorHook.setMenuPos(null)} className="text-text-muted hover:text-text-main"><X className="w-3 h-3" /></button>
                  </div>
                  <Input
                    autoFocus
                    placeholder="Search nodes..."
                    value={editorHook.menuFilter}
                    onChange={(e) => editorHook.setMenuFilter(e.target.value)}
                    className="mb-2 h-8 text-sm"
                  />
                  <div className="max-h-64 overflow-y-auto flex flex-col gap-1 scrollbar-thin">
                    {AVAILABLE_STEPS.filter(s => s.name.toLowerCase().includes(editorHook.menuFilter.toLowerCase()) || s.description.toLowerCase().includes(editorHook.menuFilter.toLowerCase())).map(step => (
                      <div
                        key={step.id}
                        className="px-2 py-1.5 hover:bg-bg-hover cursor-pointer text-sm rounded flex flex-col"
                        onClick={() => editorHook.handleAddNodeFromMenu(step)}
                      >
                        <span className="font-medium">{step.name}</span>
                        <span className="text-[10px] text-text-muted">{step.description}</span>
                      </div>
                    ))}
                    {['Branch', 'Sequence', 'Delay', 'Multigate', 'Comment'].filter(n => n.toLowerCase().includes(editorHook.menuFilter.toLowerCase())).map(name => (
                      <div
                        key={name}
                        className="px-2 py-1.5 hover:bg-bg-hover cursor-pointer text-sm rounded flex flex-col border-t border-border mt-1"
                        onClick={() => editorHook.handleAddNodeFromMenu({ id: name.toLowerCase(), name, description: `Basic ${name} node` })}
                      >
                        <span className="font-medium text-accent">{name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Property Panel */}
              {editorHook.selectedNode && (
                <div className="absolute top-4 right-4 w-64 bg-bg-card border border-border rounded-lg shadow-lg z-10 flex flex-col">
                  <div className="flex items-center justify-between p-3 border-b border-border">
                    <h3 className="font-semibold text-sm">{t('flows.properties')}</h3>
                    <button onClick={() => editorHook.setSelectedNode(null)} className="text-text-muted hover:text-text-main">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="p-4 flex flex-col gap-4">
                    {editorHook.selectedNode.type === 'trigger' && (
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-text-muted">Trigger Type</label>
                        <Input
                          value={(editorHook.selectedNode.data.type as string) || ''}
                          onChange={(e) => editorHook.updateNodeData('type', e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                    )}
                    {editorHook.selectedNode.type === 'step' && (
                      <>
                        <div className="space-y-2">
                          <label className="text-xs font-medium text-text-muted">Step ID</label>
                          <Input
                            value={(editorHook.selectedNode.data.id as string) || ''}
                            onChange={(e) => editorHook.updateNodeData('id', e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="text-xs font-medium text-text-muted">Step Type</label>
                          <Input
                            value={(editorHook.selectedNode.data.type as string) || ''}
                            onChange={(e) => editorHook.updateNodeData('type', e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                      </>
                    )}
                    {editorHook.selectedNode.type === 'end' && (
                      <div className="text-sm text-text-muted">End Node</div>
                    )}

                    <Button variant="destructive" size="sm" onClick={editorHook.deleteSelectedNode} className="mt-2">
                      <Trash2 className="w-4 h-4 mr-2" /> {t('flows.delete_node')}
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Area: Tabs */}
            <div className="h-48 shrink-0 flex flex-col border border-border rounded-md overflow-hidden bg-bg-main">
              <div className="flex border-b border-border bg-bg-card">
                <button
                  className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'yaml' ? 'border-b-2 border-accent text-text-main' : 'text-text-muted hover:text-text-main'}`}
                  onClick={() => setActiveTab('yaml')}
                >
                  {t('flows.yaml')}
                </button>
                <button
                  className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'result' ? 'border-b-2 border-accent text-text-main' : 'text-text-muted hover:text-text-main'}`}
                  onClick={() => setActiveTab('result')}
                >
                  {t('flows.result')}
                </button>
              </div>
              <div className="flex-1 overflow-auto">
                {activeTab === 'yaml' && (
                  <CodeMirror
                    value={generatedYaml}
                    height="100%"
                    extensions={[yaml()]}
                    theme={colorMode === 'dark' ? 'dark' : 'light'}
                    readOnly
                    className="h-full text-sm"
                  />
                )}
                {activeTab === 'result' && (
                  <div className="p-4">
                    {execution.isExecuting ? (
                      <div className="flex items-center justify-center h-full text-text-muted">
                        <Clock className="w-4 h-4 mr-2 animate-spin" /> {t('flows.executing')}
                      </div>
                    ) : execution.executionResult ? (
                      <div className="flex flex-col gap-2">
                        {execution.executionResult.steps.map((step, i) => (
                          <div key={i} className="flex items-center justify-between rounded border border-border bg-bg-card p-2 text-sm">
                            <div className="flex items-center gap-2">
                              {step.status === 'success' ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <X className="w-4 h-4 text-red-500" />}
                              <span className="font-medium text-text-main">{step.name}</span>
                            </div>
                            <div className="flex items-center gap-2 text-text-muted">
                              <Clock className="h-3 w-3" />
                              <span>{step.duration}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full text-text-muted text-sm">
                        {t('flows.no_result')}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full flex-col items-center justify-center text-center relative overflow-hidden rounded-[var(--radius)]">
            <div className="absolute inset-0 opacity-5">
              <img src="https://picsum.photos/seed/flow/800/600" alt="Flow Background" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
            </div>
            <div className="relative z-10 flex flex-col items-center">
              <Workflow className="mb-4 h-16 w-16 text-accent opacity-80" />
              <h3 className="text-xl font-bold text-text-main mb-2">{t('flows.title')}</h3>
              <p className="text-sm text-text-muted max-w-sm">
                {t('flows.subtitle')}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// H-7: ReactFlowProvider wraps the entire component
export function Flows() {
  return (
    <ReactFlowProvider>
      <FlowEditorInner />
    </ReactFlowProvider>
  );
}
FLOWS_EOF

echo "  ✓ Flows.tsx"

# ─────────────────────────────────────────────
echo ""
echo "=== All 4 files patched successfully ==="
echo ""
echo "  12. src/pages/PackDetail.tsx"
echo "  13. src/pages/Settings.tsx"
echo "  14. src/components/layout/Sidebar.tsx"
echo "  15. src/pages/Flows.tsx"
echo ""
