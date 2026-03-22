import { useState, useEffect } from 'react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { Activity, Clock, Box, GitMerge, RotateCw, CheckCircle2, XCircle, AlertCircle, PlayCircle, Loader2 } from 'lucide-react';

export function Dashboard() {
  const t = useT();
  const dashboard = useAppStore(state => state.dashboard);
  const isLoading = useAppStore(state => state.isLoading);
  const loadDashboard = useAppStore(state => state.loadDashboard);
  const restartKernel = useAppStore(state => state.restartKernel);
  const showDialog = useAppStore(state => state.showDialog);
  const addToast = useAppStore(state => state.addToast);
  const closeDialog = useAppStore(state => state.closeDialog);
  const [showAllActivities, setShowAllActivities] = useState(false);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('dashboard.loading')}</span>
        </div>
      </div>
    );
  }

  const handleRestartKernel = () => {
    showDialog({
      title: t('dashboard.restart_title'),
      message: t('dashboard.restart_message'),
      confirmText: t('dashboard.restart_button'),
      onConfirm: () => {
        restartKernel();
        closeDialog();
      }
    });
  };

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'kernel_start': return <PlayCircle className="w-4 h-4 text-green-500" />;
      case 'pack_load': return <Box className="w-4 h-4 text-blue-500" />;
      case 'flow_success': return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'flow_fail': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'error': return <AlertCircle className="w-4 h-4 text-red-500" />;
      default: return <Activity className="w-4 h-4 text-text-muted" />;
    }
  };

  const displayedActivities = showAllActivities ? dashboard.activities : dashboard.activities.slice(0, 3);

  return (
    <div className="flex-1 overflow-y-auto p-8 bg-bg-main animate-in fade-in">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-text-main">{t('dashboard.title')}</h1>
          <button 
            onClick={handleRestartKernel}
            className="flex items-center gap-2 px-4 py-2 bg-text-main text-bg-main rounded-md hover:opacity-90 transition-opacity text-sm font-medium"
          >
            <RotateCw className="w-4 h-4" />
            {t('dashboard.restart_kernel')}
          </button>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-bg-card border border-border rounded-xl p-5 shadow-sm">
            <div className="flex items-center gap-3 text-text-muted mb-2">
              <Activity className="w-5 h-5" />
              <span className="text-sm font-medium">{t('dashboard.kernel_status')}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${dashboard.kernelStatus === 'running' ? 'bg-green-500' : dashboard.kernelStatus === 'error' ? 'bg-red-500' : 'bg-yellow-500'}`} />
              <span className="text-xl font-bold text-text-main capitalize">
                {dashboard.kernelStatus === 'running' ? t('dashboard.running') : dashboard.kernelStatus === 'error' ? t('dashboard.error') : t('dashboard.stopped')}
              </span>
            </div>
          </div>
          
          <div className="bg-bg-card border border-border rounded-xl p-5 shadow-sm">
            <div className="flex items-center gap-3 text-text-muted mb-2">
              <Clock className="w-5 h-5" />
              <span className="text-sm font-medium">{t('dashboard.uptime')}</span>
            </div>
            <div className="text-xl font-bold text-text-main">{dashboard.uptime}</div>
          </div>

          <div className="bg-bg-card border border-border rounded-xl p-5 shadow-sm">
            <div className="flex items-center gap-3 text-text-muted mb-2">
              <Box className="w-5 h-5" />
              <span className="text-sm font-medium">{t('dashboard.active_packs')}</span>
            </div>
            <div className="text-xl font-bold text-text-main">{dashboard.activePacks}</div>
          </div>

          <div className="bg-bg-card border border-border rounded-xl p-5 shadow-sm">
            <div className="flex items-center gap-3 text-text-muted mb-2">
              <GitMerge className="w-5 h-5" />
              <span className="text-sm font-medium">{t('dashboard.registered_flows')}</span>
            </div>
            <div className="text-xl font-bold text-text-main">{dashboard.registeredFlows}</div>
          </div>
        </div>

        {/* Activity Timeline */}
        <div className="bg-bg-card border border-border rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-text-main mb-6">{t('dashboard.activity')}</h2>
          {dashboard.activities.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Activity className="mb-3 h-10 w-10 text-text-muted opacity-20" />
              <p className="text-sm text-text-muted">No recent activity</p>
            </div>
          ) : (
            <>
              <div className="space-y-6 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
                {displayedActivities.map((activity) => (
                  <div key={activity.id} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-border bg-bg-card shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm z-10">
                      {getActivityIcon(activity.type)}
                    </div>
                    <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] bg-bg-hover p-4 rounded-lg border border-border shadow-sm">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-text-main text-sm">{activity.message}</span>
                        <span className="text-xs text-text-muted">{activity.timestamp}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              
              {dashboard.activities.length > 3 && (
                <div className="mt-6 text-center">
                  <button 
                    onClick={() => setShowAllActivities(!showAllActivities)}
                    className="text-sm text-text-muted hover:text-text-main transition-colors"
                  >
                    {showAllActivities ? t('dashboard.close') : t('dashboard.show_more')}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
