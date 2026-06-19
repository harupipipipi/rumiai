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
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
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

  void _onDetect(BarcodeCapture capture) {
    if (_handled) return;
    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;
    final raw = barcodes.first.rawValue;
    if (raw == null || raw.trim().isEmpty) return;
    _handled = true;
    final payload = parseQrPayload(raw);
    final mismatch = !_matchesPurpose(payload);
    Navigator.of(context).pop((payload, mismatch));
  }

  bool _matchesPurpose(QrPayload payload) {
    switch (widget.purpose) {
      case QrScanPurpose.apiImport:
        return payload is QrApiImport;
      case QrScanPurpose.pcConnect:
        return payload is QrPcConnection;
      case QrScanPurpose.general:
        return true;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          IconButton(
            tooltip: 'ライト',
            icon: const Icon(Icons.flash_on_outlined),
            onPressed: () => _controller.toggleTorch(),
          ),
          IconButton(
            tooltip: 'カメラ切替',
            icon: const Icon(Icons.cameraswitch_outlined),
            onPressed: () => _controller.switchCamera(),
          ),
        ],
      ),
      body: Stack(
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
          ),
          _ScanOverlay(hint: widget.hint ?? _title),
        ],
      ),
    );
  }
}

class _ScanOverlay extends StatelessWidget {
  const _ScanOverlay({required this.hint});
  final String hint;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: SafeArea(
        child: Column(
          children: [
            const Spacer(),
            Center(
              child: Container(
                width: 260,
                height: 260,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white70, width: 2),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  hint,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}
