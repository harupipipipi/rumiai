import 'dart:async';

import 'package:flutter/material.dart';

import '../../domain/chat_event.dart';

class ApprovalCard extends StatefulWidget {
  const ApprovalCard({
    super.key,
    required this.event,
    required this.onApprove,
    required this.onDeny,
  });

  final ApprovalEvent event;
  final FutureOr<void> Function() onApprove;
  final FutureOr<void> Function(String? reason) onDeny;

  @override
  State<ApprovalCard> createState() => _ApprovalCardState();
}

class _ApprovalCardState extends State<ApprovalCard> {
  bool _busy = false;

  ApprovalEvent get event => widget.event;

  Future<void> _approve() async {
    if (_busy) return;
    if (event.isHighImpact) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('影響の大きい操作を確認'),
          content: Text(
            '${event.field('consequence')}\n対象: ${event.field('target')}',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('戻る'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('確認して許可'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    setState(() => _busy = true);
    try {
      await Future.sync(widget.onApprove);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deny() async {
    if (_busy) return;
    final controller = TextEditingController();
    final reason = await showDialog<String?>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('拒否理由（任意）'),
        content: TextField(
          controller: controller,
          maxLines: 3,
          decoration: const InputDecoration(hintText: '要求元に役立つ理由を入力'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('戻る'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('拒否する'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (reason == null) return;
    setState(() => _busy = true);
    try {
      await Future.sync(() => widget.onDeny(reason.isEmpty ? null : reason));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    if (!event.pending) {
      return _ResolvedCard(event: event);
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.tertiaryContainer.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.tertiary.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.shield_outlined, size: 18, color: scheme.tertiary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '承認要求',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: scheme.tertiary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            event.field('consequence', event.prompt),
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 8),
          for (final item in <(String, String)>[
            ('対象', event.field('target')),
            ('影響するデータ', event.field('affected_data')),
            ('理由', event.field('reason')),
            ('権限', event.field('capability', event.toolName)),
            ('リスク', event.field('risk_explanation')),
            ('範囲', event.field('scope')),
            ('永続性', event.field('persistence')),
            ('要求元', event.field('requester')),
            ('有効期限', event.field('expires_at')),
            ('監査', event.field('audit_text')),
          ])
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                '${item.$1}: ${item.$2}',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('技術的な詳細'),
            children: [
              SelectableText(
                '${event.enforcementMetadata}',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.close),
                  label: const Text('拒否'),
                  onPressed: _busy ? null : _deny,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: scheme.error,
                    side: BorderSide(
                      color: scheme.error.withValues(alpha: 0.5),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.check),
                  label: const Text('許可'),
                  onPressed: _busy ? null : _approve,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ResolvedCard extends StatelessWidget {
  const _ResolvedCard({required this.event});
  final ApprovalEvent event;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final approved = event.approved;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: approved
            ? scheme.primaryContainer.withValues(alpha: 0.2)
            : scheme.errorContainer.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(
            approved ? Icons.check_circle : Icons.cancel,
            size: 16,
            color: approved ? scheme.primary : scheme.error,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '${event.toolName}: ${approved ? "許可済み" : "拒否済み"}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: approved
                    ? scheme.onPrimaryContainer
                    : scheme.onErrorContainer,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
