import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '@/src/store';
import { PanelLeft } from 'lucide-react';

export function Layout() {
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);

  if (!isSetupDone) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg-main text-text-main transition-colors duration-200 font-sans">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col relative overflow-hidden">
          {!isSidebarOpen && (
            <div className="absolute top-3 left-3 z-50">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-2 hover:bg-bg-hover rounded-md text-text-muted transition-colors bg-bg-main border border-border shadow-sm"
              >
                <PanelLeft className="w-5 h-5" />
              </button>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
