import 'package:flutter/material.dart';

import 'chat_accessibility.dart';

enum ComposerSendDisposition { accepted, rejected, queued }

@immutable
class ComposerSendResult {
  const ComposerSendResult._(this.disposition, this.message);

  const ComposerSendResult.accepted()
      : this._(ComposerSendDisposition.accepted, null);

  const ComposerSendResult.rejected(String message)
      : this._(ComposerSendDisposition.rejected, message);

  const ComposerSendResult.queued(String message)
      : this._(ComposerSendDisposition.queued, message);

  final ComposerSendDisposition disposition;
  final String? message;

  bool get clearsDraft => disposition == ComposerSendDisposition.accepted;
}

typedef ComposerSendCallback = Future<ComposerSendResult> Function(String text);

class ComposerBar extends StatefulWidget {
  const ComposerBar({
    super.key,
    required this.onSend,
    required this.onStop,
    required this.busy,
    this.onAdd,
    this.enabled = true,
    this.initialText = '',
    this.onChanged,
  });

  final ComposerSendCallback onSend;
  final VoidCallback onStop;
  final VoidCallback? onAdd;
  final bool busy;
  final bool enabled;
  final String initialText;
  final ValueChanged<String>? onChanged;

  @override
  State<ComposerBar> createState() => _ComposerBarState();
}

class _ComposerBarState extends State<ComposerBar> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  bool _hasText = false;
  bool _submitting = false;
  String? _feedback;
  late String _lastReportedText;

  @override
  void initState() {
    super.initState();
    _controller.text = widget.initialText;
    _lastReportedText = _controller.text;
    _hasText = _controller.text.trim().isNotEmpty;
    _controller.addListener(_onTextChanged);
  }

  void _onTextChanged() {
    final hasText = _controller.text.trim().isNotEmpty;
    if (hasText != _hasText) setState(() => _hasText = hasText);
    if (_controller.text != _lastReportedText) {
      _lastReportedText = _controller.text;
      widget.onChanged?.call(_controller.text);
    }
  }

  @override
  void didUpdateWidget(ComposerBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialText != oldWidget.initialText &&
        _controller.text == oldWidget.initialText) {
      _controller.value = TextEditingValue(
        text: widget.initialText,
        selection: TextSelection.collapsed(offset: widget.initialText.length),
      );
    }
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || widget.busy || _submitting || !widget.enabled) return;
    setState(() {
      _submitting = true;
      _feedback = null;
    });
    ComposerSendResult result;
    try {
      result = await widget.onSend(text);
    } catch (_) {
      result = const ComposerSendResult.rejected(
        '送信を開始できませんでした。内容を確認して再試行してください。',
      );
    }
    if (!mounted) return;
    if (result.clearsDraft && _controller.text.trim() == text) {
      _controller.clear();
    }
    setState(() {
      _submitting = false;
      _feedback = result.message;
    });
    _focusNode.requestFocus();
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_onTextChanged)
      ..dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final labels = TobkiriChatAccessibilityLabels.of(context);
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
        child: FocusTraversalGroup(
          policy: OrderedTraversalPolicy(),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  FocusTraversalOrder(
                    order: const NumericFocusOrder(1),
                    child: _ActionButton(
                      key: const ValueKey('composer-add'),
                      label: labels.add,
                      hint: labels.addHint,
                      onPressed:
                          widget.busy || _submitting ? null : widget.onAdd,
                      icon: Icons.add_rounded,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FocusTraversalOrder(
                      order: const NumericFocusOrder(2),
                      child: Semantics(
                        key: const ValueKey('composer-field'),
                        label: labels.composer,
                        hint: labels.composerHint,
                        child: Stack(
                          alignment: Alignment.centerLeft,
                          children: [
                            if (!_hasText)
                              const IgnorePointer(
                                child: ExcludeSemantics(
                                  child: Padding(
                                    padding: EdgeInsets.only(left: 12),
                                    child: Text('メッセージを入力...'),
                                  ),
                                ),
                              ),
                            TextField(
                              enabled: widget.enabled,
                              controller: _controller,
                              focusNode: _focusNode,
                              minLines: 1,
                              maxLines: 6,
                              keyboardType: TextInputType.multiline,
                              textInputAction: TextInputAction.newline,
                              decoration: const InputDecoration(),
                              onSubmitted: (_) => _send(),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FocusTraversalOrder(
                    order: const NumericFocusOrder(3),
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 150),
                      child: widget.busy
                          ? _ActionButton(
                              key: const ValueKey('composer-stop'),
                              label: labels.stop,
                              hint: labels.stopHint,
                              onPressed: widget.onStop,
                              icon: Icons.stop_rounded,
                            )
                          : _ActionButton(
                              key: const ValueKey('composer-send'),
                              label: labels.send,
                              hint: _hasText
                                  ? labels.sendHint
                                  : labels.sendDisabledHint,
                              onPressed:
                                  widget.enabled && _hasText && !_submitting
                                      ? () => _send()
                                      : null,
                              icon: _submitting
                                  ? Icons.hourglass_top_rounded
                                  : Icons.arrow_upward_rounded,
                            ),
                    ),
                  ),
                ],
              ),
              if (_feedback != null) ...[
                const SizedBox(height: 6),
                Semantics(
                  liveRegion: true,
                  child: Row(
                    key: const ValueKey('composer-retry-state'),
                    children: [
                      Icon(
                        Icons.sync_problem_outlined,
                        size: 18,
                        color: Theme.of(context).colorScheme.error,
                      ),
                      const SizedBox(width: 8),
                      Expanded(child: Text(_feedback!)),
                      TextButton(
                        key: const ValueKey('composer-retry'),
                        onPressed:
                            widget.busy || _submitting ? null : () => _send(),
                        child: const Text('再試行'),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    super.key,
    required this.label,
    required this.hint,
    required this.onPressed,
    required this.icon,
  });

  final String label;
  final String hint;
  final VoidCallback? onPressed;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      enabled: onPressed != null,
      label: label,
      hint: hint,
      onTap: onPressed,
      child: ExcludeSemantics(
        child: Tooltip(
          message: label,
          child: SizedBox.square(
            dimension: 48,
            child: IconButton(
              onPressed: onPressed,
              icon: Icon(icon),
              style: IconButton.styleFrom(
                minimumSize: const Size.square(48),
                padding: EdgeInsets.zero,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
