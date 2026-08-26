import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'chat_accessibility.dart';
import 'chat_models.dart';

typedef MessageLinkOpener = Future<void> Function(Uri uri);

class MessageView extends StatefulWidget {
  const MessageView({
    super.key,
    required this.message,
    this.openLink,
  });

  final ChatMessage message;
  final MessageLinkOpener? openLink;

  @override
  State<MessageView> createState() => _MessageViewState();
}

class _MessageViewState extends State<MessageView> {
  bool _showCopy = false;

  void _revealCopy() {
    if (widget.message.content.trim().isEmpty || _showCopy) return;
    setState(() => _showCopy = true);
  }

  Future<void> _copy(TobkiriChatAccessibilityLabels labels) async {
    await Clipboard.setData(ClipboardData(text: widget.message.content));
    if (!mounted) return;
    setState(() => _showCopy = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(labels.copied),
        duration: const Duration(seconds: 1),
      ),
    );
  }

  Future<void> _openLink(Uri uri) async {
    final opener = widget.openLink;
    if (opener != null) {
      await opener(uri);
      return;
    }
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    final message = widget.message;
    final labels = TobkiriChatAccessibilityLabels.of(context);
    final scheme = Theme.of(context).colorScheme;
    final isUser = message.role == ChatRole.user;
    final content = message.content.trim();
    final links = _extractLinks(content);
    final customActions = content.isEmpty
        ? null
        : <CustomSemanticsAction, VoidCallback>{
            CustomSemanticsAction(label: labels.copy): () {
              unawaited(_copy(labels));
            },
          };

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Column(
        crossAxisAlignment:
            isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Semantics(
            key: ValueKey('message-semantics:${message.id}'),
            container: true,
            label: _semanticLabel(message, labels),
            hint: content.isEmpty ? null : labels.copyHint,
            customSemanticsActions: customActions,
            child: Focus(
              onFocusChange: (focused) {
                if (focused) _revealCopy();
              },
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPress: content.isEmpty ? null : _revealCopy,
                child: ExcludeSemantics(
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 520),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: message.error
                          ? scheme.errorContainer
                          : isUser
                              ? scheme.primaryContainer
                              : scheme.surfaceContainerHighest,
                      border: message.error
                          ? Border.all(color: scheme.error, width: 1.5)
                          : null,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: _MessageBody(message: message),
                  ),
                ),
              ),
            ),
          ),
          if (_showCopy || links.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Wrap(
                alignment: isUser ? WrapAlignment.end : WrapAlignment.start,
                spacing: 4,
                runSpacing: 4,
                children: [
                  if (_showCopy)
                    _MessageAction(
                      key: const ValueKey('message-copy'),
                      label: labels.copy,
                      hint: labels.copyHint,
                      icon: Icons.copy_outlined,
                      onPressed: () => unawaited(_copy(labels)),
                    ),
                  for (final link in links)
                    _MessageAction(
                      key: ValueKey('message-link:$link'),
                      label: labels.link(link.toString()),
                      hint: labels.openLinkHint,
                      icon: Icons.open_in_new,
                      link: true,
                      onPressed: () => unawaited(_openLink(link)),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _MessageBody extends StatelessWidget {
  const _MessageBody({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final labels = TobkiriChatAccessibilityLabels.of(context);
    final content = message.content.trim();
    final foreground = message.error
        ? Theme.of(context).colorScheme.onErrorContainer
        : Theme.of(context).colorScheme.onSurface;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (message.error)
          _StatusRow(
            icon: Icons.error_outline,
            label: labels.failed,
            color: foreground,
          ),
        if (message.error && (message.pending || content.isNotEmpty))
          const SizedBox(height: 8),
        if (message.pending)
          _StatusRow(
            icon: Icons.pending_outlined,
            label: labels.processing,
            color: foreground,
            trailing: const SizedBox.square(
              dimension: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        if (message.pending && content.isNotEmpty) const SizedBox(height: 8),
        if (content.isEmpty && !message.pending)
          Text(labels.noContent, style: TextStyle(color: foreground)),
        if (content.isNotEmpty)
          MarkdownBody(
            data: message.content,
            selectable: true,
            styleSheet:
                MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
              p: TextStyle(color: foreground, fontSize: 15, height: 1.5),
            ),
            onTapLink: (text, href, title) async {
              final uri = href == null ? null : Uri.tryParse(href);
              if (uri != null && _isSafeLink(uri)) {
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              }
            },
          ),
      ],
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({
    required this.icon,
    required this.label,
    required this.color,
    this.trailing,
  });

  final IconData icon;
  final String label;
  final Color color;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(color: color, fontWeight: FontWeight.w600),
        ),
        if (trailing != null) ...[const SizedBox(width: 8), trailing!],
      ],
    );
  }
}

class _MessageAction extends StatelessWidget {
  const _MessageAction({
    super.key,
    required this.label,
    required this.hint,
    required this.icon,
    required this.onPressed,
    this.link = false,
  });

  final String label;
  final String hint;
  final IconData icon;
  final VoidCallback onPressed;
  final bool link;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      link: link,
      label: label,
      hint: hint,
      onTap: onPressed,
      child: ExcludeSemantics(
        child: SizedBox.square(
          dimension: 48,
          child: IconButton(
            tooltip: label,
            onPressed: onPressed,
            icon: Icon(icon),
          ),
        ),
      ),
    );
  }
}

String _semanticLabel(
  ChatMessage message,
  TobkiriChatAccessibilityLabels labels,
) {
  final parts = <String>[
    message.role == ChatRole.user ? labels.user : labels.assistant,
    if (message.pending) labels.processing,
    if (message.error) labels.failed,
  ];
  final content = _plainText(message.content.trim());
  parts.add(content.isEmpty ? labels.noContent : '${labels.content}: $content');
  return parts.join(', ');
}

String _plainText(String markdown) => markdown
    .replaceAll(RegExp(r'!\[([^\]]*)\]\([^)]*\)'), r'$1')
    .replaceAll(RegExp(r'\[([^\]]+)\]\([^)]*\)'), r'$1')
    .replaceAll(RegExp(r'[`*_>#~-]'), '')
    .trim();

List<Uri> _extractLinks(String value) {
  final links = <Uri>[];
  final seen = <String>{};
  final pattern = RegExp(r'https?://[^\s\]\)<>]+');
  for (final match in pattern.allMatches(value)) {
    final raw = match.group(0)?.replaceFirst(RegExp(r'[.,;:!?]+$'), '') ?? '';
    final uri = Uri.tryParse(raw);
    if (uri != null && _isSafeLink(uri) && seen.add(uri.toString())) {
      links.add(uri);
    }
  }
  return links;
}

bool _isSafeLink(Uri uri) =>
    uri.hasAuthority && (uri.scheme == 'https' || uri.scheme == 'http');
