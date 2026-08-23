import 'package:flutter/material.dart';

import 'chat_accessibility.dart';

class ComposerBar extends StatefulWidget {
  const ComposerBar({
    super.key,
    required this.onSend,
    required this.onStop,
    required this.busy,
    this.onAdd,
    this.enabled = true,
  });

  final ValueChanged<String> onSend;
  final VoidCallback onStop;
  final VoidCallback? onAdd;
  final bool busy;
  final bool enabled;

  @override
  State<ComposerBar> createState() => _ComposerBarState();
}

class _ComposerBarState extends State<ComposerBar> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
  }

  void _onTextChanged() {
    final hasText = _controller.text.trim().isNotEmpty;
    if (hasText != _hasText) setState(() => _hasText = hasText);
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty || widget.busy || !widget.enabled) return;
    widget.onSend(text);
    _controller.clear();
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
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              FocusTraversalOrder(
                order: const NumericFocusOrder(1),
                child: _ActionButton(
                  key: const ValueKey('composer-add'),
                  label: labels.add,
                  hint: labels.addHint,
                  onPressed: widget.busy ? null : widget.onAdd,
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
                          onPressed: widget.enabled && _hasText ? _send : null,
                          icon: Icons.arrow_upward_rounded,
                        ),
                ),
              ),
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
