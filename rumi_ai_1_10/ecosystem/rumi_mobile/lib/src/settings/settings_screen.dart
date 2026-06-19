import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../qr/qr_payload.dart';
import '../qr/qr_scanner_screen.dart';
import 'api_config_store.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.configStore,
    required this.onApiChanged,
  });

  final ApiConfigStore configStore;
  final ValueChanged<ApiConfig> onApiChanged;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late ApiConfig _config;
  late PcConnection? _pc;
  bool _loading = true;
  bool _saving = false;

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
    if (!mounted) return;
    setState(() {
      _config = api;
      _pc = pc;
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
            baseUrl: _pcUrl.text.trim(), token: _pcToken.text.trim());
    await widget.configStore.savePc(pc);
    if (!mounted) return;
    setState(() {
      _config = config;
      _pc = pc;
      _saving = false;
    });
    widget.onApiChanged(config);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('設定を保存しました')),
      );
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
          purpose: QrScanPurpose.pcConnect,
          hint: 'PCの「アプリ」欄に表示されたPC接続QRをスキャン',
        ),
      ),
    );
    if (result == null) return;
    final (payload, mismatch) = result;
    if (mismatch) {
      _toast('このQRはPC接続形式ではありません');
      return;
    }
    if (payload is QrPcConnection) {
      setState(() {
        _pcUrl.text = payload.baseUrl;
        _pcToken.text = payload.token;
      });
      _toast('PC接続情報を取り込みました。保存してください。');
    }
  }

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
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
                            child: CircularProgressIndicator(strokeWidth: 2))
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
            const SizedBox(height: 16),
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
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
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
              Text(subtitle,
                  style: Theme.of(context).textTheme.bodySmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
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
            color: Theme.of(context).dividerTheme.color ?? Colors.transparent),
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
            child: Text('Coming soon',
                style: TextStyle(fontSize: 11, color: Colors.amber.shade200)),
          ),
        ],
      ),
    );
  }
}
