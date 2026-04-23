import { Navigate, useLocation } from 'react-router-dom';
import { panelRoutes } from '@/src/lib/routes';

export function StartupProfiles() {
  const location = useLocation();
  return <Navigate to={`${panelRoutes.home}${location.search}${location.hash}`} replace />;
}
