import { ToolPreviewPanel } from "../components/ToolPreview";
import type { ToolPreviewPanelRendererProps } from "./types";

export function ToolPreviewPanelRenderer({
  previews,
  showPreview,
  previewMode,
  activePreviewId,
  memo,
  onClose,
  onModeChange,
  onMemoChange,
}: ToolPreviewPanelRendererProps) {
  return (
    <div className="h-full w-[clamp(300px,28vw,380px)] flex-shrink-0 max-[1050px]:w-[300px] max-[900px]:w-full rumi-anim-fade-right">
      <ToolPreviewPanel
        previews={previews}
        isVisible={showPreview}
        onClose={onClose}
        mode={previewMode}
        onModeChange={onModeChange}
        activePreviewId={activePreviewId}
        memo={memo}
        onMemoChange={onMemoChange}
      />
    </div>
  );
}
