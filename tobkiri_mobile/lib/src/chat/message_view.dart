import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:url_launcher/url_launcher.dart';

import 'chat_accessibility.dart';
import 'chat_link_policy.dart';
import 'chat_models.dart';

typedef MessageLinkOpener = Future<bool> Function(Uri uri);

enum _LinkDecision { open, copy }

class _MessageLink {
  const _MessageLink({required this.label, required this.target});

  final String label;
  final String target;
}

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
  String? _linkStatus;

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

  Future<void> _reviewLink(_MessageLink link) async {
    final labels = TobkiriChatAccessibilityLabels.of(context);
    if (_linkStatus != null) setState(() => _linkStatus = null);
    final review = ChatLinkReview.evaluate(link.target);
    if (!review.canOpen) {
      _setLinkStatus(_dispositionMessage(review.disposition, labels));
      return;
    }

    final decision = await showDialog<_LinkDecision>(
      context: context,
      builder: (context) => _LinkReviewDialog(link: link, review: review),
    );
    if (!mounted || decision == null) return;
    if (decision == _LinkDecision.copy) {
      try {
        await Clipboard.setData(ClipboardData(text: review.rawTarget));
        if (mounted) _setLinkStatus(labels.linkCopied);
      } on Object {
        if (mounted) _setLinkStatus(labels.linkCopyFailed);
      }
      return;
    }

    var opened = false;
    try {
      final opener = widget.openLink;
      opened = opener != null
          ? await opener(review.uri!)
          : await launchUrl(
              review.uri!,
              mode: LaunchMode.externalApplication,
            );
    } on Object {
      opened = false;
    }
    if (mounted && !opened) _setLinkStatus(labels.launchFailed);
  }

  void _setLinkStatus(String message) {
    setState(() => _linkStatus = message);
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
                    child: _MessageBody(
                      message: message,
                      onTapLink: (text, href) => unawaited(
                        _reviewLink(
                          _MessageLink(
                            label: text.trim().isEmpty ? href : text,
                            target: href,
                          ),
                        ),
                      ),
                    ),
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
                      key: ValueKey('message-link:${link.target}'),
                      label: labels.link(link.label, link.target),
                      hint: labels.reviewLinkHint,
                      icon: Icons.open_in_new,
                      link: true,
                      onPressed: () => unawaited(_reviewLink(link)),
                    ),
                ],
              ),
            ),
          if (_linkStatus != null)
            Semantics(
              key: ValueKey('message-link-status:${message.id}'),
              container: true,
              liveRegion: true,
              label: _linkStatus,
              child: ExcludeSemantics(
                child: Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    _linkStatus!,
                    style: TextStyle(color: scheme.error),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _MessageBody extends StatelessWidget {
  const _MessageBody({required this.message, required this.onTapLink});

  final ChatMessage message;
  final void Function(String text, String href) onTapLink;

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
              if (href != null) onTapLink(text, href);
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

String _plainText(String markdown) =>
    _parseMarkdown(markdown).map((node) => node.textContent).join('\n').trim();

List<_MessageLink> _extractLinks(String value) {
  final links = <_MessageLink>[];
  final seen = <String>{};
  final sourceLinks = _extractMarkdownSourceLinks(value);
  for (final sourceLink in sourceLinks) {
    final link = sourceLink.link;
    if (seen.add(link.target)) links.add(link);
  }

  final bareUrl = RegExp(r'https?://[^\s\]\)<>]+');
  for (final match in bareUrl.allMatches(value)) {
    final belongsToMarkdown = sourceLinks.any(
      (sourceLink) =>
          match.start >= sourceLink.start && match.start < sourceLink.end,
    );
    if (belongsToMarkdown) continue;
    final target =
        match.group(0)?.replaceFirst(RegExp(r'[.,;:!?]+$'), '') ?? '';
    if (target.isNotEmpty && seen.add(target)) {
      links.add(_MessageLink(label: target, target: target));
    }
  }
  return links;
}

typedef _MarkdownSourceLink = ({_MessageLink link, int start, int end});

List<_MarkdownSourceLink> _extractMarkdownSourceLinks(String value) {
  final results = <_MarkdownSourceLink>[];
  var cursor = 0;
  while (cursor < value.length) {
    final labelStart = value.indexOf('[', cursor);
    if (labelStart < 0) break;
    if (labelStart > 0 && value[labelStart - 1] == '!') {
      cursor = labelStart + 1;
      continue;
    }
    final labelEnd = _findUnescaped(value, ']', labelStart + 1);
    if (labelEnd < 0 || labelEnd + 1 >= value.length) break;
    if (value[labelEnd + 1] != '(') {
      cursor = labelStart + 1;
      continue;
    }
    final targetEnd = _findClosingParenthesis(value, labelEnd + 1);
    if (targetEnd < 0) break;
    final body = value.substring(labelEnd + 2, targetEnd).trim();
    final target = _destinationWithoutTitle(body);
    if (target.isNotEmpty) {
      final rawLabel = value.substring(labelStart + 1, labelEnd).trim();
      final label = _plainText(rawLabel);
      results.add((
        link: _MessageLink(
          label: label.isEmpty ? target : label,
          target: target,
        ),
        start: labelStart,
        end: targetEnd + 1,
      ));
    }
    cursor = targetEnd + 1;
  }
  return results;
}

int _findUnescaped(String value, String character, int start) {
  for (var index = start; index < value.length; index += 1) {
    if (value[index] == '\\') {
      index += 1;
      continue;
    }
    if (value[index] == character) return index;
  }
  return -1;
}

int _findClosingParenthesis(String value, int openingIndex) {
  var depth = 1;
  for (var index = openingIndex + 1; index < value.length; index += 1) {
    if (value[index] == '\\') {
      index += 1;
      continue;
    }
    if (value[index] == '(') depth += 1;
    if (value[index] == ')') {
      depth -= 1;
      if (depth == 0) return index;
    }
  }
  return -1;
}

String _destinationWithoutTitle(String body) {
  if (body.startsWith('<')) {
    final closing = _findUnescaped(body, '>', 1);
    if (closing > 0) return _unescapeMarkdown(body.substring(1, closing));
  }
  var depth = 0;
  for (var index = 0; index < body.length; index += 1) {
    if (body[index] == '\\') {
      index += 1;
      continue;
    }
    if (body[index] == '(') depth += 1;
    if (body[index] == ')' && depth > 0) depth -= 1;
    if (RegExp(r'\s').hasMatch(body[index]) && depth == 0) {
      return _unescapeMarkdown(body.substring(0, index));
    }
  }
  return _unescapeMarkdown(body);
}

String _unescapeMarkdown(String value) {
  final result = StringBuffer();
  for (var index = 0; index < value.length; index += 1) {
    if (value[index] == '\\' && index + 1 < value.length) index += 1;
    result.write(value[index]);
  }
  return result.toString();
}

List<md.Node> _parseMarkdown(String value) {
  try {
    return md.Document(
      extensionSet: md.ExtensionSet.gitHubFlavored,
    ).parseLines(value.split('\n'));
  } on Object {
    return [md.Text(value)];
  }
}

String _dispositionMessage(
  ChatLinkDisposition disposition,
  TobkiriChatAccessibilityLabels labels,
) =>
    switch (disposition) {
      ChatLinkDisposition.allowedWeb => '',
      ChatLinkDisposition.malformed => labels.malformedLink,
      ChatLinkDisposition.blockedScheme => labels.blockedLink,
      ChatLinkDisposition.unsupportedScheme => labels.unsupportedLink,
      ChatLinkDisposition.blockedCredentials => labels.credentialLink,
    };

class _LinkReviewDialog extends StatelessWidget {
  const _LinkReviewDialog({required this.link, required this.review});

  final _MessageLink link;
  final ChatLinkReview review;

  @override
  Widget build(BuildContext context) {
    final labels = TobkiriChatAccessibilityLabels.of(context);
    final mismatch = link.label.trim() != review.rawTarget;
    return AlertDialog(
      title: Text(labels.reviewDestination),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(labels.visibleText,
                style: Theme.of(context).textTheme.labelLarge),
            SelectableText(link.label),
            const SizedBox(height: 12),
            Text(labels.destinationHost,
                style: Theme.of(context).textTheme.labelLarge),
            SelectableText(
              review.host,
              key: const ValueKey('link-review-host'),
            ),
            const SizedBox(height: 12),
            Text(labels.fullDestination,
                style: Theme.of(context).textTheme.labelLarge),
            SelectableText(
              review.rawTarget,
              key: const ValueKey('link-review-url'),
            ),
            if (mismatch) ...[
              const SizedBox(height: 12),
              Text(labels.targetMismatch),
            ],
            if (review.needsIdentityWarning) ...[
              const SizedBox(height: 12),
              Text(
                labels.identityWarning,
                key: const ValueKey('link-review-identity-warning'),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('link-review-cancel'),
          onPressed: () => Navigator.of(context).pop(),
          child: Text(labels.cancel),
        ),
        TextButton(
          key: const ValueKey('link-review-copy'),
          onPressed: () => Navigator.of(context).pop(_LinkDecision.copy),
          child: Text(labels.copyLink),
        ),
        FilledButton(
          key: const ValueKey('link-review-open'),
          onPressed: () => Navigator.of(context).pop(_LinkDecision.open),
          child: Text(labels.open),
        ),
      ],
    );
  }
}
