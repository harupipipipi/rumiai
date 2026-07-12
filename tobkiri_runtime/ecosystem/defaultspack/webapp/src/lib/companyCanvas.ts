import type { ToolPreviewItem } from "../components/ToolPreview";
import type { CompanyChannel, CompanyMessage } from "./api";

function companyAttachmentLooksLikeImage(value?: string) {
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(String(value || ""));
}

export function buildCompanyCanvasPreviews(
  messages: CompanyMessage[],
  channels: CompanyChannel[],
  activeChannelId?: string | null,
): ToolPreviewItem[] {
  const selectedChannelId = activeChannelId || channels[0]?.id || "ops-company";
  const activeChannel = channels.find((channel) => channel.id === selectedChannelId) ?? channels[0] ?? null;
  const visibleMessages = messages.filter((message) => !selectedChannelId || message.channel_id === selectedChannelId);
  return visibleMessages.flatMap((message, messageIndex) => {
    const createdAt = message.created_at ? Date.parse(message.created_at) : Date.now() - messageIndex;
    const items: ToolPreviewItem[] = [];
    const mentionText = (message.mentions ?? []).map((mention) => `@${mention}`).join(", ");

    if (message.handoff) {
      const summary = [
        "# Company Handoff",
        "",
        `- Channel: ${activeChannel?.name || message.channel_id}`,
        `- Sender: ${message.sender_id}`,
        `- Target: ${message.handoff.target_agent_id || "unassigned"}`,
        ...(message.handoff.reason ? [`- Reason: ${message.handoff.reason}`] : []),
        ...(mentionText ? [`- Mentions: ${mentionText}`] : []),
        ...(message.task_ids?.length ? [`- Tasks: ${message.task_ids.join(", ")}`] : []),
        "",
        "## Message",
        "",
        message.content,
      ].join("\n");
      items.push({
        id: `company-handoff-${message.id}`,
        toolStepId: `company-channel-${message.channel_id}`,
        timestamp: createdAt,
        data: {
          type: "file",
          filename: `handoff-${message.id}.md`,
          size: `company handoff · ${activeChannel?.name || message.channel_id}`,
          content: summary,
        },
      });
    }

    (message.attachments ?? []).forEach((attachment, attachmentIndex) => {
      const label = String(attachment.name || attachment.path || attachment.url || `attachment-${attachmentIndex + 1}`);
      const path = typeof attachment.path === "string" ? attachment.path : undefined;
      const url = typeof attachment.url === "string" ? attachment.url : undefined;
      const imageSource = url || path;
      if (companyAttachmentLooksLikeImage(imageSource)) {
        if (url) {
          items.push({
            id: `company-attachment-${message.id}-${attachmentIndex}`,
            toolStepId: `company-channel-${message.channel_id}`,
            timestamp: createdAt + attachmentIndex + 0.01,
            data: { type: "image", url, alt: label, path },
          });
        }
        return;
      }
      items.push({
        id: `company-attachment-${message.id}-${attachmentIndex}`,
        toolStepId: `company-channel-${message.channel_id}`,
        timestamp: createdAt + attachmentIndex + 0.01,
        data: {
          type: "file",
          filename: label,
          size: `company attachment · ${activeChannel?.name || message.channel_id}`,
          url,
          path,
          downloadName: label,
        },
      });
    });

    return items;
  }).sort((left, right) => right.timestamp - left.timestamp);
}
