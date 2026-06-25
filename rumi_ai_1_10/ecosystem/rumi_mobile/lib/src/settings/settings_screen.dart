import 'dart:async';

import 'package:flutter/material.dart';

import '../data/pc/device_store.dart';
import '../data/pc/pc_catalog.dart';
import '../data/pc/pc_catalog_client.dart';
import '../data/pc/pc_pairing_client.dart';
import '../platform/platform_services.dart';
import '../qr/qr_payload.dart';
import '../qr/qr_scanner_screen.dart';
import 'api_config_store.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.configStore,
    required this.deviceStore,
    required this.onApiChanged,
    this.onDevicePaired,
  });

  final ApiConfigStore configStore;
  final MobileDeviceStore deviceStore;
  final ValueChanged<ApiConfig> onApiChanged;
  final ValueChanged<PairedDevice?>? onDevicePaired;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late ApiConfig _config;
  late PcConnection? _pc;
  PairedDevice? _pairedDevice;
  DeviceIdentity? _deviceIdentity;
  bool _loading = true;
  bool _saving = false;

  PcBootstrap? _pcBootstrap;
  PcCatalog? _pcCatalog;
  bool _fetchingCatalog = false;
  String? _catalogError;

  bool _pairingInProgress = false;
  String? _pairingError;

  final _baseUrl = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _label = TextEditingController();
  final _systemPrompt = TextEditingController();
  final _pcUrl = TextEditingController();
  final _pcToken = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in [
      _baseUrl,
      _apiKey,
      _model,
      _label,
      _systemPrompt,
      _pcUrl,
      _pcToken,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final api = await widget.configStore.loadApi();
    final pc = await widget.configStore.loadPc();
    final paired = await widget.deviceStore.loadPairedDevice();
    final identity = await widget.deviceStore.loadOrCreateIdentity();
    if (!mounted) return;
    setState(() {
      _config = api;
      _pc = pc;
      _pairedDevice = paired;
      _deviceIdentity = identity;
      _syncControllers();
      _loading = false;
    });
  }

  void _syncControllers() {
    _baseUrl.text = _config.baseUrl;
    _apiKey.text = _config.apiKey;
    _model.text = _config.model;
    _label.text = _config.label;
    _systemPrompt.text = _config.systemPrompt;
    _pcUrl.text = _pc?.baseUrl ?? '';
    _pcToken.text = _pc?.token ?? '';
  }

  ApiConfig _buildConfig() => ApiConfig(
        baseUrl: _baseUrl.text.trim(),
        apiKey: _apiKey.text.trim(),
        model: _model.text.trim().isEmpty
            ? ApiConfig.defaults.model
            : _model.text.trim(),
        label: _label.text.trim(),
        systemPrompt: _systemPrompt.text.trim(),
        temperature: _config.temperature,
      );

  Future<void> _save() async {
    setState(() => _saving = true);
    final config = _buildConfig();
    await widget.configStore.saveApi(config);
    final pc = _pcUrl.text.trim().isEmpty || _pcToken.text.trim().isEmpty
        ? null
        : PcConnection(
            baseUrl: _pcUrl.text.trim(),
            token: _pcToken.text.trim(),
          );
    await widget.configStore.savePc(pc);
    if (!mounted) return;
    setState(() {
      _config = config;
      _pc = pc;
      _saving = false;
    });
    widget.onApiChanged(config);
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('設定を保存しました')));
    }
  }

  Future<void> _scanApi() async {
    final result = await Navigator.of(context).push<(QrPayload, bool)>(
      MaterialPageRoute(
        builder: (_) => const QrScannerScreen(
          purpose: QrScanPurpose.apiImport,
          hint: 'PCの「アプリ」欄に表示されたAPI/モデルQRをスキャン',
        ),
      ),
    );
    if (result == null) return;
    final (payload, mismatch) = result;
    if (mismatch) {
      _toast('このQRはAPI形式ではありません');
      return;
    }
    if (payload is QrApiImport) {
      setState(() {
        _baseUrl.text = payload.baseUrl;
        _apiKey.text = payload.apiKey;
        if (payload.model != null && payload.model!.isNotEmpty) {
          _model.text = payload.model!;
        }
        if (payload.label != null && payload.label!.isNotEmpty) {
          _label.text = payload.label!;
        }
      });
      _toast('API/モデルを取り込みました。保存してください。');
    }
  }

  Future<void> _scanPc() async {
    final result = await Navigator.of(context).push<(QrPayload, bool)>(
      MaterialPageRoute(
        builder: (_) => const QrScannerScreen(
          purpose: QrScanPurpose.general,
          hint: 'PC接続QRまたはペアリングQRをスキャン',
        ),
      ),
    );
    if (result == null) return;
    final (payload, mismatch) = result;
    if (payload is QrPcConnection) {
      setState(() {
        _pcUrl.text = payload.baseUrl;
        _pcToken.text = payload.token;
      });
      _toast('PC接続情報を取り込みました。保存してください。');
    } else if (payload is QrPairingV2) {
      await _startPairingV2(payload.payload);
    } else {
      _toast('このQRはPC接続形式ではありません');
    }
  }

  Future<void> _startPairingV2(PairingV2Payload payload) async {
    if (payload.isExpired) {
      _toast('QRコードの有効期限が切れています');
      return;
    }
    final identity = _deviceIdentity;
    if (identity == null) {
      _toast('デバイスIDが利用できません');
      return;
    }

    setState(() {
      _pairingInProgress = true;
      _pairingError = null;
    });

    final client = PcPairingClient();
    try {
      final selectedUrl = preferredPairingBaseUrl(payload.baseUrls);
      if (selectedUrl.isEmpty) {
        throw const PcPairingException('接続URLが見つかりません');
      }

      final tempPc = PcConnection(baseUrl: selectedUrl, token: '');
      final claimResp = await client.claim(
        tempPc,
        pairingId: payload.pairingId,
        code: payload.code,
        device: identity,
        requestedCapabilities: const [
          'chat.read',
          'chat.write',
          'tools.observe',
          'tools.approve',
          'credentials.request',
        ],
      );

      if (!mounted) return;
      _toast('ペアリング要求を送信しました。PC側で承認してください。');

      await _pollPairingUntilAccepted(
        client: client,
        pc: tempPc,
        pairingId: claimResp.pairingId,
        pcLabel: friendlyPcLabel(null, selectedUrl),
        payload: payload,
      );
    } on PcPairingException catch (e) {
      if (!mounted) return;
      setState(() {
        _pairingError = e.toString();
        _pairingInProgress = false;
      });
      _toast('ペアリングエラー: ${e.message}');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pairingError = '$e';
        _pairingInProgress = false;
      });
      _toast('ペアリングエラー: $e');
    } finally {
      client.close();
    }
  }

  Future<void> _pollPairingUntilAccepted({
    required PcPairingClient client,
    required PcConnection pc,
    required String pairingId,
    required String pcLabel,
    required PairingV2Payload payload,
  }) async {
    const maxAttempts = 60;
    const interval = Duration(seconds: 2);

    for (var i = 0; i < maxAttempts; i++) {
      if (!mounted) return;
      await Future<void>.delayed(interval);

      try {
        final statusResp = await client.pollStatus(
          pc,
          pairingId: pairingId,
          code: payload.code,
          deviceId: _deviceIdentity!.deviceId,
        );
        if (statusResp.isAccepted && !statusResp.hasDeviceToken) {
          if (!mounted) return;
          setState(() {
            _pairingInProgress = false;
            _pairingError = 'PCから端末トークンが返りませんでした';
          });
          _toast('ペアリングエラー: 端末トークンが空です');
          return;
        }
        if (statusResp.isReady) {
          final token = statusResp.deviceToken!.trim();
          final approvalToken = statusResp.approvalToken?.trim() ?? '';
          final device = PairedDevice(
            deviceId: _deviceIdentity!.deviceId,
            deviceToken: token,
            approvalToken: approvalToken,
            label: _deviceIdentity!.deviceLabel,
            scopes: statusResp.scopes,
            approvalScopes: statusResp.approvalScopes,
            pcBaseUrl: pc.baseUrl,
            pcLabel: friendlyPcLabel(statusResp.pcLabel, pc.baseUrl),
            pairingId: pairingId,
          );
          await widget.deviceStore.savePairedDevice(device);
          final newPc = PcConnection(
            baseUrl: pc.baseUrl,
            token: token,
            approvalToken: approvalToken,
          );
          await widget.configStore.savePc(newPc);
          if (!mounted) return;
          setState(() {
            _pairedDevice = device;
            _pc = newPc;
            _pcUrl.text = pc.baseUrl;
            _pcToken.text = token;
            _pairingInProgress = false;
          });
          widget.onDevicePaired?.call(device);
          _toast('PCとのペアリングが完了しました');
          return;
        }
      } on PcPairingException {
        // continue polling
      }
    }

    if (!mounted) return;
    setState(() {
      _pairingInProgress = false;
      _pairingError = 'タイムアウト: PC側で承認されませんでした';
    });
    _toast('ペアリングがタイムアウトしました');
  }

  Future<void> _unpair() async {
    await widget.deviceStore.clear();
    await widget.configStore.savePc(null);
    if (!mounted) return;
    setState(() {
      _pairedDevice = null;
      _pc = null;
      _pcUrl.text = '';
      _pcToken.text = '';
      _pcBootstrap = null;
      _pcCatalog = null;
    });
    widget.onDevicePaired?.call(null);
    _toast('PCとの接続を解除しました');
  }

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _fetchPcCatalog() async {
    final pc = _pc;
    if (pc == null || !pc.isConfigured) {
      _toast('PC接続情報を保存してください。');
      return;
    }
    setState(() {
      _fetchingCatalog = true;
      _catalogError = null;
    });
    final client = PcCatalogClient();
    try {
      final bootstrap = await client.fetchBootstrap(pc);
      final catalog = await client.fetchCapabilities(pc);
      if (!mounted) return;
      setState(() {
        _pcBootstrap = bootstrap;
        _pcCatalog = catalog;
        _fetchingCatalog = false;
      });
      _toast(
        '${catalog.providers.length}プロバイダー / ${catalog.models.length}モデルを取得しました',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _catalogError = e.toString();
        _fetchingCatalog = false;
      });
    } finally {
      client.close();
    }
  }

  Future<void> _pickModelFromCatalog() async {
    final catalog = _pcCatalog;
    if (catalog == null) {
      _toast('まず「PCから取得」してください。');
      return;
    }
    final selected = await showModalBottomSheet<ModelEntry>(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PcModelPicker(catalog: catalog),
    );
    if (selected == null || !mounted) return;
    setState(() {
      _model.text = selected.modelId;
      _label.text = selected.displayName;
    });
    _toast('${selected.displayName} を選択しました。保存してください。');
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(title: const Text('設定')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SectionTitle(
              icon: Icons.psychology_outlined,
              title: 'AI API (ローカル動作)',
              subtitle: 'OpenAI互換のエンドポイント。スマホ単体でチャットできます。',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _baseUrl,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'API Base URL',
                hintText: 'https://api.openai.com/v1',
                prefixIcon: Icon(Icons.cloud_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _apiKey,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'API Key',
                prefixIcon: Icon(Icons.key_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _model,
              decoration: const InputDecoration(
                labelText: 'モデル',
                hintText: 'gpt-4o-mini',
                prefixIcon: Icon(Icons.model_training_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _label,
              decoration: const InputDecoration(
                labelText: 'ラベル (任意)',
                prefixIcon: Icon(Icons.label_outline),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _systemPrompt,
              minLines: 2,
              maxLines: 5,
              decoration: const InputDecoration(
                labelText: 'システムプロンプト (任意)',
                prefixIcon: Icon(Icons.terminal_outlined),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.qr_code_scanner),
                    label: const Text('QRで取り込む'),
                    onPressed: _scanApi,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    icon: _saving
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.save_outlined),
                    label: const Text('保存'),
                    onPressed: _saving ? null : _save,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 28),
            _SectionTitle(
              icon: Icons.desktop_windows_outlined,
              title: 'PC接続',
              subtitle: 'PCのdefaultspack Kernel APIへ接続する情報。',
            ),
            const SizedBox(height: 12),
            if (_pairedDevice != null) ...[
              _PairedDeviceCard(device: _pairedDevice!, onUnpair: _unpair),
              const SizedBox(height: 12),
            ],
            if (_pairedDevice == null) ...[
              if (_pairingInProgress) ...[
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Theme.of(context).cardTheme.color,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: Theme.of(context).dividerTheme.color ??
                          Colors.transparent,
                    ),
                  ),
                  child: Column(
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(height: 12),
                      const Text('PC側の承認を待っています...'),
                      if (_pairingError != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          _pairingError!,
                          style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ] else ...[
                FilledButton.icon(
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('PCにQRでペアリング'),
                  onPressed: _scanPc,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(46),
                  ),
                ),
                const SizedBox(height: 8),
                const Center(
                  child: Text(
                    'または',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _pcUrl,
                  keyboardType: TextInputType.url,
                  decoration: const InputDecoration(
                    labelText: 'Kernel API URL',
                    hintText: 'http://192.168.x.x:8765',
                    prefixIcon: Icon(Icons.dns_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _pcToken,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Bearer token',
                    prefixIcon: Icon(Icons.vpn_key_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.qr_code_scanner),
                        label: const Text('PC接続QRをスキャン'),
                        onPressed: _scanPc,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton.icon(
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('保存'),
                        onPressed: _save,
                      ),
                    ),
                  ],
                ),
              ],
            ],
            if (_pairingError != null && !_pairingInProgress) ...[
              const SizedBox(height: 8),
              Text(
                _pairingError!,
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ],
            if (_pc != null && _pc!.isConfigured) ...[
              const SizedBox(height: 16),
              FilledButton.tonalIcon(
                icon: _fetchingCatalog
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.cloud_download_outlined),
                label: const Text('PCからプロバイダー/モデルを取得'),
                onPressed: _fetchingCatalog ? null : _fetchPcCatalog,
              ),
              if (_catalogError != null) ...[
                const SizedBox(height: 8),
                Text(
                  _catalogError!,
                  style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.error,
                  ),
                ),
              ],
              if (_pcBootstrap != null) ...[
                const SizedBox(height: 12),
                _PcInfoCard(bootstrap: _pcBootstrap!, catalog: _pcCatalog),
              ],
              if (_pcCatalog != null) ...[
                const SizedBox(height: 12),
                FilledButton.tonalIcon(
                  icon: const Icon(Icons.checklist),
                  label: const Text('モデルを選択'),
                  onPressed: _pickModelFromCatalog,
                ),
              ],
            ],
            const SizedBox(height: 28),
            _SectionTitle(
              icon: Icons.apps_outlined,
              title: 'アプリについて',
              subtitle: 'TestFlight / App Store は準備中です。',
            ),
            const SizedBox(height: 12),
            const _ComingSoonCard(label: 'TestFlight', sub: 'iOSベータ版'),
            const SizedBox(height: 10),
            const _ComingSoonCard(label: 'App Store', sub: 'iOS / Android'),
            const SizedBox(height: 24),
            Center(
              child: TextButton.icon(
                icon: const Icon(Icons.cloud_outlined),
                label: const Text('Cloudflare Pages を開く'),
                onPressed: () => _openUrl('https://pages.cloudflare.com'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    final uri = Uri.parse(url);
    await const PlatformUrlLauncher().open(uri);
  }
}

class _PairedDeviceCard extends StatelessWidget {
  const _PairedDeviceCard({required this.device, required this.onUnpair});
  final PairedDevice device;
  final VoidCallback onUnpair;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Theme.of(context).dividerTheme.color ?? Colors.transparent,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.check_circle, size: 18, color: scheme.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'PC接続済み',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'PC: ${device.displayPcLabel}',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          Text(
            'デバイス: ${device.label}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (device.scopes.isNotEmpty) ...[
            const SizedBox(height: 6),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: device.scopes
                  .map(
                    (s) => Chip(
                      label: Text(s, style: const TextStyle(fontSize: 10)),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  )
                  .toList(),
            ),
          ],
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              icon: const Icon(Icons.link_off, size: 16),
              label: const Text('切断'),
              onPressed: onUnpair,
              style: TextButton.styleFrom(foregroundColor: scheme.error),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({
    required this.icon,
    required this.title,
    required this.subtitle,
  });
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, color: scheme.primary),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleSmall),
              Text(
                subtitle,
                style: Theme.of(context).textTheme.bodySmall,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ComingSoonCard extends StatelessWidget {
  const _ComingSoonCard({required this.label, required this.sub});
  final String label;
  final String sub;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Theme.of(context).dividerTheme.color ?? Colors.transparent,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.titleSmall),
                Text(sub, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: Colors.amber.withValues(alpha: 0.4)),
            ),
            child: Text(
              'Coming soon',
              style: TextStyle(fontSize: 11, color: Colors.amber.shade200),
            ),
          ),
        ],
      ),
    );
  }
}

class _PcInfoCard extends StatelessWidget {
  const _PcInfoCard({required this.bootstrap, required this.catalog});
  final PcBootstrap bootstrap;
  final PcCatalog? catalog;

  @override
  Widget build(BuildContext context) {
    final caps = bootstrap.capabilities;
    final configured = catalog?.configuredProviders ?? const [];
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Theme.of(context).dividerTheme.color ?? Colors.transparent,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.desktop_windows, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  bootstrap.label,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              Text(
                bootstrap.version,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _CapChip(label: 'チャット', on: caps.chat),
              _CapChip(label: 'ツール', on: caps.tools),
              _CapChip(label: '承認', on: caps.approvals),
              _CapChip(label: 'キー転送', on: caps.credentialTransfer),
            ],
          ),
          if (catalog != null) ...[
            const SizedBox(height: 10),
            Text(
              'プロバイダー ${catalog!.providers.length}件（設定済み ${configured.length}）/ モデル ${catalog!.models.length}件 / プロファイル ${catalog!.profiles.length}件 / テンプレート ${catalog!.templates.length}件',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (configured.isNotEmpty) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: configured
                    .map(
                      (p) => Chip(
                        label: Text(p.displayName),
                        avatar: const Icon(Icons.cloud_done, size: 16),
                        visualDensity: VisualDensity.compact,
                      ),
                    )
                    .toList(),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _CapChip extends StatelessWidget {
  const _CapChip({required this.label, required this.on});
  final String label;
  final bool on;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: on ? scheme.primary.withValues(alpha: 0.15) : null,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: on ? scheme.primary.withValues(alpha: 0.4) : scheme.outline,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            on ? Icons.check_circle : Icons.remove_circle_outline,
            size: 13,
            color: on ? scheme.primary : scheme.outline,
          ),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: on ? scheme.primary : scheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _PcModelPicker extends StatefulWidget {
  const _PcModelPicker({required this.catalog});
  final PcCatalog catalog;

  @override
  State<_PcModelPicker> createState() => _PcModelPickerState();
}

class _PcModelPickerState extends State<_PcModelPicker> {
  String? _selectedProvider;
  String _query = '';

  @override
  void initState() {
    super.initState();
    final configured = widget.catalog.configuredProviders;
    _selectedProvider =
        configured.isNotEmpty ? configured.first.providerId : null;
  }

  @override
  Widget build(BuildContext context) {
    final providers = widget.catalog.providers;
    final models = widget.catalog.models
        .where(
          (m) => _selectedProvider == null || m.providerId == _selectedProvider,
        )
        .where(
          (m) =>
              _query.isEmpty ||
              m.displayName.toLowerCase().contains(_query.toLowerCase()) ||
              m.modelId.toLowerCase().contains(_query.toLowerCase()),
        )
        .toList();

    return DraggableScrollableSheet(
      initialChildSize: 0.8,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      expand: false,
      builder: (context, scrollController) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: [
                Text('モデルを選択', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('閉じる'),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: DropdownButtonFormField<String>(
              initialValue: _selectedProvider,
              decoration: const InputDecoration(
                labelText: 'プロバイダー',
                prefixIcon: Icon(Icons.cloud_outlined),
                isDense: true,
              ),
              items: [
                const DropdownMenuItem(value: null, child: Text('すべて')),
                ...providers.map(
                  (p) => DropdownMenuItem(
                    value: p.providerId,
                    child: Text('${p.displayName}${p.configured ? " ✓" : ""}'),
                  ),
                ),
              ],
              onChanged: (v) => setState(() => _selectedProvider = v),
            ),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              decoration: const InputDecoration(
                labelText: '検索',
                prefixIcon: Icon(Icons.search),
                isDense: true,
              ),
              onChanged: (v) => setState(() => _query = v),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: ListView.builder(
              controller: scrollController,
              itemCount: models.length,
              itemBuilder: (context, index) {
                final m = models[index];
                return ListTile(
                  leading: Icon(
                    m.supportsVision
                        ? Icons.visibility_outlined
                        : m.supportsThinking
                            ? Icons.psychology_outlined
                            : Icons.chat_outlined,
                    size: 20,
                  ),
                  title: Text(
                    m.displayName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    '${m.providerId} · ${m.modelId}${m.maxContext > 0 ? " · ${_formatContext(m.maxContext)}" : ""}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  trailing: Wrap(
                    spacing: 4,
                    children: [
                      if (m.supportsToolCalling)
                        _MiniTag(icon: Icons.build_outlined),
                      if (m.supportsVision)
                        _MiniTag(icon: Icons.image_outlined),
                    ],
                  ),
                  onTap: () => Navigator.pop(context, m),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  String _formatContext(int tokens) {
    if (tokens >= 1000000) {
      return '${(tokens / 1000000).toStringAsFixed(1)}M ctx';
    }
    if (tokens >= 1000) return '${(tokens / 1000).toStringAsFixed(0)}K ctx';
    return '$tokens ctx';
  }
}

class _MiniTag extends StatelessWidget {
  const _MiniTag({required this.icon});
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Icon(icon, size: 14, color: Theme.of(context).colorScheme.outline);
  }
}
