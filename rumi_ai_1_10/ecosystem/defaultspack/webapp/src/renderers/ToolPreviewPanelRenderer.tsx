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
    <div className="w-[min(50vw,720px)] min-w-[420px] flex-shrink-0 h-full max-[1100px]:w-[420px] max-[900px]:hidden">
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
