import 'package:flutter/material.dart';

import 'qr_payload.dart';

enum QrScanPurpose { apiImport, pcConnect, general }

class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({
    super.key,
    required this.purpose,
    this.hint,
  });

  final QrScanPurpose purpose;
  final String? hint;

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> {
  final _controller = TextEditingController();
  bool _handled = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String get _title => switch (widget.purpose) {
        QrScanPurpose.apiImport => 'API/モデルをQRで取り込む',
        QrScanPurpose.pcConnect => 'PCにQRで接続',
        QrScanPurpose.general => 'QRスキャン',
      };

  bool _matchesPurpose(QrPayload payload) {
    switch (widget.purpose) {
      case QrScanPurpose.apiImport:
        return payload is QrApiImport;
      case QrScanPurpose.pcConnect:
        return payload is QrPcConnection || payload is QrPairingV2;
      case QrScanPurpose.general:
        return true;
    }
  }

  void _submit() {
    if (_handled) return;
    final raw = _controller.text.trim();
    if (raw.isEmpty) return;
    _handled = true;
    final payload = parseQrPayload(raw);
    final mismatch = !_matchesPurpose(payload);
    Navigator.of(context).pop((payload, mismatch));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_title)),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.amber.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.amber.withValues(alpha: 0.4)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, size: 18, color: Colors.amber),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'シミュレータモード: QR内容をテキストで入力してください',
                      style: TextStyle(fontSize: 12, color: Colors.amber),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text(widget.hint ?? _title,
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            TextField(
              controller: _controller,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'QR内容 (JSON または URL)',
                hintText: '{"kind":"rumi_pc","baseUrl":"...","token":"..."}',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: const Icon(Icons.qr_code_scanner),
              label: const Text('スキャン'),
              onPressed: _submit,
            ),
            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 12),
            Text('サンプル', style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ActionChip(
                  label: const Text('PC接続 (rumi_pc)'),
                  onPressed: () {
                    _controller.text =
                        '{"kind":"rumi_pc","baseUrl":"http://192.168.1.10:8765","token":"test-token"}';
                  },
                ),
                ActionChip(
                  label: const Text('API (rumi_api)'),
                  onPressed: () {
                    _controller.text =
                        '{"kind":"rumi_api","baseUrl":"https://api.openai.com/v1","apiKey":"sk-test","model":"gpt-4o-mini"}';
                  },
                ),
                ActionChip(
                  label: const Text('ペアリングv2'),
                  onPressed: () {
                    _controller.text =
                        '{"kind":"rumi_pair_v2","pairingId":"pair-abc","code":"7KMX-PQ2F","baseUrls":["http://192.168.1.10:8765"],"serverPublicKey":"","expiresAt":1781830000000}';
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
