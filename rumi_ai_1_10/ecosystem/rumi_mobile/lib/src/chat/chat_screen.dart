import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../application/conversation_router.dart';
import '../data/local/local_chat_backend.dart';
import '../data/pc/device_store.dart';
import '../data/pc/pc_chat_backend.dart';
import '../domain/chat_event.dart';
import '../domain/connection_state.dart';
import '../domain/conversation_locator.dart';
import '../domain/space.dart';
import '../features/chat/connection_chip.dart';
import '../settings/api_config_store.dart';
import '../settings/settings_screen.dart';
import '../app_theme.dart';
import 'chat_drawer.dart';
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
  bool _loadingPc = false;
  List<PairedDevice> _pairedDevices = [];

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
    }
  }

  Future<void> _loadPcConversations() async {
    final space = _spaces.where((s) => s.id == _activeSpaceId).firstOrNull;
    if (space == null || !space.isPc) {
      _pcConversations = [];
      return;
    }
    final connection = space.pcConnection;
    if (connection == null || !connection.isConfigured) {
      _pcConversations = [];
      return;
    }
    setState(() => _loadingPc = true);
    try {
      final backend = PcConversationBackend(
          connection: connection, deviceId: space.deviceId);
      final summaries = await backend.listConversations();
      backend.close();
      if (!mounted) return;
      setState(() {
        _pcConversations = summaries
            .map((s) => PcConversationItem(
                  id: s.id,
                  title: s.title,
                  messageCount: s.messageCount,
                  updatedAt: s.updatedAt,
                  pinned: s.pinned,
                  preview: '',
                ))
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
    });
    if (spaceId != Space.local.id) {
      await _loadPcConversations();
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

  void _onScroll() {}

  void _scrollToBottom({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final max = _scrollController.position.maxScrollExtent;
      if (animate) {
        _scrollController.animateTo(max,
            duration: const Duration(milliseconds: 180), curve: Curves.easeOut);
      } else {
        _scrollController.jumpTo(max);
      }
    });
  }

  Future<void> _newChat() async {
    await widget.store.createAndPersist();
    if (mounted) setState(() {});
  }

  Future<void> _select(String id) async {
    await widget.store.select(id);
    if (mounted) setState(() {});
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
              child: const Text('キャンセル')),
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
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => SettingsScreen(
        configStore: widget.configStore,
        deviceStore: widget.deviceStore,
        onApiChanged: (next) {
          setState(() => _apiConfig = next);
        },
        onDevicePaired: (device) async {
          await _loadPcConnection();
          await _loadSpaces();
          if (mounted) setState(() {});
        },
      ),
    ));
    final refreshed = await widget.configStore.loadApi();
    await _loadPcConnection();
    await _loadSpaces();
    if (mounted) setState(() => _apiConfig = refreshed);
  }

  Future<void> _send(String text) async {
    if (text.trim().isEmpty) return;
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

  void _stop() {
    final id = widget.store.active?.id;
    if (id != null) {
      _router.local.stop(id);
    }
    setState(() => _streaming = false);
  }

  void _promptConfigure() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('APIを設定してください'),
        action: SnackBarAction(
          label: '設定',
          onPressed: _openSettings,
        ),
      ),
    );
  }

  String _activeSpaceLabel() {
    final space = _spaces.where((s) => s.id == _activeSpaceId).firstOrNull;
    if (space == null) return '';
    if (space.isLocal) return 'このスマホ';
    return space.isOffline ? '${space.label} — オフライン' : space.label;
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
              activeId: widget.store.active?.id,
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
                  widget.store.active?.title ?? 'Rumi',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  _activeSpaceLabel(),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w400,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            actions: [
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
    final convo = widget.store.active;
    if (convo == null || convo.messages.isEmpty) {
      return _EmptyState(onSuggest: _send, busy: _busy);
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
          busy: _streaming,
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onSuggest, required this.busy});
  final ValueChanged<String> onSuggest;
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
                  child: const Icon(Icons.auto_awesome,
                      color: Colors.white, size: 28),
                ),
                const SizedBox(height: 16),
                Text('Rumiへようこそ',
                    style: theme.textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text('何でも聞いてください。スマホ単体でも動作します。',
                    style: theme.textTheme.bodySmall),
                const SizedBox(height: 24),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: _suggestions
                      .map((s) => ActionChip(
                            label: Text(s),
                            onPressed: busy ? null : () => onSuggest(s),
                          ))
                      .toList(),
                ),
              ],
            ),
          ),
        ),
        ComposerBar(onSend: onSuggest, onStop: () {}, busy: busy),
      ],
    );
  }
}
