import { PanelRouter } from '@/src/app/PanelRouter';
import { usePanelBootstrap } from '@/src/app/usePanelBootstrap';
import { useAppStore } from '@/src/store';

export default function App() {
  usePanelBootstrap();
  const isSetupDone = useAppStore(state => state.isSetupDone);

  return <PanelRouter isSetupDone={isSetupDone} />;
}
