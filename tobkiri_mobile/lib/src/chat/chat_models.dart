enum ChatRole {
  user,
  assistant;

  static ChatRole fromWire(String value) =>
      value == 'user' ? ChatRole.user : ChatRole.assistant;
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    this.pending = false,
    this.error = false,
  });

  final String id;
  final ChatRole role;
  final String content;
  final bool pending;
  final bool error;

  ChatMessage copyWith({
    String? content,
    bool? pending,
    bool? error,
  }) =>
      ChatMessage(
        id: id,
        role: role,
        content: content ?? this.content,
        pending: pending ?? this.pending,
        error: error ?? this.error,
      );
}
