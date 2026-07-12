import packageMetadata from '../../../package.json';

const importedMetadata = packageMetadata as typeof packageMetadata & {
  default?: { version?: string };
};

export const RUMI_VIEWER_VERSION =
  importedMetadata.version ?? importedMetadata.default?.version ?? 'unknown';

export function ViewerVersionLabel() {
  return (
    <div
      className="pointer-events-none flex shrink-0 select-none justify-end bg-bg-main px-3 pb-2 pt-1 text-[10px] leading-none text-text-muted opacity-45 sm:px-4"
      aria-label={`Rumi Viewer version ${RUMI_VIEWER_VERSION}`}
    >
      Rumi Viewer v{RUMI_VIEWER_VERSION}
    </div>
  );
}
