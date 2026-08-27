import {
  ChatStreamInterruptedError,
  api,
  type ChatStreamHandlers,
  type Conversation,
  type SendMessageOptions,
} from "../../../lib/api";

export { ChatStreamInterruptedError };

export const sideChatResources = {
  createConversation(options: Parameters<typeof api.createConversation>[0]) {
    return api.createConversation(options);
  },
  getConversation(conversationId: string): Promise<Conversation> {
    return api.getConversation(conversationId);
  },
  streamMessage(
    conversationId: string,
    text: string,
    options: SendMessageOptions,
    handlers: ChatStreamHandlers,
  ) {
    return api.streamMessage(conversationId, text, options, handlers);
  },
  stopMessage(conversationId: string) {
    return api.stopMessage(conversationId);
  },
  readWorkspaceFile(
    path: string,
    options?: Parameters<typeof api.readWorkspaceFile>[1],
  ) {
    return api.readWorkspaceFile(path, options);
  },
};
