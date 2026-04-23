import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';

export function Layout() {
  const isSetupDone = useAppStore(state => state.isSetupDone);

  if (!isSetupDone) {
    return <Navigate to={panelRoutes.setup} replace />;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg-main text-text-main transition-colors duration-200 font-sans">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col relative overflow-hidden scrollbar-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
