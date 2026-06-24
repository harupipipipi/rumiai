import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

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
  late final MobileScannerController _scanner;
  bool _handled = false;
  bool _showManualInput = false;

  @override
  void initState() {
    super.initState();
    _scanner = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      formats: const [BarcodeFormat.qrCode],
    );
  }

  @override
  void dispose() {
    _scanner.dispose();
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

  void _handleRaw(String raw) {
    if (_handled) return;
    raw = raw.trim();
    if (raw.isEmpty) return;
    _handled = true;
    final payload = parseQrPayload(raw);
    final mismatch = !_matchesPurpose(payload);
    Navigator.of(context).pop((payload, mismatch));
  }

  void _submitManual() {
    _handleRaw(_controller.text);
  }

  void _onDetect(BarcodeCapture capture) {
    final value = capture.barcodes
        .map((barcode) => barcode.rawValue)
        .whereType<String>()
        .firstWhere((value) => value.trim().isNotEmpty, orElse: () => '');
    _handleRaw(value);
  }

  Widget _buildScanner() {
    return AspectRatio(
      aspectRatio: 1,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(
          fit: StackFit.expand,
          children: [
            MobileScanner(
              controller: _scanner,
              onDetect: _onDetect,
              errorBuilder: (context, error) => Container(
                color: Colors.black,
                padding: const EdgeInsets.all(20),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.no_photography_outlined,
                        color: Colors.white70, size: 42),
                    const SizedBox(height: 12),
                    Text(
                      error.errorDetails?.message ?? 'カメラを開始できませんでした',
                      textAlign: TextAlign.center,
                      style:
                          const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                    const SizedBox(height: 16),
                    FilledButton.tonal(
                      onPressed: () {
                        setState(() => _showManualInput = true);
                      },
                      child: const Text('手入力に切り替え'),
                    ),
                  ],
                ),
              ),
            ),
            IgnorePointer(
              child: Center(
                child: Container(
                  width: 236,
                  height: 236,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: Colors.white, width: 3),
                  ),
                ),
              ),
            ),
            Positioned(
              left: 12,
              right: 12,
              bottom: 12,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton.filledTonal(
                    tooltip: 'ライト',
                    icon: const Icon(Icons.flashlight_on_outlined),
                    onPressed: _scanner.toggleTorch,
                  ),
                  const SizedBox(width: 12),
                  IconButton.filledTonal(
                    tooltip: 'カメラ切替',
                    icon: const Icon(Icons.cameraswitch_outlined),
                    onPressed: _scanner.switchCamera,
                  ),
                  const SizedBox(width: 12),
                  IconButton.filledTonal(
                    tooltip: '手入力',
                    icon: const Icon(Icons.keyboard_outlined),
                    onPressed: () {
                      setState(() => _showManualInput = true);
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildManualInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
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
          icon: const Icon(Icons.check),
          label: const Text('取り込む'),
          onPressed: _submitManual,
        ),
      ],
    );
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
            Text(widget.hint ?? _title,
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            _showManualInput ? _buildManualInput() : _buildScanner(),
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
