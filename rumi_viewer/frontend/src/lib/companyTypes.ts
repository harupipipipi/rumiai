/**
 * Company Channel types for multi-agent collaboration.
 * Shared internal channel where agents coordinate via mentions and file handoffs.
 */

export interface CompanyChannelMessage {
  id: string;
  channelId: string;
  senderId: string;          // agent or user id
  senderName: string;
  senderAvatar?: string;
  content: string;
  mentions: string[];        // @agent-id list, e.g. ["@coding_engineer", "@reviewer"]
  attachments: MessageAttachment[];
  replyTo?: string;          // parent message id for threading
  timestamp: number;         // epoch ms
  status: 'sent' | 'delivered' | 'read' | 'failed';
}

export interface MessageAttachment {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  /** Workspace-relative path if it's a workspace file handoff */
  workspacePath?: string;
  /** Inline base64 for small payloads (<64KB) */
  inlineData?: string;
}

export interface CompanyChannel {
  id: string;
  name: string;
  description: string;
  members: ChannelMember[];
  createdAt: number;
  lastActivityAt: number;
  pinned: boolean;
}

export interface ChannelMember {
  id: string;
  name: string;
  role: 'agent' | 'user' | 'admin';
  avatar?: string;
  online: boolean;
}

export interface AgentMention {
  agentId: string;
  agentName: string;
  messageId: string;
  channelId: string;
  acknowledged: boolean;
  timestamp: number;
}
