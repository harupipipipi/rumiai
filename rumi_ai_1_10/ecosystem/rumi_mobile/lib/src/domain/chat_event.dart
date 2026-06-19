import 'conversation_locator.dart';

sealed class ChatEvent {
  final ConversationLocator locator;
  final String? runId;
  const ChatEvent({required this.locator, this.runId});
}

class ChatRunStarted extends ChatEvent {
  final String assistantMessageId;
  const ChatRunStarted({
    required super.locator,
    required String runId,
    required this.assistantMessageId,
  }) : super(runId: runId);
}

class ChatDelta extends ChatEvent {
  final String assistantMessageId;
  final String delta;
  final String accumulatedContent;
  const ChatDelta({
    required super.locator,
    required super.runId,
    required this.assistantMessageId,
    required this.delta,
    required this.accumulatedContent,
  });
}

class ChatMessageCommitted extends ChatEvent {
  final String messageId;
  final String content;
  final bool error;
  const ChatMessageCommitted({
    required super.locator,
    required super.runId,
    required this.messageId,
    required this.content,
    required this.error,
  });
}

class ChatRunCompleted extends ChatEvent {
  const ChatRunCompleted({required super.locator, required super.runId});
}

class ChatRunStopped extends ChatEvent {
  const ChatRunStopped({required super.locator, required super.runId});
}

class ChatErrorEvent extends ChatEvent {
  final String message;
  final String? assistantMessageId;
  const ChatErrorEvent({
    required super.locator,
    required super.runId,
    required this.message,
    this.assistantMessageId,
  });
}
