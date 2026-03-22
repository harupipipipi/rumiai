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

  const themes: Theme[] = ['Rumi', 'Minimal', 'Standard', 'Rounded'];

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
