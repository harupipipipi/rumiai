import { ToolPreviewPanel } from "../components/ToolPreview";
import type { ToolPreviewPanelRendererProps } from "./types";

export function ToolPreviewPanelRenderer({
  previews,
  showPreview,
  previewMode,
  activePreviewId,
  onClose,
  onModeChange,
}: ToolPreviewPanelRendererProps) {
  return (
    <div className="w-[380px] flex-shrink-0 h-full">
      <ToolPreviewPanel
        previews={previews}
        isVisible={showPreview}
        onClose={onClose}
        mode={previewMode}
        onModeChange={onModeChange}
        activePreviewId={activePreviewId}
      />
    </div>
  );
}
