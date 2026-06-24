import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../application/conversation_router.dart';
import '../data/local/local_chat_backend.dart';
import '../data/pc/device_store.dart';
import '../data/pc/pc_catalog.dart';
import '../data/pc/pc_catalog_client.dart';
import '../data/pc/pc_chat_backend.dart';
import '../domain/chat_event.dart';
import '../domain/connection_state.dart';
import '../domain/conversation_backend.dart';
import '../domain/conversation_locator.dart';
import '../domain/space.dart';
import '../features/chat/connection_chip.dart';
import '../settings/api_config_store.dart';
import '../settings/settings_screen.dart';
import '../app_theme.dart';
import 'chat_drawer.dart';
import 'chat_models.dart';
import 'chat_store.dart';
import 'composer_bar.dart';
import 'message_view.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.store,
    required this.configStore,
    required this.deviceStore,
  });

  final ChatStore store;
  final ApiConfigStore configStore;
  final MobileDeviceStore deviceStore;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _uuid = const Uuid();
  final _scrollController = ScrollController();
  ApiConfig? _apiConfig;
  late final ConversationRouter _router;
  PcConversationBackend? _pcBackend;
  PairedDevice? _pairedDevice;
  DeviceConnectionView _connectionView = DeviceConnectionView.unpaired;
  bool _busy = false;
  bool _streaming = false;
  late Future<void> _initFuture;

  List<Space> _spaces = [Space.local];
  String _activeSpaceId = Space.local.id;
  List<PcConversationItem> _pcConversations = [];
  ConversationSnapshot? _activePcSnapshot;
  bool _loadingPc = false;
  List<PairedDevice> _pairedDevices = [];
  PcCatalog? _pcCatalog;
  bool _loadingPcCatalog = false;
  String? _selectedPcModel;
  String _pcThinkingLevel = 'medium';
  bool _pcDeepthinkEnabled = false;
  String _pcMode = 'chat';
  bool _pcYoloMode = false;
  bool _pcUltraYoloMode = false;

  @override
  void initState() {
    super.initState();
    _router = ConversationRouter(
      local: LocalConversationBackend(
        store: widget.store,
        configStore: widget.configStore,
      ),
    );
    _initFuture = _init();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _router.local.dispose();
    _pcBackend?.close();
    super.dispose();
  }

  Future<void> _init() async {
    try {
      await widget.store.load();
      _apiConfig = await widget.configStore.loadApi();
      final active = widget.store.active;
      if (active == null) {
        await widget.store.createAndPersist();
      }
      await _loadPcConnection();
      await _loadSpaces();
    } catch (error, stack) {
      debugPrint('Rumi init error: $error\n$stack');
    }
    if (mounted) setState(() {});
  }

  Future<void> _loadSpaces() async {
    _pairedDevices = await widget.deviceStore.loadPairedDevices();
    final spaces = <Space>[Space.local];
    for (final device in _pairedDevices) {
      spaces.add(Space.fromPairedDevice(device));
    }
    _spaces = spaces;
    if (!_spaces.any((s) => s.id == _activeSpaceId)) {
      _activeSpaceId = Space.local.id;
    }
    if (_activeSpaceId != Space.local.id) {
      await _loadPcConversations();
      await _loadPcCatalogForActiveSpace();
    } else {
      _pcCatalog = null;
    }
  }

  Future<void> _loadPcConversations() async {
    final space = _activeSpace();
    if (space == null || !space.isPc) {
      _pcConversations = [];
      return;
    }
    final backend = _ensurePcBackendForSpace(space);
    if (backend == null) {
      _pcConversations = [];
      return;
    }
    setState(() => _loadingPc = true);
    try {
      final summaries = await backend.listConversations();
      if (!mounted) return;
      setState(() {
        _pcConversations = summaries
            .map(
              (s) => PcConversationItem(
                id: s.id,
                title: s.title,
                messageCount: s.messageCount,
                updatedAt: s.updatedAt,
                pinned: s.pinned,
                preview: '',
              ),
            )
            .toList();
        _loadingPc = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pcConversations = [];
        _loadingPc = false;
      });
      _updateSpaceOffline(_activeSpaceId, true);
    }
  }

  Future<void> _loadPcCatalogForActiveSpace() async {
    final space = _activeSpace();
    final connection = space?.pcConnection;
    if (space == null || !space.isPc || connection == null) {
      _pcCatalog = null;
      return;
    }
    if (!connection.isConfigured) return;
    if (mounted) setState(() => _loadingPcCatalog = true);
    final client = PcCatalogClient();
    try {
      final catalog = await client.fetchCapabilities(connection);
      final selected = _initialPcModelForCatalog(catalog);
      if (!mounted) return;
      setState(() {
        _pcCatalog = catalog;
        _selectedPcModel = selected;
        _pcThinkingLevel = catalog.runtime.thinkingLevel;
        _pcDeepthinkEnabled = catalog.runtime.deepthinkEnabled;
        _loadingPcCatalog = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _pcCatalog = null;
        _loadingPcCatalog = false;
      });
    } finally {
      client.close();
    }
  }

  String? _initialPcModelForCatalog(PcCatalog catalog) {
    final preferred = catalog.runtime.preferredModel.trim();
    final preferredProfile =
        preferred.isEmpty ? null : catalog.profileById(preferred);
    if (preferredProfile != null &&
        preferredProfile.effectiveProfileId != 'stub/default' &&
        (preferredProfile.configured || preferredProfile.local)) {
      return preferredProfile.effectiveProfileId;
    }
    final usable = catalog.selectableProfiles
        .where((p) => p.configured || p.local)
        .toList();
    for (final profile in usable) {
      if (profile.effectiveProfileId != 'stub/default' &&
          profile.providerId != 'stub') {
        return profile.effectiveProfileId;
      }
    }
    if (preferredProfile != null) return preferredProfile.effectiveProfileId;
    return usable.isNotEmpty ? usable.first.effectiveProfileId : null;
  }

  void _updateSpaceOffline(String spaceId, bool offline) {
    _spaces = _spaces
        .map((s) => s.id == spaceId ? s.copyWith(online: !offline) : s)
        .toList();
  }

  Future<void> _selectSpace(String spaceId) async {
    if (spaceId == _activeSpaceId) return;
    setState(() {
      _activeSpaceId = spaceId;
      _pcConversations = [];
      _activePcSnapshot = null;
      _pcCatalog = null;
    });
    if (spaceId != Space.local.id) {
      await _loadPcConversations();
      await _loadPcCatalogForActiveSpace();
    }
    if (mounted) setState(() {});
  }

  Future<void> _loadPcConnection() async {
    final paired = await widget.deviceStore.loadPairedDevice();
    if (paired != null && paired.deviceToken.isNotEmpty) {
      final pc = paired.toPcConnection();
      _pcBackend?.close();
      _pcBackend = PcConversationBackend(
        connection: pc,
        deviceId: paired.deviceId,
      );
      _router.setPc(_pcBackend!);
      _pairedDevice = paired;
      _connectionView = DeviceConnectionView(
        pairingState: PairingState.paired,
        pcConnectionState: PcConnectionState.online,
        canReadPcConversations: paired.canReadPcConversations,
        canWritePcConversations: paired.canWritePcConversations,
        canObservePcTools: paired.canObservePcTools,
        canApprovePcTools: paired.canApprovePcTools,
        canRequestCredentialCopy: paired.canRequestCredentialCopy,
      );
    } else {
      _pcBackend?.close();
      _pcBackend = null;
      _router.setPc(null);
      _pairedDevice = null;
      _connectionView = DeviceConnectionView.unpaired;
    }
  }

  Space? _activeSpace() {
    for (final space in _spaces) {
      if (space.id == _activeSpaceId) return space;
    }
    return Space.local;
  }

  bool get _activeSpaceIsPc => _activeSpace()?.isPc ?? false;

  PcConversationBackend? _ensurePcBackendForSpace(Space space) {
    final connection = space.pcConnection;
    if (connection == null || !connection.isConfigured) return null;
    final current = _pcBackend;
    if (current != null &&
        current.connection.baseUrl == connection.baseUrl &&
        current.connection.token == connection.token &&
        current.deviceId == space.deviceId) {
      _router.setPc(current);
      return current;
    }
    _pcBackend?.close();
    final backend = PcConversationBackend(
      connection: connection,
      deviceId: space.deviceId,
    );
    _pcBackend = backend;
    _router.setPc(backend);
    return backend;
  }

  Conversation? _displayConversation() {
    if (_activeSpaceIsPc) return _activePcSnapshot?.conversation;
    return widget.store.active;
  }

  String? _displayActiveId() {
    if (_activeSpaceIsPc) return _activePcSnapshot?.locator.conversationId;
    return widget.store.active?.id;
  }

  void _onScroll() {}

  void _scrollToBottom({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final max = _scrollController.position.maxScrollExtent;
      if (animate) {
        _scrollController.animateTo(
          max,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      } else {
        _scrollController.jumpTo(max);
      }
    });
  }

  Future<void> _newChat() async {
    if (_activeSpaceIsPc) {
      final space = _activeSpace();
      if (space == null) return;
      final backend = _ensurePcBackendForSpace(space);
      if (backend == null) {
        _promptPcConfigure();
        return;
      }
      try {
        final locator = await backend.createConversation(
          CreateConversationRequest(
            authority: ConversationAuthorityKind.pc,
            deviceId: space.deviceId,
          ),
        );
        final snapshot = await backend.getConversation(locator);
        if (!mounted) return;
        setState(() => _activePcSnapshot = snapshot);
        await _loadPcConversations();
      } catch (e) {
        _updateSpaceOffline(_activeSpaceId, true);
        if (mounted) setState(() {});
      }
      return;
    }
    await widget.store.createAndPersist();
    if (mounted) setState(() {});
  }

  Future<void> _select(String id) async {
    if (_activeSpaceIsPc) {
      await _selectPcConversation(id);
      return;
    }
    await widget.store.select(id);
    if (mounted) setState(() {});
  }

  Future<void> _selectPcConversation(String id) async {
    final space = _activeSpace();
    if (space == null) return;
    final backend = _ensurePcBackendForSpace(space);
    if (backend == null) {
      _promptPcConfigure();
      return;
    }
    try {
      final locator = ConversationLocator.pc(id, deviceId: space.deviceId);
      final snapshot = await backend.getConversation(locator);
      if (!mounted) return;
      setState(() => _activePcSnapshot = snapshot);
      _scrollToBottom(animate: false);
    } catch (e) {
      _updateSpaceOffline(_activeSpaceId, true);
      if (mounted) setState(() {});
    }
  }

  Future<void> _reconnectActiveSpace() async {
    _updateSpaceOffline(_activeSpaceId, false);
    if (mounted) setState(() {});
    await _loadPcConversations();
  }

  Future<void> _continuePcConversationLocally() async {
    final snapshot = _activePcSnapshot;
    if (snapshot == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('コピーできるPC会話がありません')));
      return;
    }
    final local = await widget.store.createAndPersist();
    await widget.store.rename(local.id, snapshot.conversation.title);
    for (final message in snapshot.conversation.messages) {
      await widget.store.addMessage(local.id, message.copy());
    }
    setState(() {
      _activeSpaceId = Space.local.id;
      _activePcSnapshot = null;
    });
  }

  Future<void> _delete(String id) async {
    await widget.store.delete(id);
    if (mounted) setState(() {});
  }

  Future<void> _pin(String id) async {
    await widget.store.togglePin(id);
    if (mounted) setState(() {});
  }

  Future<void> _rename(String id) async {
    final convo = widget.store.conversations.firstWhere((c) => c.id == id);
    final controller = TextEditingController(text: convo.title);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('名前を変更'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'チャット名'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (result != null) {
      await widget.store.rename(id, result);
      if (mounted) setState(() {});
    }
  }

  void _openSettings() async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => SettingsScreen(
          configStore: widget.configStore,
          deviceStore: widget.deviceStore,
          onApiChanged: (next) {
            setState(() => _apiConfig = next);
          },
          onDevicePaired: (device) async {
            await _loadPcConnection();
            _activeSpaceId =
                device == null ? Space.local.id : 'pc:${device.deviceId}';
            await _loadSpaces();
            if (mounted) setState(() {});
          },
        ),
      ),
    );
    final refreshed = await widget.configStore.loadApi();
    await _loadPcConnection();
    await _loadSpaces();
    if (mounted) setState(() => _apiConfig = refreshed);
  }

  Future<void> _send(String text) async {
    if (text.trim().isEmpty) return;
    if (await _tryExecuteSlashCommand(text)) return;
    if (_activeSpaceIsPc) {
      await _sendToPc(text);
      return;
    }
    final config = _apiConfig;
    if (config == null || !config.isConfigured) {
      _promptConfigure();
      return;
    }

    final convo = widget.store.active ?? await widget.store.createAndPersist();
    final locator = ConversationLocator.local(convo.id);
    final clientMessageId = _uuid.v4();
    final expectedRevision = convo.revision;

    setState(() {
      _busy = true;
      _streaming = true;
    });
    _scrollToBottom();

    final backend = _router.backendFor(locator);
    try {
      await for (final event in backend.sendMessage(
        locator: locator,
        text: text,
        clientMessageId: clientMessageId,
        expectedRevision: expectedRevision,
        model: _activeModelId(),
      )) {
        if (!mounted) break;
        switch (event) {
          case ChatDelta():
            setState(() {});
            _scrollToBottom(animate: false);
            break;
          case ChatErrorEvent():
            break;
          case ChatRunStarted():
          case ChatMessageCommitted():
          case ChatRunCompleted():
          case ChatRunStopped():
          case ToolCallEvent():
          case ApprovalEvent():
            break;
        }
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _streaming = false;
        });
      }
    }
    if (mounted) setState(() {});
  }

  Future<void> _sendToPc(String text) async {
    final space = _activeSpace();
    if (space == null) return;
    final backend = _ensurePcBackendForSpace(space);
    if (backend == null) {
      _promptPcConfigure();
      return;
    }

    var snapshot = _activePcSnapshot;
    if (snapshot == null) {
      final locator = await backend.createConversation(
        CreateConversationRequest(
          authority: ConversationAuthorityKind.pc,
          deviceId: space.deviceId,
        ),
      );
      snapshot = await backend.getConversation(locator);
      if (!mounted) return;
      setState(() => _activePcSnapshot = snapshot);
    }
    final locator = snapshot.locator;
    final clientMessageId = _uuid.v4();
    final expectedRevision = snapshot.revision;
    _appendPcMessage(
      ChatMessage(
        id: clientMessageId,
        role: ChatRole.user,
        content: text,
        createdAt: DateTime.now(),
      ),
    );

    setState(() {
      _busy = true;
      _streaming = true;
    });
    _scrollToBottom();

    try {
      await for (final event in backend.sendMessage(
        locator: locator,
        text: text,
        clientMessageId: clientMessageId,
        expectedRevision: expectedRevision,
        model: _activeModelId(),
        profileId: _activeModelId(),
        params: _pcRequestParams(),
      )) {
        if (!mounted) break;
        _applyPcEvent(event);
        _scrollToBottom(animate: false);
      }
      try {
        final refreshed = await backend.getConversation(locator);
        if (mounted) setState(() => _activePcSnapshot = refreshed);
        await _loadPcConversations();
      } catch (_) {
        // Keep optimistic snapshot if refresh fails.
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _streaming = false;
        });
      }
    }
  }

  void _appendPcMessage(ChatMessage message) {
    final snapshot = _activePcSnapshot;
    if (snapshot == null) return;
    final messages = snapshot.conversation.messages;
    if (messages.any((m) => m.id == message.id)) return;
    setState(() {
      messages.add(message);
      snapshot.conversation.revision += 1;
      snapshot.conversation.updatedAt = DateTime.now();
    });
  }

  void _updatePcMessage(
    String id,
    String content, {
    bool? pending,
    bool? error,
  }) {
    final snapshot = _activePcSnapshot;
    if (snapshot == null) return;
    final messages = snapshot.conversation.messages;
    final matches = messages.where((m) => m.id == id);
    if (matches.isEmpty) return;
    final message = matches.first;
    setState(() {
      message.content = content;
      if (pending != null) message.pending = pending;
      if (error != null) message.error = error;
      snapshot.conversation.updatedAt = DateTime.now();
    });
  }

  void _applyPcEvent(ChatEvent event) {
    switch (event) {
      case ChatRunStarted():
        _appendPcMessage(
          ChatMessage(
            id: event.assistantMessageId,
            role: ChatRole.assistant,
            content: '',
            createdAt: DateTime.now(),
            pending: true,
          ),
        );
        break;
      case ChatDelta():
        _updatePcMessage(
          event.assistantMessageId,
          event.accumulatedContent,
          pending: true,
        );
        break;
      case ChatMessageCommitted():
        _updatePcMessage(
          event.messageId,
          event.content,
          pending: false,
          error: event.error,
        );
        break;
      case ChatErrorEvent():
        final assistantId = event.assistantMessageId;
        if (assistantId != null) {
          _updatePcMessage(
            assistantId,
            event.message,
            pending: false,
            error: true,
          );
        }
        break;
      case ChatRunCompleted():
      case ChatRunStopped():
      case ToolCallEvent():
      case ApprovalEvent():
        break;
    }
  }

  void _stop() {
    if (_activeSpaceIsPc) {
      final locator = _activePcSnapshot?.locator;
      if (locator != null) {
        unawaited(_router.backendFor(locator).stop(locator.conversationId));
      }
      setState(() => _streaming = false);
      return;
    }
    final id = widget.store.active?.id;
    if (id != null) {
      unawaited(_router.local.stop(id));
    }
    setState(() => _streaming = false);
  }

  void _promptConfigure() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('APIを設定してください'),
        action: SnackBarAction(label: '設定', onPressed: _openSettings),
      ),
    );
  }

  void _promptPcConfigure() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('PCとペアリングしてください'),
        action: SnackBarAction(label: '設定', onPressed: _openSettings),
      ),
    );
  }

  Map<String, dynamic> _pcRequestParams() {
    final profile = _activePcProfile();
    final params = <String, dynamic>{
      'deepthink_enabled': _pcDeepthinkEnabled,
      'tool_selection': const {
        'mode': 'auto',
        'include': <String>[],
        'exclude': <String>[],
        'scope': 'turn',
        'must_use': false,
      },
      'metadata': {'mode': _pcMode},
    };
    if (profile?.supportsThinking ?? true) {
      params['thinking_level'] = _pcThinkingLevel;
    }
    if (_pcYoloMode || _pcUltraYoloMode) {
      params['tool_policy'] = {
        'yolo_mode': true,
        'allow_shell': true,
        'allow_file_write': true,
        'write_actions_require_approval': false,
      };
    }
    return params;
  }

  Future<bool> _tryExecuteSlashCommand(String text) async {
    final trimmed = text.trim();
    if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return false;
    if (_activeSpaceIsPc) {
      final catalog = await _ensurePcCatalog();
      final parsed = _parsePcSlashCommand(trimmed, catalog?.commands ?? []);
      if (parsed == null) {
        _showSnack('未登録のPC commandです');
        return true;
      }
      await _executePcCommand(parsed.command, args: parsed.args);
      return true;
    }
    final localModelMatch =
        RegExp(r'^/models?(?:\s+(.+))?$', caseSensitive: false)
            .firstMatch(trimmed);
    if (localModelMatch != null) {
      final model = (localModelMatch.group(1) ?? '').trim();
      if (model.isEmpty) {
        await _openModelPicker();
      } else {
        await _setLocalModel(model);
      }
      return true;
    }
    _showSnack('このスマホでは /model に対応しています');
    return true;
  }

  Future<PcCatalog?> _ensurePcCatalog() async {
    if (!_activeSpaceIsPc) return null;
    if (_pcCatalog != null) return _pcCatalog;
    await _loadPcCatalogForActiveSpace();
    return _pcCatalog;
  }

  Future<void> _openComposerOptions() async {
    if (_activeSpaceIsPc) {
      await _ensurePcCatalog();
    }
    if (!mounted) return;
    final catalog = _pcCatalog;
    final commands = _activeSpaceIsPc
        ? (catalog?.commands ?? const <PcCommandItem>[])
            .where((c) => c.enabled && c.visibility != 'hidden')
            .toList()
        : const <PcCommandItem>[];
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) {
        final theme = Theme.of(context);
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
          shrinkWrap: true,
          children: [
            Text('オプション', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.model_training_outlined),
              title: const Text('モデル'),
              subtitle: Text(_activeModelLabel()),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(_openModelPicker());
              },
            ),
            if (_activeSpaceIsPc) ...[
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('DeepThink'),
                subtitle: const Text('PCのDeepThink設定'),
                value: _pcDeepthinkEnabled,
                onChanged: (value) {
                  Navigator.of(context).pop();
                  unawaited(_setPcDeepthink(value));
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.psychology_alt_outlined),
                title: const Text('Thinking level'),
                subtitle: Text(_pcThinkingLevel),
              ),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final level in const [
                    'none',
                    'low',
                    'medium',
                    'high',
                    'xhigh',
                  ])
                    ChoiceChip(
                      label: Text(level),
                      selected: _pcThinkingLevel == level,
                      onSelected: (_) {
                        Navigator.of(context).pop();
                        unawaited(_setPcThinkingLevel(level));
                      },
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text('/ commands', style: theme.textTheme.titleSmall),
              if (_loadingPcCatalog)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: LinearProgressIndicator(),
                ),
              for (final command in commands)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  leading: Icon(_iconForCommand(command)),
                  title: Text(command.label),
                  subtitle: Text(
                    '/${command.name}${command.args.isEmpty ? "" : " ${command.args.map((a) => "<${a.name}>").join(" ")}"}',
                  ),
                  trailing: command.active
                      ? const Icon(Icons.check_circle, size: 18)
                      : null,
                  onTap: () {
                    Navigator.of(context).pop();
                    unawaited(_runPcCommandFromMenu(command));
                  },
                ),
            ] else ...[
              const SizedBox(height: 12),
              Text('/ commands', style: theme.textTheme.titleSmall),
              ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                leading: const Icon(Icons.model_training_outlined),
                title: const Text('Model'),
                subtitle: const Text('/model <name>'),
                onTap: () {
                  Navigator.of(context).pop();
                  unawaited(_openModelPicker());
                },
              ),
            ],
          ],
        );
      },
    );
  }

  Future<void> _openModelPicker() async {
    if (_activeSpaceIsPc) {
      final catalog = await _ensurePcCatalog();
      if (!mounted) return;
      final profiles = catalog?.selectableProfiles ?? const <ProfileEntry>[];
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        useSafeArea: true,
        builder: (context) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
            children: [
              Text('モデルを選択', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (profiles.isEmpty)
                const ListTile(title: Text('PCからモデル一覧を取得できませんでした')),
              for (final profile in profiles)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  enabled: profile.configured || profile.local,
                  leading: Icon(
                    profile.supportsVision
                        ? Icons.visibility_outlined
                        : Icons.smart_toy_outlined,
                  ),
                  title: Text(profile.displayLabel),
                  subtitle: Text(
                    [
                      profile.providerDisplayName.isNotEmpty
                          ? profile.providerDisplayName
                          : profile.providerId,
                      profile.modelId,
                      if (profile.maxContext > 0)
                        '${(profile.maxContext / 1000).round()}k',
                    ].where((part) => part.isNotEmpty).join(' · '),
                  ),
                  trailing: profile.effectiveProfileId == _activeModelId()
                      ? const Icon(Icons.check)
                      : null,
                  onTap: profile.configured || profile.local
                      ? () {
                          Navigator.of(context).pop();
                          unawaited(_setPcModel(profile.effectiveProfileId));
                        }
                      : null,
                ),
            ],
          );
        },
      );
      return;
    }
    final controller = TextEditingController(text: _activeModelId());
    final selected = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('このスマホのモデル'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'model',
            hintText: 'gpt-4o-mini',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (selected != null && selected.trim().isNotEmpty) {
      await _setLocalModel(selected.trim());
    }
  }

  Future<void> _setLocalModel(String model) async {
    final current = _apiConfig ?? await widget.configStore.loadApi();
    final next = current.copyWith(model: model.trim());
    await widget.configStore.saveApi(next);
    if (!mounted) return;
    setState(() => _apiConfig = next);
    _showSnack('このスマホのモデルを ${next.model} にしました');
  }

  Future<void> _setPcModel(String profileId) async {
    final space = _activeSpace();
    final connection = space?.pcConnection;
    if (connection == null || !connection.isConfigured) {
      _promptPcConfigure();
      return;
    }
    setState(() => _selectedPcModel = profileId);
    final client = PcCatalogClient();
    try {
      final result = await client.executeCommand(
        connection,
        command: 'model',
        args: {'query': profileId},
        conversationId: _activePcSnapshot?.locator.conversationId,
        mode: _pcMode,
      );
      await _handlePcCommandResult(
        PcCommandItem.fromJson(<String, dynamic>{
          'id': 'model',
          'name': 'model',
          'label': 'Model',
          'category': 'model',
          'visibility': 'default',
          'risk': 'low',
          'execution': {
            'type': 'model_command',
            'action': 'select_or_suggest_model'
          },
        }),
        result,
      );
    } catch (e) {
      _showSnack('PCモデル設定に失敗しました: $e');
    } finally {
      client.close();
    }
  }

  Future<void> _setPcThinkingLevel(String level) async {
    setState(() => _pcThinkingLevel = level);
    final command = _pcCatalog?.commands.firstWhere(
      (c) => c.id == 'think' || c.name == 'think',
      orElse: () => PcCommandItem.fromJson(<String, dynamic>{
        'id': 'think',
        'name': 'think',
        'label': 'Thinking Level',
        'category': 'model',
        'visibility': 'default',
        'risk': 'low',
        'args': [
          {'name': 'level', 'type': 'enum'}
        ],
        'execution': {
          'type': 'rumi_function',
          'qualified_name': 'defaultspack:ai_set_thinking_level'
        },
      }),
    );
    if (command != null) {
      await _executePcCommand(command, args: {
        'level': level,
        'scope': 'profile',
        'profile_id': _activeModelId(),
      });
      if (mounted) setState(() => _pcThinkingLevel = level);
    }
  }

  Future<void> _setPcDeepthink(bool enabled) async {
    setState(() => _pcDeepthinkEnabled = enabled);
    final command = _pcCatalog?.commands.firstWhere(
      (c) => c.id == 'deepthink' || c.name == 'deepthink',
      orElse: () => PcCommandItem.fromJson(<String, dynamic>{
        'id': 'deepthink',
        'name': 'deepthink',
        'label': 'DeepThink',
        'category': 'model',
        'visibility': 'default',
        'risk': 'medium',
        'args': [
          {'name': 'enabled', 'type': 'boolean'}
        ],
        'execution': {
          'type': 'rumi_function',
          'qualified_name': 'defaultspack:ai_set_deepthink_enabled'
        },
      }),
    );
    if (command != null) {
      await _executePcCommand(command, args: {'enabled': enabled});
    }
  }

  Future<void> _runPcCommandFromMenu(PcCommandItem command) async {
    if (command.isModelCommand) {
      await _openModelPicker();
      return;
    }
    final args = await _collectPcCommandArgs(command);
    if (args == null) return;
    await _executePcCommand(command, args: args);
  }

  Future<Map<String, dynamic>?> _collectPcCommandArgs(
    PcCommandItem command,
  ) async {
    if (command.args.isEmpty) return const {};
    if (!mounted) return null;
    if (command.args.length == 1) {
      final arg = command.args.first;
      if (arg.type == 'enum' && arg.values.isNotEmpty) {
        final picked = await showModalBottomSheet<String>(
          context: context,
          showDragHandle: true,
          useSafeArea: true,
          builder: (context) => ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
            children: [
              Text(
                '/${command.name} ${arg.name}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (!arg.required)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('そのまま実行'),
                  onTap: () => Navigator.pop(context, ''),
                ),
              for (final value in arg.values)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(value),
                  onTap: () => Navigator.pop(context, value),
                ),
            ],
          ),
        );
        if (picked == null) return null;
        return picked.isEmpty ? const {} : {arg.name: picked};
      }
      if (arg.type == 'boolean') {
        final picked = await showModalBottomSheet<String>(
          context: context,
          showDragHandle: true,
          useSafeArea: true,
          builder: (context) => ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
            children: [
              Text(
                '/${command.name} ${arg.name}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (!arg.required)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('切り替え'),
                  onTap: () => Navigator.pop(context, 'toggle'),
                ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('ON'),
                onTap: () => Navigator.pop(context, 'true'),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('OFF'),
                onTap: () => Navigator.pop(context, 'false'),
              ),
            ],
          ),
        );
        if (picked == null) return null;
        if (picked == 'toggle') return const {};
        return {arg.name: picked == 'true'};
      }
    }

    final controllers = {
      for (final arg in command.args) arg.name: TextEditingController()
    };
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('/${command.name}'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final arg in command.args)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextField(
                    controller: controllers[arg.name],
                    decoration: InputDecoration(
                      labelText: arg.required ? '${arg.name} *' : arg.name,
                      helperText:
                          arg.values.isEmpty ? null : arg.values.join(', '),
                    ),
                  ),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            onPressed: () {
              final values = <String, dynamic>{};
              for (final arg in command.args) {
                final value = controllers[arg.name]?.text.trim() ?? '';
                if (value.isNotEmpty) values[arg.name] = value;
              }
              Navigator.pop(context, values);
            },
            child: const Text('実行'),
          ),
        ],
      ),
    );
    for (final controller in controllers.values) {
      controller.dispose();
    }
    return result;
  }

  Future<void> _executePcCommand(
    PcCommandItem command, {
    Map<String, dynamic> args = const {},
  }) async {
    final space = _activeSpace();
    final connection = space?.pcConnection;
    if (connection == null || !connection.isConfigured) {
      _promptPcConfigure();
      return;
    }
    final client = PcCatalogClient();
    try {
      final result = await client.executeCommand(
        connection,
        command: command.name.isNotEmpty ? command.name : command.id,
        args: args,
        conversationId: _activePcSnapshot?.locator.conversationId,
        mode: _pcMode,
      );
      await _handlePcCommandResult(command, result, parsedArgs: args);
    } catch (e) {
      _showSnack('PC commandに失敗しました: $e');
    } finally {
      client.close();
    }
  }

  Future<void> _handlePcCommandResult(
    PcCommandItem command,
    PcCommandExecuteResult result, {
    Map<String, dynamic> parsedArgs = const {},
  }) async {
    if (result.requiresApproval) {
      _showSnack(result.message.isNotEmpty ? result.message : '承認が必要です');
      return;
    }
    if (command.isModelCommand) {
      if (result.action == 'open_model_picker') {
        await _openModelPicker();
        return;
      }
      if (result.action == 'show_model_candidates') {
        await _openModelCandidates(result.candidates);
        return;
      }
      final selected = result.selectedModel?.effectiveProfileId;
      if (selected != null && selected.isNotEmpty) {
        setState(() => _selectedPcModel = selected);
      }
      await _loadPcCatalogForActiveSpace();
    }
    final action = result.action.isNotEmpty
        ? result.action
        : command.execution['action'] as String? ?? '';
    if (action.isNotEmpty) {
      await _runPcFrontendAction(
          action, command, result.args.isEmpty ? parsedArgs : result.args);
    }
    if (command.execution['type'] == 'rumi_function') {
      await _loadPcCatalogForActiveSpace();
    }
    if (result.message.isNotEmpty) {
      _showSnack(result.message);
    }
  }

  Future<void> _openModelCandidates(List<PcModelCandidate> candidates) async {
    if (!mounted) return;
    if (candidates.isEmpty) {
      _showSnack('一致するモデルがありません');
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) => ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
        children: [
          Text('候補モデル', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final candidate in candidates)
            ListTile(
              contentPadding: EdgeInsets.zero,
              enabled: candidate.configured,
              title: Text(candidate.displayLabel),
              subtitle: Text(
                [
                  candidate.providerDisplayName.isNotEmpty
                      ? candidate.providerDisplayName
                      : candidate.providerId,
                  candidate.modelId,
                ].where((part) => part.isNotEmpty).join(' · '),
              ),
              onTap: candidate.configured
                  ? () {
                      Navigator.of(context).pop();
                      unawaited(_setPcModel(candidate.effectiveProfileId));
                    }
                  : null,
            ),
        ],
      ),
    );
  }

  Future<void> _runPcFrontendAction(
    String action,
    PcCommandItem command,
    Map<String, dynamic> args,
  ) async {
    switch (action) {
      case 'open_command_help':
        await _openComposerOptions();
        return;
      case 'open_model_picker':
        await _openModelPicker();
        return;
      case 'set_fast_mode':
        final candidate = _fastPcProfile();
        if (candidate == null) {
          _showSnack('fast対応モデルが見つかりません');
          return;
        }
        await _setPcModel(candidate.effectiveProfileId);
        if (candidate.supportsThinking) {
          await _setPcThinkingLevel('low');
        }
        return;
      case 'set_price_mode':
        final tier =
            '${args['tier'] ?? 'low'}'.toLowerCase() == 'high' ? 'high' : 'low';
        final candidate = _pricePcProfile(tier);
        if (candidate == null) {
          _showSnack('price=$tier の候補が見つかりません');
          return;
        }
        await _setPcModel(candidate.effectiveProfileId);
        return;
      case 'new_conversation':
        await _newChat();
        return;
      case 'clear_composer_state':
        _showSnack('入力をクリアしました');
        return;
      case 'set_mode_coding':
        setState(() => _pcMode = _pcMode == 'coding' ? 'agent' : 'coding');
        _showSnack('PC mode: $_pcMode');
        return;
      case 'set_mode_chat':
        setState(() => _pcMode = 'chat');
        _showSnack('PC mode: chat');
        return;
      case 'set_mode_agent':
        setState(() => _pcMode = 'agent');
        _showSnack('PC mode: agent');
        return;
      case 'toggle_yolo':
        setState(() =>
            _pcYoloMode = _parseCommandBool(args['enabled'], !_pcYoloMode));
        _showSnack('Yolo: ${_pcYoloMode ? "on" : "off"}');
        return;
      case 'toggle_ultra_yolo':
        setState(() {
          _pcUltraYoloMode =
              _parseCommandBool(args['enabled'], !_pcUltraYoloMode);
          if (_pcUltraYoloMode) _pcYoloMode = true;
        });
        _showSnack('Ultra Yolo: ${_pcUltraYoloMode ? "on" : "off"}');
        return;
      case 'show_status':
        _showSnack(
          'mode=$_pcMode model=${_activeModelLabel()} thinking=$_pcThinkingLevel deepthink=${_pcDeepthinkEnabled ? "on" : "off"}',
        );
        return;
      case 'open_settings':
        _openSettings();
        return;
      default:
        _showSnack('/${command.name} はPC commandとして取得済みです');
    }
  }

  ProfileEntry? _fastPcProfile() {
    final profiles = _pcCatalog?.selectableProfiles ?? const <ProfileEntry>[];
    for (final profile in profiles) {
      if (!profile.configured && !profile.local) continue;
      if (profile.speedTier == 'fast' ||
          profile.capabilityTags.contains('fast')) {
        return profile;
      }
    }
    return profiles.isNotEmpty ? profiles.first : null;
  }

  ProfileEntry? _pricePcProfile(String tier) {
    final profiles = _pcCatalog?.selectableProfiles ?? const <ProfileEntry>[];
    final matches = profiles.where((profile) {
      if (!profile.configured && !profile.local) return false;
      return profile.costTier == tier;
    }).toList();
    if (matches.isNotEmpty) return matches.first;
    return profiles.isNotEmpty ? profiles.first : null;
  }

  bool _parseCommandBool(Object? value, bool fallback) {
    if (value == null || value == '') return fallback;
    if (value is bool) return value;
    if (value is num) return value != 0;
    final normalized = value.toString().trim().toLowerCase();
    if (['false', '0', 'off', 'no', 'disabled'].contains(normalized)) {
      return false;
    }
    if (['true', '1', 'on', 'yes', 'enabled'].contains(normalized)) {
      return true;
    }
    return fallback;
  }

  IconData _iconForCommand(PcCommandItem command) {
    switch (command.category) {
      case 'model':
        return Icons.model_training_outlined;
      case 'mode':
        return Icons.tune_outlined;
      case 'coding':
        return Icons.code_outlined;
      case 'tools':
        return Icons.construction_outlined;
      case 'settings':
        return Icons.settings_outlined;
      default:
        return Icons.bolt_outlined;
    }
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
  }

  String _activeSpaceLabel() {
    final space = _activeSpace();
    if (space == null) return '';
    if (space.isLocal) return 'このスマホ';
    return space.isOffline ? '${space.label} — オフライン' : space.label;
  }

  String _activeModelId() {
    if (_activeSpaceIsPc) {
      final selected = (_selectedPcModel ?? '').trim();
      if (selected.isNotEmpty) return selected;
      final runtime = _pcCatalog?.runtime.preferredModel.trim() ?? '';
      if (runtime.isNotEmpty) return runtime;
      return '';
    }
    return _apiConfig?.model.trim().isNotEmpty == true
        ? _apiConfig!.model.trim()
        : ApiConfig.defaults.model;
  }

  String _activeModelLabel() {
    final modelId = _activeModelId();
    if (_activeSpaceIsPc) {
      if (modelId.isEmpty) return 'PC既定モデル';
      return _pcCatalog?.labelForProfile(modelId) ?? modelId;
    }
    return modelId;
  }

  ProfileEntry? _activePcProfile() {
    final modelId = _activeModelId();
    if (!_activeSpaceIsPc || modelId.isEmpty) return null;
    return _pcCatalog?.profileById(modelId);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _initFuture,
      builder: (context, snapshot) {
        return Scaffold(
          drawer: Drawer(
            width: 320,
            child: ChatDrawer(
              spaces: _spaces,
              activeSpaceId: _activeSpaceId,
              conversations: widget.store.conversations,
              pcConversations: _pcConversations,
              loadingPc: _loadingPc,
              activeId: _displayActiveId(),
              onNewChat: () {
                Navigator.of(context).pop();
                _newChat();
              },
              onSelectSpace: (spaceId) {
                Navigator.of(context).pop();
                _selectSpace(spaceId);
              },
              onSelect: (id) {
                Navigator.of(context).pop();
                _select(id);
              },
              onDelete: _delete,
              onRename: _rename,
              onPin: _pin,
              onReconnectSpace: () {
                Navigator.of(context).pop();
                _reconnectActiveSpace();
              },
              onContinueOffline: () {
                Navigator.of(context).pop();
                _continuePcConversationLocally();
              },
              onOpenSettings: () {
                Navigator.of(context).pop();
                _openSettings();
              },
            ),
          ),
          appBar: AppBar(
            leading: Builder(
              builder: (context) => IconButton(
                tooltip: 'チャット一覧',
                icon: const Icon(Icons.menu),
                onPressed: () => Scaffold.of(context).openDrawer(),
              ),
            ),
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _displayConversation()?.title ?? 'Rumi',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  '${_activeSpaceLabel()} · ${_activeModelLabel()}',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w400,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
            actions: [
              if (_spaces.length > 1)
                PopupMenuButton<String>(
                  tooltip: 'スマホ/PCを切り替え',
                  icon: const Icon(Icons.devices_outlined),
                  initialValue: _activeSpaceId,
                  onSelected: (spaceId) {
                    unawaited(_selectSpace(spaceId));
                  },
                  itemBuilder: (context) => [
                    for (final space in _spaces)
                      CheckedPopupMenuItem<String>(
                        value: space.id,
                        checked: space.id == _activeSpaceId,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              space.isLocal
                                  ? Icons.phone_android
                                  : Icons.desktop_windows,
                              size: 18,
                            ),
                            const SizedBox(width: 8),
                            Text(space.label),
                          ],
                        ),
                      ),
                  ],
                ),
              ConnectionChip(
                connectionView: _connectionView,
                pairedDevice: _pairedDevice,
                onTap: _openSettings,
              ),
              const SizedBox(width: 4),
              IconButton(
                tooltip: '新規チャット',
                icon: const Icon(Icons.add_comment_outlined),
                onPressed: _newChat,
              ),
              IconButton(
                tooltip: '設定',
                icon: const Icon(Icons.settings_outlined),
                onPressed: _openSettings,
              ),
            ],
          ),
          body: _buildBody(snapshot),
        );
      },
    );
  }

  Widget _buildBody(AsyncSnapshot<void> snapshot) {
    if (snapshot.connectionState != ConnectionState.done) {
      return const Center(child: CircularProgressIndicator());
    }
    final convo = _displayConversation();
    if (convo == null || convo.messages.isEmpty) {
      return _EmptyState(
        onSuggest: _send,
        onAdd: _openComposerOptions,
        busy: _busy,
      );
    }
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(vertical: 12),
            itemCount: convo.messages.length,
            itemBuilder: (context, index) {
              final message = convo.messages[index];
              return MessageView(key: ValueKey(message.id), message: message);
            },
          ),
        ),
        ComposerBar(
          onSend: _send,
          onStop: _stop,
          onAdd: _openComposerOptions,
          busy: _streaming,
        ),
      ],
    );
  }
}

class _ParsedPcCommand {
  const _ParsedPcCommand({required this.command, required this.args});

  final PcCommandItem command;
  final Map<String, dynamic> args;
}

_ParsedPcCommand? _parsePcSlashCommand(
  String input,
  List<PcCommandItem> commands,
) {
  final trimmed = input.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null;
  final body = trimmed.substring(1).trim();
  if (body.isEmpty) return null;
  final normalizedBody = body.toLowerCase();

  PcCommandItem? matchedCommand;
  var matchedName = '';
  for (final command in commands) {
    for (final name in _pcCommandNames(command)) {
      final candidate = _matchPcCommandName(normalizedBody, name);
      if (candidate == null || candidate.length <= matchedName.length) {
        continue;
      }
      matchedCommand = command;
      matchedName = candidate;
    }
  }
  if (matchedCommand == null) return null;

  final rest = body.substring(matchedName.length).trim();
  final args = <String, dynamic>{};
  final specs = matchedCommand.args;
  if (specs.length == 1 && rest.isNotEmpty) {
    args[specs.first.name] = rest;
  } else if (specs.length > 1 && rest.isNotEmpty) {
    final tokens = rest.split(RegExp(r'\s+'));
    for (var i = 0; i < specs.length; i++) {
      final spec = specs[i];
      if (i == specs.length - 1) {
        final remainder = tokens.skip(i).join(' ');
        if (remainder.isNotEmpty) args[spec.name] = remainder;
      } else if (i < tokens.length && tokens[i].isNotEmpty) {
        args[spec.name] = tokens[i];
      }
    }
  }
  return _ParsedPcCommand(command: matchedCommand, args: args);
}

List<String> _pcCommandNames(PcCommandItem command) {
  final names = <String>{command.id, command.name, ...command.aliases};
  final list = names
      .map((value) => value.trim().toLowerCase())
      .where((value) => value.isNotEmpty)
      .toList();
  list.sort((left, right) => right.length.compareTo(left.length));
  return list;
}

String? _matchPcCommandName(String body, String candidate) {
  final direct =
      RegExp('^${RegExp.escape(candidate)}(?:\\s+|\$)').firstMatch(body);
  if (direct != null) return direct.group(0)?.trimRight();

  final parts = candidate.split(RegExp(r'[\s_-]+')).where((p) => p.isNotEmpty);
  if (parts.length < 2) return null;
  final pattern = parts.map(RegExp.escape).join(r'[\s_-]+');
  final flexible = RegExp('^$pattern(?:\\s+|\$)').firstMatch(body);
  return flexible?.group(0)?.trimRight();
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.onSuggest,
    required this.onAdd,
    required this.busy,
  });
  final ValueChanged<String> onSuggest;
  final VoidCallback onAdd;
  final bool busy;

  static const _suggestions = [
    '今日のニュースを要約して',
    'PythonでFizzBuzzを書いて',
    'アイデア出しを手伝って',
    'この文章を校正して',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.extension<RumiColors>() ?? RumiColors.dark;
    return Column(
      children: [
        Expanded(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      color: colors.accent,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.auto_awesome,
                      color: Colors.white,
                      size: 28,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Rumiへようこそ',
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '何でも聞いてください。スマホ単体でも動作します。',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: 24),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    alignment: WrapAlignment.center,
                    children: _suggestions
                        .map(
                          (s) => ActionChip(
                            label: Text(s),
                            onPressed: busy ? null : () => onSuggest(s),
                          ),
                        )
                        .toList(),
                  ),
                ],
              ),
            ),
          ),
        ),
        ComposerBar(
          onSend: onSuggest,
          onStop: () {},
          onAdd: onAdd,
          busy: busy,
        ),
      ],
    );
  }
}
