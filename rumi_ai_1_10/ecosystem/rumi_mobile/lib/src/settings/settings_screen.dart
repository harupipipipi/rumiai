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
  List<MobileProviderConfig> _providerConfigs = [];
  late PcConnection? _pc;
  MobileNotificationSettings _notificationSettings =
      MobileNotificationSettings.defaults;
  List<PairedDevice> _pairedDevices = [];
  DeviceIdentity? _deviceIdentity;
  bool _loading = true;
  bool _saving = false;

  PcBootstrap? _pcBootstrap;
  PcCatalog? _pcCatalog;
  bool _fetchingCatalog = false;
  String? _catalogError;

  bool _pairingInProgress = false;
  String? _pairingError;
  String _pairingVerificationCode = '';

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
    final providerConfigs = await widget.configStore.loadProviderConfigs();
    final pc = await widget.configStore.loadPc();
    final notificationSettings =
        await widget.configStore.loadNotificationSettings();
    final paired = await widget.deviceStore.loadPairedDevice();
    final pairedDevices = await widget.deviceStore.loadPairedDevices();
    final identity = await widget.deviceStore.loadOrCreateIdentity();
    if (!mounted) return;
    setState(() {
      _config = api;
      _providerConfigs = providerConfigs;
      _pc = pc;
      _notificationSettings = notificationSettings;
      _pairedDevices = pairedDevices;
      if (_pc == null && paired != null) {
        _pc = paired.toPcConnection();
      }
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
    final pcUrl = _pcUrl.text.trim();
    if (pcUrl.isNotEmpty && !pcConnectionUrlAllowed(pcUrl)) {
      if (!mounted) return;
      setState(() => _saving = false);
      _toast('release版ではPC接続にHTTPS URLが必要です');
      return;
    }
    final pc = pcUrl.isEmpty || _pcToken.text.trim().isEmpty
        ? null
        : PcConnection(
            baseUrl: pcUrl,
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
      if (!pcConnectionUrlAllowed(payload.baseUrl)) {
        _toast('release版ではPC接続にHTTPS URLが必要です');
        return;
      }
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

    const requestedScopes = [
      'chat.read',
      'chat.write',
      'tools.observe',
    ];
    final verificationCode = await claimVerificationCode(
      pairingId: payload.pairingId,
      device: identity,
      requestedCapabilities: requestedScopes,
    );

    setState(() {
      _pairingInProgress = true;
      _pairingError = null;
      _pairingVerificationCode = verificationCode;
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
        requestedCapabilities: requestedScopes,
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
        _pairingVerificationCode = '';
      });
      _toast('ペアリングエラー: ${e.message}');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pairingError = '$e';
        _pairingInProgress = false;
        _pairingVerificationCode = '';
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
        );
        if (!statusResp.isAccepted) continue;

        final tokenResp = await client.pickupTokenDelivery(
          pc,
          pairingId: pairingId,
          pickupSecret: payload.pickupSecret,
          deviceId: _deviceIdentity!.deviceId,
        );
        if (!tokenResp.hasDeviceToken && !tokenResp.hasTokenDeliveryEnvelope) {
          if (!mounted) return;
          setState(() {
            _pairingInProgress = false;
            _pairingError = 'PCから端末トークンが返りませんでした';
            _pairingVerificationCode = '';
          });
          _toast('ペアリングエラー: 端末トークンが空です');
          return;
        }
        if (tokenResp.isReady) {
          final deliveryPayload = tokenResp.hasTokenDeliveryEnvelope
              ? await widget.deviceStore.decryptTokenDeliveryEnvelope(
                  tokenResp.tokenDeliveryEnvelope!,
                  pairingId: pairingId,
                  deviceId: _deviceIdentity!.deviceId,
                )
              : <String, dynamic>{};
          final token = (deliveryPayload['client_access_token'] as String? ??
                  deliveryPayload['device_token'] as String? ??
                  tokenResp.deviceToken ??
                  '')
              .trim();
          final approvalToken =
              (deliveryPayload['approver_access_token'] as String? ??
                      deliveryPayload['approval_token'] as String? ??
                      tokenResp.approvalToken ??
                      '')
                  .trim();
          if (token.isEmpty) {
            if (!mounted) return;
            setState(() {
              _pairingInProgress = false;
              _pairingError = '端末トークンの復号に失敗しました';
              _pairingVerificationCode = '';
            });
            _toast('ペアリングエラー: 端末トークンを復号できませんでした');
            return;
          }
          final scopes = _stringList(
            deliveryPayload['scopes'],
            fallback: tokenResp.scopes,
          );
          final approvalScopes = _stringList(
            deliveryPayload['approval_scopes'],
            fallback: tokenResp.approvalScopes,
          );
          final device = PairedDevice(
            deviceId: _deviceIdentity!.deviceId,
            deviceToken: token,
            approvalToken: approvalToken,
            label: _deviceIdentity!.deviceLabel,
            scopes: scopes,
            approvalScopes: approvalScopes,
            pcBaseUrl: pc.baseUrl,
            pcLabel: friendlyPcLabel(
              deliveryPayload['pc_label'] as String? ?? tokenResp.pcLabel,
              pc.baseUrl,
            ),
            pairingId: pairingId,
          );
          await widget.deviceStore.savePairedDevice(device);
          final newPc = PcConnection(
            baseUrl: pc.baseUrl,
            token: token,
            approvalToken: approvalToken,
          );
          await widget.configStore.savePc(newPc);
          if (tokenResp.hasTokenDeliveryEnvelope) {
            try {
              await client.ackTokenDelivery(
                pc,
                pairingId: pairingId,
                pickupSecret: payload.pickupSecret,
                deviceId: _deviceIdentity!.deviceId,
                deliveryId: tokenResp.deliveryId,
              );
            } catch (_) {
              // The encrypted payload is already saved locally; ack can retry on
              // a later status poll without rotating the server-side token.
            }
          }
          final pairedDevices = await widget.deviceStore.loadPairedDevices();
          if (!mounted) return;
          setState(() {
            _pairedDevices = pairedDevices;
            _pc = newPc;
            _pcUrl.text = pc.baseUrl;
            _pcToken.text = token;
            _pairingInProgress = false;
            _pairingVerificationCode = '';
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
      _pairingVerificationCode = '';
    });
    _toast('ペアリングがタイムアウトしました');
  }

  Future<void> _selectPairedDevice(PairedDevice device) async {
    await widget.deviceStore.savePairedDevice(device);
    final pc = device.toPcConnection();
    await widget.configStore.savePc(pc);
    if (!mounted) return;
    setState(() {
      _pc = pc;
      _pcUrl.text = pc.baseUrl;
      _pcToken.text = pc.token;
    });
    widget.onDevicePaired?.call(device);
    _toast('${device.displayPcLabel} に切り替えました');
  }

  Future<void> _unpair(PairedDevice device) async {
    await widget.deviceStore.removePairedDevice(device.connectionId);
    final devices = await widget.deviceStore.loadPairedDevices();
    final removingActive =
        _pc?.baseUrl == device.pcBaseUrl && _pc?.token == device.deviceToken;
    PcConnection? nextPc = _pc;
    PairedDevice? nextDevice;
    if (removingActive) {
      nextDevice = devices.isNotEmpty ? devices.first : null;
      nextPc = nextDevice?.toPcConnection();
      await widget.configStore.savePc(nextPc);
      if (nextDevice != null) {
        await widget.deviceStore.savePairedDevice(nextDevice);
      }
    }
    if (!mounted) return;
    setState(() {
      _pairedDevices = devices;
      _pc = nextPc;
      _pcUrl.text = nextPc?.baseUrl ?? '';
      _pcToken.text = nextPc?.token ?? '';
      _pcBootstrap = null;
      _pcCatalog = null;
    });
    if (removingActive) {
      widget.onDevicePaired?.call(nextDevice);
    }
    _toast('${device.displayPcLabel} との接続を解除しました');
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
      final providerConfigs = _mergeProviderCatalog(catalog);
      await widget.configStore.saveProviderConfigs(providerConfigs);
      if (!mounted) return;
      setState(() {
        _pcBootstrap = bootstrap;
        _pcCatalog = catalog;
        _providerConfigs = providerConfigs;
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

  List<MobileProviderConfig> _mergeProviderCatalog(PcCatalog catalog) {
    final existingByProvider = {
      for (final config in _providerConfigs) config.providerId: config,
    };
    final merged = <MobileProviderConfig>[];
    for (final provider in catalog.providers) {
      if (!_shouldShowMobileProvider(provider)) continue;
      final existing = existingByProvider.remove(provider.providerId);
      final model = existing?.model.trim().isNotEmpty == true
          ? existing!.model
          : _defaultModelForProvider(provider, catalog);
      final baseUrl = existing?.baseUrl.trim().isNotEmpty == true
          ? existing!.baseUrl
          : _defaultBaseUrlForProvider(provider);
      final openaiCompatible = provider.openaiCompatible ||
          _usesOpenAiCompatibleFallback(provider) ||
          _baseUrlLooksOpenAiCompatible(baseUrl);
      merged.add(
        MobileProviderConfig(
          providerId: provider.providerId,
          displayName: provider.displayName.isNotEmpty
              ? provider.displayName
              : provider.providerId,
          label: existing?.label ?? '',
          apiKey: existing?.apiKey ?? '',
          baseUrl: baseUrl,
          model: model,
          openaiCompatible: openaiCompatible,
          local: provider.local,
          catalogOnly: provider.catalogOnly,
        ),
      );
    }
    merged.addAll(existingByProvider.values);
    merged.sort((a, b) => a.effectiveLabel.compareTo(b.effectiveLabel));
    return merged;
  }

  bool _shouldShowMobileProvider(ProviderEntry provider) {
    final providerId = provider.providerId.trim();
    if (providerId.isEmpty) return false;
    if (providerId == 'stub' || providerId == 'rumi') return false;
    if (provider.local && provider.defaultBaseUrl.startsWith('local://')) {
      return false;
    }
    return true;
  }

  String _defaultModelForProvider(ProviderEntry provider, PcCatalog catalog) {
    final chatDefault = provider.defaultModelFor['chat']?.trim() ?? '';
    if (chatDefault.isNotEmpty) return chatDefault;
    final providerDefault = provider.defaultModel.trim();
    if (providerDefault.isNotEmpty) return providerDefault;
    final profiles = catalog.profiles
        .where((profile) => profile.providerId == provider.providerId)
        .toList();
    if (profiles.isNotEmpty) return profiles.first.modelId;
    final models = catalog.modelsForProvider(provider.providerId);
    if (models.isNotEmpty) return models.first.modelId;
    return ApiConfig.defaults.model;
  }

  String _defaultBaseUrlForProvider(ProviderEntry provider) {
    final catalogUrl = provider.defaultBaseUrl.trim();
    if (catalogUrl.isNotEmpty) return catalogUrl;
    switch (provider.providerId) {
      case 'openai':
        return 'https://api.openai.com/v1';
      case 'google':
      case 'gemini':
        return 'https://generativelanguage.googleapis.com/v1beta/openai';
      case 'anthropic':
        return 'https://api.anthropic.com';
      case 'openrouter':
        return 'https://openrouter.ai/api/v1';
      default:
        return '';
    }
  }

  bool _usesOpenAiCompatibleFallback(ProviderEntry provider) {
    return provider.providerId == 'google' || provider.providerId == 'gemini';
  }

  bool _baseUrlLooksOpenAiCompatible(String baseUrl) {
    final lower = baseUrl.trim().toLowerCase();
    if (lower.isEmpty || lower.startsWith('local://')) return false;
    return lower.contains('/openai') ||
        lower.endsWith('/v1') ||
        lower.contains('/v1/');
  }

  bool _isActiveMobileProvider(MobileProviderConfig provider) {
    return _config.providerId == provider.providerId &&
        _config.baseUrl == provider.baseUrl &&
        _config.model == provider.model;
  }

  Future<void> _activateMobileProvider(MobileProviderConfig provider) async {
    if (!provider.isConfigured) {
      await _editMobileProvider(provider);
      return;
    }
    final next = provider.toApiConfig(
      systemPrompt: _systemPrompt.text.trim(),
      temperature: _config.temperature,
    );
    await widget.configStore.saveApi(next);
    if (!mounted) return;
    setState(() {
      _config = next;
      _syncControllers();
    });
    widget.onApiChanged(next);
    _toast('${provider.effectiveLabel} をこのスマホのAPIにしました');
  }

  Future<void> _editMobileProvider(MobileProviderConfig provider) async {
    final label = TextEditingController(text: provider.label);
    final apiKey = TextEditingController(text: provider.apiKey);
    final saved = await showModalBottomSheet<MobileProviderConfig>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            left: 16,
            right: 16,
            top: 4,
            bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                provider.displayName.isNotEmpty
                    ? provider.displayName
                    : provider.providerId,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: label,
                decoration: const InputDecoration(
                  labelText: 'ラベル',
                  prefixIcon: Icon(Icons.label_outline),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: apiKey,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'API Key',
                  prefixIcon: Icon(Icons.key_outlined),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('キャンセル'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.icon(
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('保存'),
                      onPressed: () {
                        Navigator.pop(
                          context,
                          provider.copyWith(
                            label: label.text.trim(),
                            apiKey: apiKey.text.trim(),
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
    label.dispose();
    apiKey.dispose();
    if (saved == null) return;
    final nextProviders = [
      for (final existing in _providerConfigs)
        if (existing.providerId != saved.providerId) existing,
      saved,
    ]..sort((a, b) => a.effectiveLabel.compareTo(b.effectiveLabel));
    await widget.configStore.saveProviderConfigs(nextProviders);
    if (!mounted) return;
    setState(() => _providerConfigs = nextProviders);
    if (saved.isConfigured) {
      await _activateMobileProvider(saved);
    } else {
      _toast('API Keyを保存しました');
    }
  }

  Future<void> _setPcTaskFinishedNotifications(bool enabled) async {
    final next = _notificationSettings.copyWith(
      pcTaskFinishedEnabled: enabled,
    );
    setState(() => _notificationSettings = next);
    await widget.configStore.saveNotificationSettings(next);
    if (enabled) {
      unawaited(const PlatformNotifications().requestAuthorization());
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

  bool _isActivePairedDevice(PairedDevice device) {
    final pc = _pc;
    return pc != null &&
        pc.baseUrl == device.pcBaseUrl &&
        pc.token == device.deviceToken;
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
              title: 'このスマホのAI API',
              subtitle: 'PCから取得したproviderごとにAPI Keyを保存できます。',
            ),
            const SizedBox(height: 12),
            if (_providerConfigs.isNotEmpty) ...[
              for (final provider in _providerConfigs) ...[
                _MobileProviderCard(
                  provider: provider,
                  active: _isActiveMobileProvider(provider),
                  onUse: () => unawaited(_activateMobileProvider(provider)),
                  onEdit: () => unawaited(_editMobileProvider(provider)),
                ),
                const SizedBox(height: 10),
              ],
              const SizedBox(height: 6),
            ] else ...[
              const _ProviderHintCard(),
              const SizedBox(height: 12),
            ],
            Text(
              'OpenAI互換を直接設定',
              style: Theme.of(context).textTheme.titleSmall,
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
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              secondary: const Icon(Icons.notifications_active_outlined),
              title: const Text('PCタスク完了通知'),
              subtitle: const Text('PCで実行したチャット/タスクが終わったら通知します。'),
              value: _notificationSettings.pcTaskFinishedEnabled,
              onChanged: (value) {
                unawaited(_setPcTaskFinishedNotifications(value));
              },
            ),
            const SizedBox(height: 12),
            if (_pairedDevices.isNotEmpty) ...[
              for (final device in _pairedDevices) ...[
                _PairedDeviceCard(
                  device: device,
                  active: _isActivePairedDevice(device),
                  onUse: () => unawaited(_selectPairedDevice(device)),
                  onUnpair: () => unawaited(_unpair(device)),
                ),
                const SizedBox(height: 12),
              ],
            ],
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
                    if (_pairingVerificationCode.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text(
                        '確認コード',
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _pairingVerificationCode,
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontFeatures: const [
                            FontFeature.tabularFigures(),
                          ],
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'PC側に表示されているコードと一致することを確認してください',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    ],
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
              const SizedBox(height: 12),
            ] else ...[
              FilledButton.icon(
                icon: const Icon(Icons.qr_code_scanner),
                label: Text(_pairedDevices.isEmpty ? 'PCにQRでペアリング' : 'PCを追加'),
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
                  hintText: 'https://your-rumi.example.com',
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
  const _PairedDeviceCard({
    required this.device,
    required this.active,
    required this.onUse,
    required this.onUnpair,
  });
  final PairedDevice device;
  final bool active;
  final VoidCallback onUse;
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
              Icon(
                active ? Icons.check_circle : Icons.desktop_windows_outlined,
                size: 18,
                color: active ? scheme.primary : scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  active ? '使用中のPC' : 'PC接続済み',
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
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (!active)
                TextButton.icon(
                  icon: const Icon(Icons.check, size: 16),
                  label: const Text('使用'),
                  onPressed: onUse,
                ),
              TextButton.icon(
                icon: const Icon(Icons.link_off, size: 16),
                label: const Text('切断'),
                onPressed: onUnpair,
                style: TextButton.styleFrom(foregroundColor: scheme.error),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MobileProviderCard extends StatelessWidget {
  const _MobileProviderCard({
    required this.provider,
    required this.active,
    required this.onUse,
    required this.onEdit,
  });

  final MobileProviderConfig provider;
  final bool active;
  final VoidCallback onUse;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final configured = provider.isConfigured;
    final supported = provider.baseUrl.trim().isNotEmpty &&
        (provider.openaiCompatible || provider.providerId == 'anthropic');
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: active
              ? scheme.primary.withValues(alpha: 0.45)
              : Theme.of(context).dividerTheme.color ?? Colors.transparent,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                active ? Icons.check_circle : Icons.cloud_outlined,
                size: 18,
                color: active ? scheme.primary : scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  provider.effectiveLabel,
                  style: Theme.of(context).textTheme.titleSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              _StatusPill(
                label: configured ? 'Key保存済み' : '未設定',
                active: configured,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            [
              if (provider.displayName.isNotEmpty) provider.displayName,
              provider.model,
            ].where((part) => part.trim().isNotEmpty).join(' · '),
            style: Theme.of(context).textTheme.bodySmall,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          if (!supported) ...[
            const SizedBox(height: 4),
            Text(
              'このproviderはスマホ単体の送信URLをPCから取得できていません',
              style: TextStyle(fontSize: 12, color: scheme.error),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton.icon(
                icon: const Icon(Icons.key_outlined, size: 16),
                label: const Text('API Key'),
                onPressed: onEdit,
              ),
              TextButton.icon(
                icon: const Icon(Icons.check, size: 16),
                label: const Text('使用'),
                onPressed: configured && supported && !active ? onUse : null,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ProviderHintCard extends StatelessWidget {
  const _ProviderHintCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Theme.of(context).dividerTheme.color ?? Colors.transparent,
        ),
      ),
      child: const Row(
        children: [
          Icon(Icons.cloud_download_outlined),
          SizedBox(width: 10),
          Expanded(
            child: Text('PC接続後に「PCからプロバイダー/モデルを取得」を押すとprovider一覧が入ります。'),
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.active});

  final String label;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = active ? scheme.primary : scheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, color: color),
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

List<String> _stringList(Object? value, {List<String> fallback = const []}) {
  if (value is! List) return fallback;
  return value
      .map((e) => e.toString())
      .where((e) => e.trim().isNotEmpty)
      .toList();
}

class _MiniTag extends StatelessWidget {
  const _MiniTag({required this.icon});
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Icon(icon, size: 14, color: Theme.of(context).colorScheme.outline);
  }
}
