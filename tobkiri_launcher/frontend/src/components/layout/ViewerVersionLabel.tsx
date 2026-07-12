import packageMetadata from '../../../package.json';
import { LAUNCHER_DISPLAY_NAME } from '@/src/lib/launcherBrand';

export const RUMI_VIEWER_VERSION = packageMetadata.version;

export function ViewerVersionLabel() {
  return (
    <div
      className="pointer-events-none flex shrink-0 select-none justify-end bg-bg-main px-3 pb-2 pt-1 text-[10px] leading-none text-text-muted opacity-45 sm:px-4"
      aria-label={`${LAUNCHER_DISPLAY_NAME} version ${RUMI_VIEWER_VERSION}`}
    >
      {LAUNCHER_DISPLAY_NAME} v{RUMI_VIEWER_VERSION}
    </div>
  );
}
