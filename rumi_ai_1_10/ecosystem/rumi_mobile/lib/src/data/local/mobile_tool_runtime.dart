import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:uuid/uuid.dart';

import '../../platform/platform_services.dart';
import 'defaultspack_tool_agent_manifest.g.dart';

const mobileCompatibleTag = 'mobile-compatible';
const mobileFlutterTag = 'mobile-flutter';
const mobileIosTag = 'mobile-ios';
const mobileAndroidTag = 'mobile-android';
const mobileSwiftNativeTag = 'mobile-swift-native';
const mobileKotlinNativeTag = 'mobile-kotlin-native';
const mobilePcDelegatedTag = 'pc-delegated';
const mobileAgentTemplateId = 'rumi.composer.default';
const mobileAgentAiInputId = 'rumi.composer.default:default_ai_input';
const mobileAgentToolPolicyId = 'rumi.composer.default:default_tools';
const assistantProgressToolName = 'assistant_progress';
const assistantProgressDisplayName = '作業状況';
const mobileAssistantProgressSystemInstruction =
    'Internal progress tool: assistant_progress is only for short user-visible status, not reasoning. '
    'Call it at most at phase changes, important discoveries, failures, or final verification. '
    'Do not call it before every tool. Do not include hidden reasoning, analysis, or chain-of-thought. '
    'Keep summary and next_action under 120 characters. A normal external tool should occur between repeated progress updates unless you are finalizing or blocked.';

const _assistantProgressTextLimit = 120;
const _assistantProgressRelatedToolLimit = 4;
const _assistantProgressPhases = <String>{
  'inspect',
  'change',
  'verify',
  'recover',
  'finalize',
};
const _assistantProgressStatuses = <String>{
  'active',
  'completed',
  'blocked',
};
const _taskBoardDefaultColumns = <String>['Backlog', 'Doing', 'Review', 'Done'];
const _mobileConsentCategories = <String, Map<String, Object>>{
  'investment': {
    'keywords': <String>[
      '投資',
      '株',
      '株式',
      '株価',
      '銘柄',
      'ポートフォリオ',
      '資産運用',
      '利回り',
      '配当',
      '投資信託',
      'ファンド',
      'fx',
      '為替',
      '仮想通貨',
      '暗号資産',
      'ビットコイン',
      'etf',
      'nisa',
      'ideco',
      '信用取引',
      '空売り',
      'investment',
      'stock',
      'portfolio',
      'dividend',
      'fund',
      'forex',
      'crypto',
      'bitcoin',
      'trading',
    ],
    'disclaimer':
        'この回答は一般的な情報提供のみを目的としており、特定の金融商品の購入・売却を推奨するものではありません。投資判断はご自身の責任で行ってください。',
  },
  'tax': {
    'keywords': <String>[
      '税金',
      '確定申告',
      '所得税',
      '住民税',
      '消費税',
      '法人税',
      '相続税',
      '贈与税',
      '控除',
      '節税',
      '税務',
      '年末調整',
      '源泉徴収',
      '経費',
      '減価償却',
      'tax',
      'deduction',
      'income tax',
      'tax return',
    ],
    'disclaimer':
        'この回答は一般的な税務情報の提供を目的としており、個別の税務アドバイスではありません。具体的な税務判断については、税理士等の専門家にご相談ください。',
  },
  'medical': {
    'keywords': <String>[
      '診断',
      '治療',
      '処方',
      '薬',
      '服薬',
      '投薬',
      '症状',
      '病気',
      '疾患',
      '手術',
      '副作用',
      '医療',
      '医師',
      '病院',
      'クリニック',
      'diagnosis',
      'treatment',
      'prescription',
      'medication',
      'symptom',
      'disease',
      'surgery',
      'side effect',
    ],
    'disclaimer':
        'この回答は一般的な医療情報の提供を目的としており、医学的な診断・治療の代替となるものではありません。健康上の問題については、必ず医師にご相談ください。',
  },
  'legal': {
    'keywords': <String>[
      '訴訟',
      '裁判',
      '弁護士',
      '法律相談',
      '契約書',
      '損害賠償',
      '慰謝料',
      '示談',
      '告訴',
      '起訴',
      '法的',
      '判例',
      '法令',
      '条文',
      '権利',
      'lawsuit',
      'attorney',
      'legal advice',
      'contract',
      'liability',
      'damages',
      'litigation',
    ],
    'disclaimer':
        'この回答は一般的な法律情報の提供を目的としており、個別の法的アドバイスではありません。具体的な法律問題については、弁護士等の専門家にご相談ください。',
  },
};
const _defaultMobilePlatforms = <String>['ios', 'android'];
const _flutterRuntimeLayers = <String>['flutter', 'dart'];
const _nativeUrlRuntimeLayers = <String>[
  'flutter',
  'ios-swift',
  'android-kotlin',
];
const _nativeMediaPickerRuntimeLayers = <String>[
  'flutter',
  'ios-swift',
  'android-kotlin',
];
const _defaultMediaPickMaxBytes = 4 * 1024 * 1024;
const _hardMediaPickMaxBytes = 8 * 1024 * 1024;

class MobileToolDefinition {
  const MobileToolDefinition({
    required this.name,
    required this.description,
    required this.parameters,
    required this.tags,
    this.aliases = const [],
    this.unavailableReason = '',
    this.executionPlatforms = _defaultMobilePlatforms,
    this.runtimeLayers = _flutterRuntimeLayers,
    this.nativeLayers = const [],
    this.requiresMobileApproval = false,
  });

  final String name;
  final String description;
  final Map<String, dynamic> parameters;
  final List<String> tags;
  final List<String> aliases;
  final String unavailableReason;
  final List<String> executionPlatforms;
  final List<String> runtimeLayers;
  final List<String> nativeLayers;
  final bool requiresMobileApproval;

  bool get available => unavailableReason.trim().isEmpty;

  Map<String, dynamic> toOpenAiTool({String? exportedName}) => {
        'type': 'function',
        'function': {
          'name': exportedName ?? name,
          'description': description,
          'parameters': parameters,
        },
      };

  Iterable<String> get openAiNames sync* {
    final names = <String>{name, ...aliases};
    for (final candidate in names) {
      if (_isOpenAiFunctionName(candidate)) yield candidate;
    }
  }
}

const _defaultspackToolAgentManifestCatalog =
    defaultspackToolAgentManifestCatalog;

class MobileToolCall {
  const MobileToolCall({
    required this.id,
    required this.name,
    required this.arguments,
  });

  final String id;
  final String name;
  final Map<String, dynamic> arguments;
}

class MobileToolApprovalRequest {
  const MobileToolApprovalRequest({
    required this.toolName,
    required this.prompt,
    required this.arguments,
    required this.risk,
  });

  final String toolName;
  final String prompt;
  final Map<String, dynamic> arguments;
  final String risk;
}

class MobileToolResult {
  const MobileToolResult({
    required this.output,
    required this.ok,
    this.summary = '',
  });

  final String output;
  final bool ok;
  final String summary;

  String toToolMessageContent() => jsonEncode({
        'status': ok ? 'ok' : 'error',
        'summary': summary,
        'data': output,
      });
}

abstract interface class MobileToolDelegate {
  Future<MobileToolResult> invoke(MobileToolCall call);
}

abstract interface class MobileToolApprovalDelegate {
  Future<bool> approve(MobileToolApprovalRequest request);
}

class MobileToolRuntime {
  const MobileToolRuntime({
    MobileToolDelegate? pcDelegate,
    MobileToolApprovalDelegate? approvalDelegate,
    PlatformUrlLauncher urlLauncher = const PlatformUrlLauncher(),
    PlatformClipboard clipboard = const PlatformClipboard(),
    PlatformMediaPicker mediaPicker = const PlatformMediaPicker(),
  })  : _pcDelegate = pcDelegate,
        _approvalDelegate = approvalDelegate,
        _urlLauncher = urlLauncher,
        _clipboard = clipboard,
        _mediaPicker = mediaPicker;

  final MobileToolDelegate? _pcDelegate;
  final MobileToolApprovalDelegate? _approvalDelegate;
  final PlatformUrlLauncher _urlLauncher;
  final PlatformClipboard _clipboard;
  final PlatformMediaPicker _mediaPicker;

  bool get pcDelegationAvailable => _pcDelegate != null;

  static const supportedTools = <MobileToolDefinition>[
    MobileToolDefinition(
      name: 'calculator',
      description:
          'Run the defaultspack-compatible calculator tool on this phone. Use it for arithmetic only.',
      tags: ['tool', 'math', mobileCompatibleTag],
      aliases: ['tool_calculator', 'defaultspack.tool.calculator'],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'expression': {
            'type': 'string',
            'description': 'Arithmetic expression, such as "(12.5 + 3) / 2".',
          },
        },
        'required': ['expression'],
      },
    ),
    MobileToolDefinition(
      name: 'tool_consent_check',
      description:
          'Run the defaultspack consent check locally on this phone using the built-in keyword classifier.',
      tags: ['tool', 'consent', mobileCompatibleTag],
      aliases: [
        'defaults_tool_consent_check',
        'defaultspack_tool_consent_check',
        'defaults.tool.consent.check',
        'defaults.tool.consent_check',
        'defaultspack.tool.consent.check',
        'defaultspack.tool.consent_check',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'text': {'type': 'string'},
          'use_ai': {'type': 'boolean', 'default': false},
          'model': {'type': 'string'},
        },
        'required': ['text'],
      },
    ),
    MobileToolDefinition(
      name: 'tool_consent_confirm',
      description:
          'Confirm a phone-local defaultspack consent record created by tool_consent_check.',
      tags: ['tool', 'consent', mobileCompatibleTag],
      aliases: [
        'defaults_tool_consent_confirm',
        'defaultspack_tool_consent_confirm',
        'defaults.tool.consent.confirm',
        'defaults.tool.consent_confirm',
        'defaultspack.tool.consent.confirm',
        'defaultspack.tool.consent_confirm',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'consent_id': {'type': 'string'},
          'accepted': {'type': 'boolean'},
        },
        'required': ['consent_id', 'accepted'],
      },
    ),
    MobileToolDefinition(
      name: 'current_time',
      description:
          'Return the current date/time from this phone. Use for time, date, and timezone questions.',
      tags: ['tool', 'time', mobileCompatibleTag],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'format': {
            'type': 'string',
            'enum': ['iso8601', 'human'],
            'default': 'human',
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'mobile_platform_info',
      description:
          'Return this app runtime and mobile platform information, split by Flutter, iOS, Android, Swift, and Kotlin layers.',
      tags: ['tool', 'diagnostics', 'mobile', mobileCompatibleTag],
      aliases: [
        'platform_info',
        'mobile.platform.info',
        'defaultspack.mobile.platform_info',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
      },
    ),
    MobileToolDefinition(
      name: 'todo',
      description:
          'Run the defaultspack todo tool on this phone. Use it to keep a small task list during an agent turn.',
      tags: ['tool', 'planning', mobileCompatibleTag],
      aliases: ['tool_todo', 'defaultspack.tool.todo'],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'action': {
            'type': 'string',
            'enum': [
              'add',
              'create',
              'complete',
              'done',
              'update',
              'edit',
              'remove',
              'delete',
              'clear',
              'list',
              'show',
            ],
            'default': 'list',
          },
          'title': {'type': 'string'},
          'task': {'type': 'string'},
          'todo_id': {'type': 'string'},
          'id': {'type': 'string'},
          'status': {'type': 'string'},
          'priority': {'type': 'string'},
          'notes': {'type': 'string'},
        },
      },
    ),
    MobileToolDefinition(
      name: 'tool_task_board',
      description:
          'Run the defaultspack task board tool on this phone. Use it for agent planning with Kanban-style cards.',
      tags: ['tool', 'planning', 'task_board', mobileCompatibleTag],
      aliases: ['task_board', 'defaultspack.tool.task_board'],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'action': {
            'type': 'string',
            'enum': [
              'configure',
              'configure_columns',
              'create',
              'add',
              'update',
              'edit',
              'move',
              'block',
              'unblock',
              'subtask_add',
              'add_subtask',
              'subtask_update',
              'subtask_complete',
              'subtask_remove',
              'remove_subtask',
              'delete',
              'remove',
              'clear',
              'list',
              'show',
            ],
            'default': 'list',
          },
          'title': {'type': 'string'},
          'task': {'type': 'string'},
          'card_id': {'type': 'string'},
          'id': {'type': 'string'},
          'column': {'type': 'string'},
          'column_id': {'type': 'string'},
          'status': {'type': 'string'},
          'columns': {
            'type': 'array',
            'items': {'type': 'string'},
          },
          'position': {'type': 'integer'},
          'notes': {'type': 'string'},
          'priority': {'type': 'string'},
          'assignee': {'type': 'string'},
          'subtask_id': {'type': 'string'},
          'done': {'type': 'boolean'},
          'blocker_reason': {'type': 'string'},
          'reason': {'type': 'string'},
        },
      },
    ),
    MobileToolDefinition(
      name: 'mobile_json',
      description:
          'Validate, format, or minify JSON locally on this phone using Flutter/Dart.',
      tags: ['tool', 'json', 'text', mobileCompatibleTag],
      aliases: ['json_format', 'json_validate', 'mobile.json'],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'action': {
            'type': 'string',
            'enum': ['validate', 'format', 'pretty', 'minify'],
            'default': 'format',
          },
          'text': {'type': 'string'},
          'json': {},
          'indent': {'type': 'string', 'default': '  '},
        },
      },
    ),
    MobileToolDefinition(
      name: 'mobile_base64',
      description:
          'Encode or decode Base64 locally on this phone using Flutter/Dart.',
      tags: ['tool', 'encoding', 'text', mobileCompatibleTag],
      aliases: ['base64_codec', 'mobile.base64'],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'action': {
            'type': 'string',
            'enum': ['encode', 'decode'],
            'default': 'encode',
          },
          'text': {'type': 'string'},
          'data': {'type': 'string'},
        },
      },
    ),
    MobileToolDefinition(
      name: 'mobile_uuid',
      description:
          'Generate UUID v4 values locally on this phone using Flutter/Dart.',
      tags: ['tool', 'id', 'uuid', mobileCompatibleTag],
      aliases: ['uuid_generate', 'mobile.uuid'],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'count': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 20,
            'default': 1,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'mobile_url_open',
      description:
          'Open an http/https URL visibly on this phone. Implemented through Flutter with iOS Swift and Android Kotlin native bridges.',
      tags: ['tool', 'browser', 'url', 'mobile', mobileCompatibleTag],
      aliases: [
        'url_open',
        'browser_open_url',
        'defaults.browser.open_url',
        'defaultspack.browser.open_url',
        'defaults.browser.open.url',
        'defaultspack.browser.open.url',
      ],
      runtimeLayers: _nativeUrlRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIApplication.open',
        'android:Kotlin Intent.ACTION_VIEW',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'url': {'type': 'string'},
        },
        'required': ['url'],
      },
    ),
    MobileToolDefinition(
      name: 'media_clipboard_read',
      description:
          'Read text from this phone clipboard after explicit mobile approval.',
      tags: ['tool', 'media', 'clipboard', mobileCompatibleTag],
      aliases: [
        'clipboard_read',
        'defaults_media_clipboard_read',
        'defaultspack_media_clipboard_read',
        'defaults.media.clipboard.read',
        'defaults.media.clipboard_read',
        'defaultspack.media.clipboard.read',
        'defaultspack.media.clipboard_read',
      ],
      runtimeLayers: _nativeUrlRuntimeLayers,
      nativeLayers: [
        'ios:Flutter Clipboard/Pasteboard bridge',
        'android:Flutter ClipboardManager bridge',
      ],
      requiresMobileApproval: true,
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'reason': {
            'type': 'string',
            'description': 'Why clipboard text is needed.',
          },
          'max_chars': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 8000,
            'default': 4000,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_clipboard_write',
      description:
          'Write text to this phone clipboard after explicit mobile approval.',
      tags: ['tool', 'media', 'clipboard', mobileCompatibleTag],
      aliases: [
        'clipboard_write',
        'defaults_media_clipboard_write',
        'defaultspack_media_clipboard_write',
        'defaults.media.clipboard.write',
        'defaults.media.clipboard_write',
        'defaultspack.media.clipboard.write',
        'defaultspack.media.clipboard_write',
      ],
      runtimeLayers: _nativeUrlRuntimeLayers,
      nativeLayers: [
        'ios:Flutter Clipboard/Pasteboard bridge',
        'android:Flutter ClipboardManager bridge',
      ],
      requiresMobileApproval: true,
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'text': {'type': 'string'},
          'content': {'type': 'string'},
          'reason': {
            'type': 'string',
            'description': 'Why clipboard text should be replaced.',
          },
        },
        'required': ['text'],
      },
    ),
    MobileToolDefinition(
      name: 'media_file_pick',
      description:
          'Pick one image, audio, or document from this phone after explicit mobile approval. Returns file metadata and base64 content.',
      tags: ['tool', 'media', 'file', 'picker', mobileCompatibleTag],
      aliases: [
        'file_pick',
        'media_pick_file',
        'mobile_media_pick',
        'defaults_media_file_pick',
        'defaultspack_media_file_pick',
        'defaults.media.file.pick',
        'defaults.media.file_pick',
        'defaultspack.media.file.pick',
        'defaultspack.media.file_pick',
      ],
      runtimeLayers: _nativeMediaPickerRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIDocumentPickerViewController',
        'android:Kotlin Intent.ACTION_OPEN_DOCUMENT',
      ],
      requiresMobileApproval: true,
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'kind': {
            'type': 'string',
            'enum': ['image', 'audio', 'file'],
            'default': 'file',
          },
          'type': {
            'type': 'string',
            'enum': ['image', 'audio', 'file'],
          },
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardMediaPickMaxBytes,
            'default': _defaultMediaPickMaxBytes,
          },
          'reason': {
            'type': 'string',
            'description': 'Why this phone file is needed.',
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'tool_search',
      description:
          'Search the mobile tool catalog and explain whether defaultspack tools are available on this phone.',
      tags: ['tool', 'search', 'catalog', mobileCompatibleTag],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'query': {
            'type': 'string',
            'description': 'Tool name, service, or desired action.',
          },
          'limit': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 12,
            'default': 6,
          },
          'platform': {
            'type': 'string',
            'enum': [
              'android',
              'flutter',
              'ios',
              'kotlin',
              'pc',
              'swift',
            ],
          },
        },
        'required': ['query'],
      },
    ),
    MobileToolDefinition(
      name: 'tool_names',
      description:
          'List tool function names available to the mobile defaultspack-compatible runtime.',
      tags: ['tool', 'catalog', mobileCompatibleTag],
      aliases: [
        'defaults_tool_names',
        'defaultspack_tool_names',
        'defaults.tool.names',
        'defaultspack.tool.names',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
      },
    ),
    MobileToolDefinition(
      name: 'tool_list',
      description:
          'List mobile-compatible tools and known PC-only defaultspack tools with reasons.',
      tags: ['tool', 'catalog', mobileCompatibleTag],
      aliases: [
        'defaults_tool_list',
        'defaultspack_tool_list',
        'defaults.tool.list',
        'defaultspack.tool.list',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'include_unavailable': {
            'type': 'boolean',
            'default': true,
          },
          'limit': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 400,
            'default': 240,
          },
          'platform': {
            'type': 'string',
            'enum': [
              'android',
              'flutter',
              'ios',
              'kotlin',
              'pc',
              'swift',
            ],
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'tool_schema',
      description:
          'Return the schema and mobile execution status for a defaultspack tool name.',
      tags: ['tool', 'catalog', mobileCompatibleTag],
      aliases: [
        'defaults_tool_schema',
        'defaultspack_tool_schema',
        'defaults.tool.schema',
        'defaultspack.tool.schema',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'tool_name': {'type': 'string'},
          'name': {'type': 'string'},
          'tool_id': {'type': 'string'},
        },
      },
    ),
    MobileToolDefinition(
      name: 'tool_invoke',
      description:
          'Invoke a mobile-compatible defaultspack tool through the defaultspack tool_invoke convention. Host-bound tools return a clear unavailable reason.',
      tags: ['tool', 'broker', mobileCompatibleTag],
      aliases: [
        'defaults_tool_invoke',
        'defaultspack_tool_invoke',
        'defaults.tool.invoke',
        'defaultspack.tool.invoke',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'tool_name': {'type': 'string'},
          'tool_id': {'type': 'string'},
          'name': {'type': 'string'},
          'arguments': {'type': 'object'},
          'args': {'type': 'object'},
          'input': {'type': 'object'},
        },
        'required': ['tool_name'],
      },
    ),
    MobileToolDefinition(
      name: 'agent_plan',
      description:
          'Create a lightweight phone-local agent plan using the defaultspack agent_plan convention.',
      tags: ['agent', 'planning', mobileCompatibleTag],
      aliases: [
        'defaults_agent_plan',
        'defaultspack_agent_plan',
        'defaults.agent.plan',
        'defaultspack.agent.plan',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'objective': {'type': 'string'},
          'title': {'type': 'string'},
          'steps': {
            'type': 'array',
            'items': {'type': 'string'},
          },
          'plan': {},
        },
      },
    ),
    MobileToolDefinition(
      name: 'agent_progress',
      description:
          'Return phone-local agent progress, plans, task board cards, and todos.',
      tags: ['agent', 'status', mobileCompatibleTag],
      aliases: [
        'defaults_agent_progress',
        'defaultspack_agent_progress',
        'defaults.agent.progress',
        'defaultspack.agent.progress',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
      },
    ),
    MobileToolDefinition(
      name: 'agent_status',
      description:
          'Return phone-local agent status using the defaultspack agent_status convention.',
      tags: ['agent', 'status', mobileCompatibleTag],
      aliases: [
        'defaults_agent_status',
        'defaultspack_agent_status',
        'defaults.agent.status',
        'defaultspack.agent.status',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
      },
    ),
    MobileToolDefinition(
      name: assistantProgressToolName,
      description:
          'Emit a brief user-visible work progress update. Use sparingly at phase changes, important findings, failures, or final verification.',
      tags: [
        'tool',
        'progress',
        'internal',
        mobileCompatibleTag,
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': false,
        'properties': {
          'phase': {
            'type': 'string',
            'enum': ['change', 'finalize', 'inspect', 'recover', 'verify'],
          },
          'status': {
            'type': 'string',
            'enum': ['active', 'blocked', 'completed'],
          },
          'summary': {
            'type': 'string',
            'maxLength': _assistantProgressTextLimit,
          },
          'next_action': {
            'type': 'string',
            'maxLength': _assistantProgressTextLimit,
          },
          'related_tool_call_ids': {
            'type': 'array',
            'maxItems': _assistantProgressRelatedToolLimit,
            'items': {'type': 'string'},
          },
        },
        'required': ['phase', 'status', 'summary', 'next_action'],
      },
    ),
  ];

  static const unavailableDefaultspackTools = <MobileToolDefinition>[
    MobileToolDefinition(
      name: 'web_search',
      description: 'Run the defaultspack web research tool.',
      tags: ['tool', 'research', 'web'],
      aliases: ['tool_web_search', 'defaultspack.tool.web_search'],
      unavailableReason:
          'このtoolはPC側defaultspackのresearch providerに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'reddit_search',
      description: 'Run the defaultspack reddit research tool.',
      tags: ['tool', 'research', 'reddit'],
      aliases: ['tool_reddit_search', 'defaultspack.tool.reddit_search'],
      unavailableReason:
          'このtoolはPC側defaultspackのresearch providerに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'file_reader',
      description: 'Read files from the host workspace.',
      tags: ['tool', 'file', 'workspace', 'host'],
      aliases: ['tool_file_reader', 'defaultspack.tool.file_reader'],
      unavailableReason:
          'このtoolはPCのworkspace/file systemに依存するため、このスマホ単体では実行できません。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'subagent',
      description: 'Run the default delegation/subagent tool.',
      tags: ['tool', 'agent', 'host'],
      aliases: ['tool_subagent', 'defaultspack.tool.subagent'],
      unavailableReason:
          'このtoolはPC側のagent runtimeと会話/workspace状態に依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'tool_task_board_agent_session',
      description:
          'Link task board cards to defaultspack coding agent sessions.',
      tags: ['tool', 'planning', 'task_board', 'agent', 'coding', 'host'],
      unavailableReason:
          'このtoolはPC側のcoding agent sessionに依存するため、このスマホ単体では実行できません。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'terminal',
      description: 'Run terminal commands on the host runtime.',
      tags: ['terminal', 'host', 'workspace'],
      unavailableReason:
          'このtoolはPC側のterminal/workspaceに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'browser',
      description: 'Operate the host browser or browser companion.',
      tags: ['browser', 'host'],
      unavailableReason:
          'このtoolはPC側のブラウザ状態に依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'computer',
      description: 'Operate the host desktop UI.',
      tags: ['computer', 'desktop', 'host'],
      unavailableReason: 'このtoolはPC画面の操作権限が必要なため、このスマホ単体では実行できません。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'files',
      description: 'Read or write host workspace files.',
      tags: ['file', 'workspace', 'host'],
      unavailableReason:
          'このtoolはPCのworkspace/file systemに依存するため、このスマホ単体では実行できません。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
  ];

  List<MobileToolDefinition> get availableTools => supportedTools;

  int get knownDefaultspackToolAgentCount =>
      _defaultspackToolAgentManifestCatalog.length;

  int get knownUnavailableDefaultspackToolCount =>
      _runtimeCatalogRecords(includeUnavailable: true)
          .where((record) => record['mobile_compatible'] != true)
          .length;

  List<Map<String, dynamic>> openAiTools() {
    final exported = <Map<String, dynamic>>[];
    final seenNames = <String>{};

    void addTool({
      required String name,
      required String description,
      required Map<String, dynamic> parameters,
    }) {
      final trimmed = name.trim();
      if (!_isOpenAiFunctionName(trimmed) || !seenNames.add(trimmed)) return;
      exported.add({
        'type': 'function',
        'function': {
          'name': trimmed,
          'description': description,
          'parameters': parameters,
        },
      });
    }

    for (final tool in supportedTools) {
      for (final name in tool.openAiNames) {
        addTool(
          name: name,
          description: _openAiToolDescription(tool),
          parameters: tool.parameters,
        );
      }
    }

    for (final record in _runtimeCatalogRecords(includeUnavailable: true)) {
      if (!_shouldExportCatalogRecordAsNativeTool(record)) continue;
      addTool(
        name: '${record['function_id'] ?? ''}',
        description: _openAiCatalogDescription(record),
        parameters: _asObjectSchema(record['parameters']),
      );
    }

    return exported;
  }

  static bool isAssistantProgressToolName(String name) =>
      name.trim() == assistantProgressToolName;

  static Map<String, dynamic> assistantProgressPayload(
    MobileToolResult result,
  ) {
    final parsed = _decodeObject(result.output);
    final data = parsed['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return data.map((key, value) => MapEntry('$key', value));
    return normalizeAssistantProgressPayload({
      'summary': result.summary,
      'next_action': '',
    });
  }

  static Map<String, dynamic> normalizeAssistantProgressPayload(
    Map<String, dynamic>? arguments,
  ) {
    final args = arguments ?? const {};
    final phase = '${args['phase'] ?? ''}'.trim();
    final status = '${args['status'] ?? ''}'.trim();
    final summary = _clampText(args['summary'], _assistantProgressTextLimit);
    final nextAction =
        _clampText(args['next_action'], _assistantProgressTextLimit);
    final relatedRaw = args['related_tool_call_ids'];
    final related = <String>[];
    if (relatedRaw is List) {
      for (final item in relatedRaw) {
        final value = '$item'.trim();
        if (value.isNotEmpty) related.add(value);
        if (related.length >= _assistantProgressRelatedToolLimit) break;
      }
    }
    return {
      'phase': _assistantProgressPhases.contains(phase) ? phase : 'inspect',
      'status': _assistantProgressStatuses.contains(status) ? status : 'active',
      'summary': summary.isNotEmpty ? summary : '作業状況を更新しています',
      'next_action': nextAction.isNotEmpty ? nextAction : '続行します',
      'related_tool_call_ids': related,
    };
  }

  MobileToolResult execute(MobileToolCall call) {
    final name = _canonicalToolName(call.name);
    switch (name) {
      case 'calculator':
        return _calculator(call.arguments);
      case 'tool_consent_check':
        return _toolConsentCheck(call.arguments);
      case 'tool_consent_confirm':
        return _toolConsentConfirm(call.arguments);
      case 'current_time':
        return _currentTime(call.arguments);
      case 'mobile_platform_info':
        return _mobilePlatformInfo(call.arguments);
      case 'todo':
        return _todo(call.arguments);
      case 'tool_task_board':
      case 'task_board':
        return _taskBoard(call.arguments);
      case 'mobile_json':
        return _mobileJson(call.arguments);
      case 'mobile_base64':
        return _mobileBase64(call.arguments);
      case 'mobile_uuid':
        return _mobileUuid(call.arguments);
      case 'mobile_url_open':
      case 'media_clipboard_read':
      case 'media_clipboard_write':
      case 'media_file_pick':
        return _asyncOnlyTool(name);
      case 'tool_search':
        return _toolSearch(call.arguments);
      case 'tool_names':
        return _toolNames(call.arguments);
      case 'tool_list':
        return _toolList(call.arguments);
      case 'tool_schema':
        return _toolSchema(call.arguments);
      case 'tool_invoke':
        return _toolInvoke(call.arguments);
      case 'agent_plan':
        return _agentPlan(call.arguments);
      case 'agent_progress':
      case 'agent_status':
        return _agentStatus(call.arguments, name);
      case assistantProgressToolName:
        return _assistantProgress(call.arguments);
      default:
        return MobileToolResult(
          ok: false,
          summary: 'unsupported tool',
          output: _unsupportedReason(name),
        );
    }
  }

  Future<MobileToolResult> executeAsync(MobileToolCall call) async {
    final name = _canonicalToolName(call.name);
    if (_isAsyncPhoneToolName(name)) {
      return _executeAsyncPhoneTool(
        MobileToolCall(id: call.id, name: name, arguments: call.arguments),
      );
    }
    if (name == 'tool_invoke') {
      final requested =
          '${call.arguments['tool_name'] ?? call.arguments['tool_id'] ?? call.arguments['name'] ?? ''}'
              .trim();
      final requestedCanonical = _canonicalToolName(requested);
      if (_isAsyncPhoneToolName(requestedCanonical)) {
        return _toolInvokeAsync(call.arguments);
      }
    }
    final result = execute(call);
    if (_pcDelegate == null ||
        result.ok ||
        !_shouldDelegateToPc(call, result)) {
      return result;
    }
    return _pcDelegate.invoke(call);
  }

  Future<MobileToolResult> _executeAsyncPhoneTool(MobileToolCall call) {
    final name = _canonicalToolName(call.name);
    switch (name) {
      case 'mobile_url_open':
        return _mobileUrlOpen(call.arguments);
      case 'media_clipboard_read':
        return _mediaClipboardRead(call.arguments);
      case 'media_clipboard_write':
        return _mediaClipboardWrite(call.arguments);
      case 'media_file_pick':
        return _mediaFilePick(call.arguments);
      default:
        return Future.value(execute(call));
    }
  }

  Future<MobileToolResult> _toolInvokeAsync(Map<String, dynamic> args) async {
    final requested =
        '${args['tool_name'] ?? args['tool_id'] ?? args['name'] ?? ''}'.trim();
    if (requested.isEmpty) return _toolInvoke(args);
    final canonical = _canonicalToolName(requested);
    if (!_isAsyncPhoneToolName(canonical)) return _toolInvoke(args);
    final tool = _findToolDefinition(canonical);
    final result = await _executeAsyncPhoneTool(
      MobileToolCall(
        id: 'tool_invoke:${DateTime.now().microsecondsSinceEpoch}',
        name: canonical,
        arguments: _invokeArguments(args),
      ),
    );
    return MobileToolResult(
      ok: result.ok,
      summary: '${tool?.name ?? canonical}: ${result.summary}',
      output: jsonEncode({
        'status': result.ok ? 'ok' : 'error',
        'data': {
          'tool_name': tool?.name ?? canonical,
          'requested_tool_name': requested,
          'result': result.output,
          'summary': result.summary,
          'is_error': !result.ok,
          'execution_location': 'phone',
        },
      }),
    );
  }

  String _openAiToolDescription(MobileToolDefinition tool) {
    if (tool.name == 'tool_invoke' && pcDelegationAvailable) {
      return '${tool.description} The mobile tool surface is unified: phone-compatible tools run locally, and host-bound defaultspack tools route to the connected PC runtime when PC delegation is enabled.';
    }
    return tool.description;
  }

  bool _shouldDelegateToPc(MobileToolCall call, MobileToolResult result) {
    final name = _canonicalToolName(call.name);
    if (MobileToolRuntime.isAssistantProgressToolName(name)) return false;
    if (const {
      'tool_search',
      'tool_names',
      'tool_list',
      'tool_schema',
      'agent_plan',
      'agent_progress',
      'agent_status',
      'todo',
      'tool_task_board',
      'task_board',
      'calculator',
      'tool_consent_check',
      'tool_consent_confirm',
      'current_time',
      'mobile_platform_info',
      'mobile_json',
      'mobile_base64',
      'mobile_uuid',
      'mobile_url_open',
      'media_clipboard_read',
      'media_clipboard_write',
      'media_file_pick',
    }.contains(name)) {
      return false;
    }
    if (name == 'tool_invoke') {
      final requested =
          '${call.arguments['tool_name'] ?? call.arguments['tool_id'] ?? call.arguments['name'] ?? ''}'
              .trim();
      final requestedCanonical = _canonicalToolName(requested);
      final requestedTool = _findToolDefinition(requestedCanonical);
      if (requestedTool != null && requestedTool.available) return false;
      return true;
    }
    final output = result.output.toLowerCase();
    return result.summary == 'unsupported tool' ||
        result.summary.contains('unavailable on phone') ||
        output.contains('tool_unavailable_on_phone') ||
        output.contains('pc側') ||
        output.contains('pc runtime') ||
        output.contains('pc接続時');
  }

  MobileToolResult _calculator(Map<String, dynamic> args) {
    final expression = '${args['expression'] ?? args['input'] ?? ''}'.trim();
    if (expression.isEmpty) {
      return const MobileToolResult(
        ok: false,
        summary: 'expression is required',
        output: 'expression is required',
      );
    }
    try {
      final value = _ExpressionParser(expression).parse();
      final normalized = _formatNumber(value);
      return MobileToolResult(
        ok: true,
        summary: normalized,
        output: '$expression = $normalized',
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'calculation failed',
        output: '計算できませんでした: $error',
      );
    }
  }

  MobileToolResult _toolConsentCheck(Map<String, dynamic> args) {
    final text = '${args['text'] ?? args['input'] ?? ''}';
    if (text.trim().isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'text is required',
        output: jsonEncode({
          'status': 'error',
          'error': {'code': 'MISSING_PARAM', 'message': 'text is required'},
        }),
      );
    }
    final lower = text.toLowerCase();
    final categories = <String>[];
    for (final entry in _mobileConsentCategories.entries) {
      final keywords = entry.value['keywords'];
      if (keywords is! List<String>) continue;
      if (keywords.any((keyword) => lower.contains(keyword.toLowerCase()))) {
        categories.add(entry.key);
      }
    }
    categories.sort();
    final requiresConsent = categories.isNotEmpty;
    String? consentId;
    final disclaimers = <String, String>{};
    if (requiresConsent) {
      consentId = _nextToolId('consent');
      for (final category in categories) {
        final disclaimer = _mobileConsentCategories[category]?['disclaimer'];
        if (disclaimer is String) disclaimers[category] = disclaimer;
      }
      _mobileConsents[consentId] = {
        'consent_id': consentId,
        'categories': categories,
        'accepted': false,
        'created_at': DateTime.now().toUtc().toIso8601String(),
        'accepted_at': null,
      };
    }
    final useAi = args['use_ai'] == true;
    return MobileToolResult(
      ok: true,
      summary: requiresConsent
          ? 'consent required: ${categories.join(', ')}'
          : 'consent not required',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'requires_consent': requiresConsent,
          'categories': categories,
          'consent_id': consentId,
          'disclaimers': disclaimers,
          'classifier': 'mobile_keyword',
          if (useAi)
            'ai_classification_skipped':
                'mobile tool_consent_check currently uses the built-in keyword classifier; AI consent classification can be delegated to the PC runtime.',
        },
      }),
    );
  }

  MobileToolResult _toolConsentConfirm(Map<String, dynamic> args) {
    final consentId = '${args['consent_id'] ?? args['id'] ?? ''}'.trim();
    if (consentId.isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'consent_id is required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'MISSING_PARAM',
            'message': 'consent_id is required',
          },
        }),
      );
    }
    final accepted = args['accepted'];
    if (accepted is! bool) {
      return MobileToolResult(
        ok: false,
        summary: 'accepted is required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'INVALID_PARAM',
            'message': 'accepted must be a boolean',
          },
        }),
      );
    }
    final record = _mobileConsents[consentId];
    if (record == null) {
      return MobileToolResult(
        ok: false,
        summary: 'consent not found',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'NOT_FOUND',
            'message': "consent_id '$consentId' not found",
          },
        }),
      );
    }
    record['accepted'] = accepted;
    record['accepted_at'] =
        accepted ? DateTime.now().toUtc().toIso8601String() : null;
    return MobileToolResult(
      ok: true,
      summary: accepted ? 'consent accepted' : 'consent rejected',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'consent_id': consentId,
          'accepted': accepted,
          'accepted_at': record['accepted_at'],
        },
      }),
    );
  }

  MobileToolResult _currentTime(Map<String, dynamic> args) {
    final now = DateTime.now();
    final format = '${args['format'] ?? 'human'}'.trim();
    if (format == 'iso8601') {
      return MobileToolResult(
        ok: true,
        summary: now.toIso8601String(),
        output: now.toIso8601String(),
      );
    }
    final offset = now.timeZoneOffset;
    final sign = offset.isNegative ? '-' : '+';
    final abs = offset.abs();
    final hh = abs.inHours.toString().padLeft(2, '0');
    final mm = (abs.inMinutes % 60).toString().padLeft(2, '0');
    final text =
        '${now.toIso8601String()} (${now.timeZoneName}, UTC$sign$hh:$mm)';
    return MobileToolResult(ok: true, summary: text, output: text);
  }

  MobileToolResult _mobilePlatformInfo(Map<String, dynamic> args) {
    final platform = _currentMobilePlatform();
    final data = {
      'platform': platform,
      'supported_platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_bridge_layers': const {
        'ios': 'Swift MethodChannel',
        'android': 'Kotlin MethodChannel',
      },
      'dart': {
        'version': Platform.version,
        'locale': Platform.localeName,
        'processors': Platform.numberOfProcessors,
      },
      'os': {
        'name': Platform.operatingSystem,
        'version': Platform.operatingSystemVersion,
      },
      'tool_runtime': {
        'mobile_compatible_tag': mobileCompatibleTag,
        'platform_tags': const [
          mobileFlutterTag,
          mobileIosTag,
          mobileAndroidTag,
          mobileSwiftNativeTag,
          mobileKotlinNativeTag,
        ],
      },
    };
    return MobileToolResult(
      ok: true,
      summary: 'mobile platform: $platform',
      output: jsonEncode({'status': 'ok', 'data': data}),
    );
  }

  MobileToolResult _todo(Map<String, dynamic> args) {
    final action = '${args['action'] ?? 'list'}'.trim().toLowerCase();
    try {
      Map<String, dynamic>? changed;
      if (action == 'add' || action == 'create') {
        final title = '${args['title'] ?? args['task'] ?? ''}'.trim();
        if (title.isEmpty) throw const FormatException('title is required');
        changed = {
          'id': _nextToolId('todo'),
          'title': title,
          'status': '${args['status'] ?? 'todo'}',
          'priority': '${args['priority'] ?? 'normal'}',
          'notes': '${args['notes'] ?? ''}',
          'created_at': DateTime.now().millisecondsSinceEpoch,
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        };
        _mobileTodos.add(changed);
      } else if (action == 'complete' || action == 'done') {
        final todo = _findById(_mobileTodos, _argId(args, 'todo_id'));
        if (todo == null) throw const FormatException('todo_id not found');
        todo['status'] = 'done';
        todo['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(todo);
      } else if (action == 'update' || action == 'edit') {
        final todo = _findById(_mobileTodos, _argId(args, 'todo_id'));
        if (todo == null) throw const FormatException('todo_id not found');
        for (final key in ['title', 'status', 'priority', 'notes']) {
          if (args.containsKey(key) && args[key] != null) {
            todo[key] = '${args[key]}';
          }
        }
        todo['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(todo);
      } else if (action == 'remove' || action == 'delete') {
        final id = _argId(args, 'todo_id');
        final before = _mobileTodos.length;
        _mobileTodos.removeWhere((todo) => todo['id'] == id);
        if (_mobileTodos.length == before) {
          throw const FormatException('todo_id not found');
        }
        changed = {'id': id};
      } else if (action == 'clear') {
        changed = {'cleared': _mobileTodos.length};
        _mobileTodos.clear();
      } else if (action != 'list' && action != 'show') {
        throw FormatException('Unsupported todo action: $action');
      }
      final openCount =
          _mobileTodos.where((todo) => todo['status'] != 'done').length;
      final summary = changed != null && '${changed['title'] ?? ''}'.isNotEmpty
          ? '$action: ${changed['title']}; ${_mobileTodos.length} todos ($openCount open)'
          : '${_mobileTodos.length} todos ($openCount open)';
      return MobileToolResult(
        ok: true,
        summary: summary,
        output: jsonEncode({
          'action': action,
          'summary': summary,
          'todos': _mobileTodos,
          'changed': changed,
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'todo failed',
        output: '$error',
      );
    }
  }

  MobileToolResult _taskBoard(Map<String, dynamic> args) {
    final action = '${args['action'] ?? 'list'}'.trim().toLowerCase();
    try {
      Map<String, dynamic>? changed;
      if (action == 'configure' ||
          action == 'configure_columns' ||
          action == 'set_columns' ||
          action == 'columns') {
        _mobileTaskBoard['columns'] = _normalizeColumns(args['columns']);
        changed = {'columns': _mobileTaskBoard['columns']};
      } else if (action == 'create' || action == 'add') {
        final title = '${args['title'] ?? args['task'] ?? ''}'.trim();
        if (title.isEmpty) throw const FormatException('title is required');
        final card = {
          'id': _nextToolId('card'),
          'title': title,
          'column': _resolveColumn(args),
          'status': '${args['status'] ?? 'todo'}',
          'priority': '${args['priority'] ?? 'normal'}',
          'notes': '${args['notes'] ?? ''}',
          'assignee': '${args['assignee'] ?? ''}',
          'subtasks': <Map<String, dynamic>>[],
          'blocked_by': <String>[],
          'blocker_reason': '',
          'created_at': DateTime.now().millisecondsSinceEpoch,
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        };
        _mobileTaskCards.add(card);
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'update' || action == 'edit') {
        final card = _findById(_mobileTaskCards, _argId(args, 'card_id'));
        if (card == null) throw const FormatException('card_id not found');
        for (final key in [
          'title',
          'status',
          'priority',
          'notes',
          'assignee'
        ]) {
          if (args.containsKey(key) && args[key] != null) {
            card[key] = '${args[key]}';
          }
        }
        if (args['column'] != null || args['column_id'] != null) {
          card['column'] = _resolveColumn(args);
        }
        card['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'move') {
        final card = _findById(_mobileTaskCards, _argId(args, 'card_id'));
        if (card == null) throw const FormatException('card_id not found');
        card['column'] = _resolveColumn(args);
        card['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'block' || action == 'unblock') {
        final card = _findById(_mobileTaskCards, _argId(args, 'card_id'));
        if (card == null) throw const FormatException('card_id not found');
        if (action == 'block') {
          card['blocker_reason'] =
              '${args['blocker_reason'] ?? args['reason'] ?? ''}';
          final blocker =
              '${args['blocked_by'] ?? args['depends_on'] ?? ''}'.trim();
          card['blocked_by'] = blocker.isEmpty ? <String>[] : [blocker];
        } else {
          card['blocker_reason'] = '';
          card['blocked_by'] = <String>[];
        }
        card['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'subtask_add' || action == 'add_subtask') {
        final card = _findById(_mobileTaskCards, _argId(args, 'card_id'));
        if (card == null) throw const FormatException('card_id not found');
        final title = '${args['title'] ?? args['task'] ?? ''}'.trim();
        if (title.isEmpty) throw const FormatException('title is required');
        final subtask = {
          'id': _nextToolId('subtask'),
          'title': title,
          'done': false,
          'status': 'todo',
          'assignee': '${args['assignee'] ?? ''}',
          'created_at': DateTime.now().millisecondsSinceEpoch,
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        };
        _subtasks(card).add(subtask);
        card['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'subtask_update' ||
          action == 'subtask_complete' ||
          action == 'subtask_remove' ||
          action == 'remove_subtask') {
        final card = _findById(_mobileTaskCards, _argId(args, 'card_id'));
        if (card == null) throw const FormatException('card_id not found');
        final subtasks = _subtasks(card);
        final subtask = _findById(subtasks, _argId(args, 'subtask_id'));
        if (subtask == null) {
          throw const FormatException('subtask_id not found');
        }
        if (action == 'subtask_remove' || action == 'remove_subtask') {
          subtasks.removeWhere((item) => item['id'] == subtask['id']);
        } else {
          for (final key in ['title', 'status', 'notes', 'assignee']) {
            if (args.containsKey(key) && args[key] != null) {
              subtask[key] = '${args[key]}';
            }
          }
          if (action == 'subtask_complete') {
            subtask['done'] = true;
            subtask['status'] = 'done';
          } else if (args.containsKey('done')) {
            subtask['done'] = args['done'] == true;
          }
          subtask['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        }
        card['updated_at'] = DateTime.now().millisecondsSinceEpoch;
        changed = Map<String, dynamic>.from(card);
      } else if (action == 'delete' || action == 'remove') {
        final id = _argId(args, 'card_id');
        final before = _mobileTaskCards.length;
        _mobileTaskCards.removeWhere((card) => card['id'] == id);
        if (_mobileTaskCards.length == before) {
          throw const FormatException('card_id not found');
        }
        changed = {'id': id};
      } else if (action == 'clear') {
        changed = {'cleared': _mobileTaskCards.length};
        _mobileTaskCards.clear();
      } else if (action != 'list' && action != 'show') {
        throw FormatException('Unsupported task_board action: $action');
      }
      final summary = _taskBoardSummary(action);
      return MobileToolResult(
        ok: true,
        summary: summary,
        output: jsonEncode({
          'action': action,
          'summary': summary,
          'board': _taskBoardSnapshot(),
          'changed': changed,
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'task_board failed',
        output: '$error',
      );
    }
  }

  MobileToolResult _mobileJson(Map<String, dynamic> args) {
    final action = '${args['action'] ?? 'format'}'.trim().toLowerCase();
    final raw = args.containsKey('json')
        ? jsonEncode(args['json'])
        : '${args['text'] ?? args['input'] ?? ''}'.trim();
    if (raw.isEmpty) {
      return _jsonToolError('MISSING_INPUT', 'text or json is required');
    }
    try {
      final decoded = jsonDecode(raw);
      final output = switch (action) {
        'minify' => jsonEncode(decoded),
        'validate' => jsonEncode({
            'status': 'ok',
            'valid': true,
            'type': decoded.runtimeType.toString(),
          }),
        _ =>
          JsonEncoder.withIndent('${args['indent'] ?? '  '}').convert(decoded),
      };
      return MobileToolResult(
        ok: true,
        summary: action == 'validate' ? 'valid JSON' : 'JSON $action',
        output: output,
      );
    } catch (error) {
      return _jsonToolError('INVALID_JSON', '$error');
    }
  }

  MobileToolResult _jsonToolError(String code, String message) {
    return MobileToolResult(
      ok: false,
      summary: 'JSON failed',
      output: jsonEncode({
        'status': 'error',
        'error': {'code': code, 'message': message},
      }),
    );
  }

  MobileToolResult _mobileBase64(Map<String, dynamic> args) {
    final action = '${args['action'] ?? 'encode'}'.trim().toLowerCase();
    final text = '${args['text'] ?? args['data'] ?? args['input'] ?? ''}';
    try {
      if (action == 'decode') {
        final bytes = base64.decode(text.trim());
        final decoded = utf8.decode(bytes);
        return MobileToolResult(
          ok: true,
          summary: 'base64 decoded',
          output: decoded,
        );
      }
      final encoded = base64.encode(utf8.encode(text));
      return MobileToolResult(
        ok: true,
        summary: 'base64 encoded',
        output: encoded,
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'base64 failed',
        output: jsonEncode({
          'status': 'error',
          'error': {'code': 'INVALID_BASE64', 'message': '$error'},
        }),
      );
    }
  }

  MobileToolResult _mobileUuid(Map<String, dynamic> args) {
    final count = (args['count'] is num)
        ? math.max(1, math.min(20, (args['count'] as num).toInt()))
        : 1;
    final values = List.generate(count, (_) => const Uuid().v4());
    return MobileToolResult(
      ok: true,
      summary: count == 1 ? values.single : '$count UUIDs',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'uuids': values,
          if (count == 1) 'uuid': values.single,
        },
      }),
    );
  }

  Future<MobileToolResult> _mobileUrlOpen(Map<String, dynamic> args) async {
    final raw = '${args['url'] ?? args['href'] ?? args['input'] ?? ''}'.trim();
    if (raw.isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'url is required',
        output: jsonEncode({
          'status': 'error',
          'error': {'code': 'MISSING_URL', 'message': 'url is required'},
        }),
      );
    }
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'invalid URL',
        output: jsonEncode({
          'status': 'error',
          'error': {'code': 'INVALID_URL', 'message': 'invalid URL: $raw'},
        }),
      );
    }
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      return MobileToolResult(
        ok: false,
        summary: 'unsupported URL scheme',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'UNSUPPORTED_URL_SCHEME',
            'message': 'Only http and https URLs can be opened by this tool.',
          },
        }),
      );
    }
    final ok = await _urlLauncher.open(uri);
    return MobileToolResult(
      ok: ok,
      summary: ok ? 'opened ${uri.host}' : 'URL open failed',
      output: jsonEncode({
        'status': ok ? 'ok' : 'error',
        'data': {
          'url': uri.toString(),
          'opened': ok,
          'execution_location': 'phone',
          'runtime_layers': _nativeUrlRuntimeLayers,
        },
      }),
    );
  }

  Future<MobileToolResult> _mediaClipboardRead(
    Map<String, dynamic> args,
  ) async {
    final approved = await _requestMobileApproval(
      toolName: 'media_clipboard_read',
      risk: 'high',
      arguments: args,
      prompt: 'このスマホのclipboardからテキストを読み取ります。許可した内容はAIのtool結果として会話に渡されます。',
    );
    if (!approved) return _mobileApprovalRequired('media_clipboard_read');

    final text = await _clipboard.readText() ?? '';
    final maxChars = (args['max_chars'] is num)
        ? math.max(1, math.min(8000, (args['max_chars'] as num).toInt()))
        : 4000;
    final truncated = text.length > maxChars;
    final content = truncated ? text.substring(0, maxChars) : text;
    return MobileToolResult(
      ok: true,
      summary: truncated
          ? 'clipboard read ${content.length}/${text.length} chars'
          : 'clipboard read ${content.length} chars',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'content': content,
          'truncated': truncated,
          'length': text.length,
          'returned_length': content.length,
          'execution_location': 'phone',
          'requires_mobile_approval': true,
        },
      }),
    );
  }

  Future<MobileToolResult> _mediaClipboardWrite(
    Map<String, dynamic> args,
  ) async {
    final text = '${args['text'] ?? args['content'] ?? args['input'] ?? ''}';
    if (text.isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'text is required',
        output: jsonEncode({
          'status': 'error',
          'error': {'code': 'MISSING_PARAM', 'message': 'text is required'},
        }),
      );
    }
    final approved = await _requestMobileApproval(
      toolName: 'media_clipboard_write',
      risk: 'high',
      arguments: {
        ...args,
        'preview': _clampText(text.replaceAll(RegExp(r'\s+'), ' '), 160),
        'length': text.length,
      },
      prompt: 'このスマホのclipboardを新しいテキストで置き換えます。現在のclipboard内容は上書きされます。',
    );
    if (!approved) return _mobileApprovalRequired('media_clipboard_write');

    await _clipboard.writeText(text);
    return MobileToolResult(
      ok: true,
      summary: 'clipboard wrote ${text.length} chars',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'written': true,
          'length': text.length,
          'execution_location': 'phone',
          'requires_mobile_approval': true,
        },
      }),
    );
  }

  Future<MobileToolResult> _mediaFilePick(Map<String, dynamic> args) async {
    final kind = _normalizeMediaPickKind(
      args['kind'] ?? args['type'] ?? args['media_type'],
    );
    final maxBytes = _boundedMediaPickMaxBytes(args['max_bytes']);
    final approved = await _requestMobileApproval(
      toolName: 'media_file_pick',
      risk: 'high',
      arguments: {
        ...args,
        'kind': kind,
        'max_bytes': maxBytes,
      },
      prompt: 'このスマホから1つのファイルを選択します。選択したファイル内容はAIのtool結果として会話に渡されます。',
    );
    if (!approved) return _mobileApprovalRequired('media_file_pick');

    try {
      final picked = await _mediaPicker.pick(kind: kind, maxBytes: maxBytes);
      if (picked == null) {
        return MobileToolResult(
          ok: false,
          summary: 'file pick cancelled',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'MEDIA_PICK_CANCELLED',
              'message': 'No file was selected on this phone.',
              'execution_location': 'phone',
            },
          }),
        );
      }
      if (picked.size > maxBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'file is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'MEDIA_FILE_TOO_LARGE',
              'message': 'Selected file is larger than max_bytes.',
              'size': picked.size,
              'max_bytes': maxBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }
      return MobileToolResult(
        ok: true,
        summary: 'picked ${picked.name} (${picked.size} bytes)',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'name': picked.name,
            'mime_type': picked.mimeType,
            'size': picked.size,
            'kind': kind,
            'base64': picked.base64Data,
            'encoding': 'base64',
            'execution_location': 'phone',
            'runtime_layers': _nativeMediaPickerRuntimeLayers,
            'requires_mobile_approval': true,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'file pick failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'MEDIA_PICK_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  Future<bool> _requestMobileApproval({
    required String toolName,
    required String prompt,
    required Map<String, dynamic> arguments,
    required String risk,
  }) async {
    final delegate = _approvalDelegate;
    if (delegate == null) return false;
    try {
      return await delegate.approve(
        MobileToolApprovalRequest(
          toolName: toolName,
          prompt: prompt,
          arguments: arguments,
          risk: risk,
        ),
      );
    } catch (_) {
      return false;
    }
  }

  MobileToolResult _mobileApprovalRequired(String toolName) {
    return MobileToolResult(
      ok: false,
      summary: '$toolName requires mobile approval',
      output: jsonEncode({
        'status': 'error',
        'error': {
          'code': 'MOBILE_APPROVAL_REQUIRED',
          'message':
              '$toolName requires explicit approval on this phone before it can run.',
          'tool_name': toolName,
          'execution_location': 'phone',
        },
      }),
    );
  }

  MobileToolResult _asyncOnlyTool(String name) {
    return MobileToolResult(
      ok: false,
      summary: '$name requires async runtime',
      output: jsonEncode({
        'status': 'error',
        'error': {
          'code': 'ASYNC_TOOL_REQUIRES_EXECUTE_ASYNC',
          'message':
              '$name uses a Flutter platform channel and must be run through executeAsync.',
        },
      }),
    );
  }

  MobileToolResult _toolSearch(Map<String, dynamic> args) {
    final query = '${args['query'] ?? ''}'.trim().toLowerCase();
    final platformFilter = _normalizePlatformFilter(
      args['platform'] ?? args['execution_platform'] ?? args['mobile_platform'],
    );
    final limit = (args['limit'] is num)
        ? math.max(1, math.min(12, (args['limit'] as num).toInt()))
        : 6;
    final records = <Map<String, dynamic>>[];
    for (final record in _runtimeCatalogRecords(includeUnavailable: true)) {
      if (!_recordMatchesPlatform(record, platformFilter)) continue;
      final haystack = _recordSearchText(record);
      if (query.isEmpty || haystack.contains(query)) {
        records.add(record);
      }
      if (records.length >= limit) break;
    }
    if (records.isEmpty) {
      records.add(_unsupportedToolRecord(query));
    }
    return MobileToolResult(
      ok: true,
      summary: '${records.length} tools',
      output: jsonEncode({
        'agent_template': _agentTemplateRecord(),
        'tool_surface': _toolSurfaceRecord(pcDelegationAvailable),
        'platform_filter': platformFilter,
        'tools': records,
      }),
    );
  }

  MobileToolResult _toolNames(Map<String, dynamic> args) {
    final includeAliases = args['include_aliases'] != false;
    final includeUnavailable = args['include_unavailable'] != false;
    final platformFilter = _normalizePlatformFilter(
      args['platform'] ?? args['execution_platform'] ?? args['mobile_platform'],
    );
    final names = <String>[];
    for (final record
        in _runtimeCatalogRecords(includeUnavailable: includeUnavailable)) {
      if (!_recordMatchesPlatform(record, platformFilter)) continue;
      for (final key in ['function_id', 'tool_id', 'requested_name']) {
        final value = '${record[key] ?? ''}'.trim();
        if (value.isNotEmpty && _isOpenAiFunctionName(value)) names.add(value);
      }
      if (includeAliases) {
        names.addAll(
          (record['aliases'] as List? ?? const [])
              .map((alias) => '$alias')
              .where(_isOpenAiFunctionName),
        );
      }
    }
    return MobileToolResult(
      ok: true,
      summary: '${names.length} tool names',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'names': names.toSet().toList()..sort(),
          'mobile_compatible_tag': mobileCompatibleTag,
          'platform_filter': platformFilter,
        },
      }),
    );
  }

  MobileToolResult _toolList(Map<String, dynamic> args) {
    final includeUnavailable = args['include_unavailable'] != false;
    final platformFilter = _normalizePlatformFilter(
      args['platform'] ?? args['execution_platform'] ?? args['mobile_platform'],
    );
    final limit = (args['limit'] is num)
        ? math.max(1, math.min(400, (args['limit'] as num).toInt()))
        : 240;
    final allRecords =
        _runtimeCatalogRecords(includeUnavailable: includeUnavailable)
            .where((record) => _recordMatchesPlatform(record, platformFilter))
            .toList();
    final records = allRecords.take(limit).toList();
    return MobileToolResult(
      ok: true,
      summary: '${records.length} tools',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'agent_template': _agentTemplateRecord(),
          'tool_surface': _toolSurfaceRecord(pcDelegationAvailable),
          'platform_filter': platformFilter,
          'platform_summary': _platformSummary(allRecords),
          'tools': records,
          'manifest_tool_agent_count':
              _defaultspackToolAgentManifestCatalog.length,
          'truncated': allRecords.length > records.length,
        },
      }),
    );
  }

  MobileToolResult _toolSchema(Map<String, dynamic> args) {
    final requested =
        '${args['tool_name'] ?? args['name'] ?? args['tool_id'] ?? ''}'.trim();
    if (requested.isEmpty) {
      return const MobileToolResult(
        ok: false,
        summary: 'tool_name is required',
        output: 'tool_name is required',
      );
    }
    final canonical = _canonicalToolName(requested);
    final entry = _findDefaultspackCatalogEntry(requested) ??
        _findDefaultspackCatalogEntry(canonical);
    final tool = _findToolDefinition(canonical);
    final record = entry != null
        ? _decorateCatalogRecord(
            _catalogEntryRecord(entry, requestedName: requested),
          )
        : tool == null
            ? _decorateCatalogRecord(_unsupportedToolRecord(canonical))
            : _decorateCatalogRecord(
                _toolRecord(tool, requestedName: requested));
    return MobileToolResult(
      ok: true,
      summary: '${record['tool_id']} schema',
      output: jsonEncode({
        'status': 'ok',
        'data': record,
      }),
    );
  }

  MobileToolResult _toolInvoke(Map<String, dynamic> args) {
    final requested =
        '${args['tool_name'] ?? args['tool_id'] ?? args['name'] ?? ''}'.trim();
    if (requested.isEmpty) {
      return MobileToolResult(
        ok: false,
        summary: 'tool_name is required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'MISSING_PARAM',
            'message': 'tool_name is required',
          },
        }),
      );
    }

    final canonical = _canonicalToolName(requested);
    if (canonical == 'tool_invoke') {
      return MobileToolResult(
        ok: false,
        summary: 'recursive tool_invoke is not allowed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'RECURSIVE_TOOL_INVOKE',
            'message': 'tool_invoke cannot invoke itself',
          },
        }),
      );
    }

    final tool = _findToolDefinition(canonical);
    final invokeArgs = _invokeArguments(args);
    if (tool != null && tool.available) {
      final result = execute(
        MobileToolCall(
          id: 'tool_invoke:${DateTime.now().microsecondsSinceEpoch}',
          name: canonical,
          arguments: invokeArgs,
        ),
      );
      return MobileToolResult(
        ok: result.ok,
        summary: '${tool.name}: ${result.summary}',
        output: jsonEncode({
          'status': result.ok ? 'ok' : 'error',
          'data': {
            'tool_name': tool.name,
            'requested_tool_name': requested,
            'result': result.output,
            'summary': result.summary,
            'is_error': !result.ok,
            'execution_location': 'phone',
          },
        }),
      );
    }

    final entry = _findDefaultspackCatalogEntry(requested) ??
        _findDefaultspackCatalogEntry(canonical);
    final record = entry == null
        ? _decorateCatalogRecord(_unsupportedToolRecord(canonical))
        : _decorateCatalogRecord(
            _catalogEntryRecord(entry, requestedName: requested),
          );
    final reason = '${record['unavailable_reason'] ?? ''}'.trim();
    return MobileToolResult(
      ok: false,
      summary: '${record['tool_id'] ?? requested}: unavailable on phone',
      output: jsonEncode({
        'status': 'error',
        'error': {
          'code': 'TOOL_UNAVAILABLE_ON_PHONE',
          'message': reason.isEmpty
              ? 'This tool is not executable in the phone-local runtime.'
              : reason,
          'details': record,
        },
      }),
    );
  }

  List<Map<String, dynamic>> _runtimeCatalogRecords({
    required bool includeUnavailable,
  }) {
    return _catalogRecords(includeUnavailable: includeUnavailable)
        .map(_decorateCatalogRecord)
        .toList();
  }

  Map<String, dynamic> _decorateCatalogRecord(Map<String, dynamic> record) {
    final decorated = Map<String, dynamic>.from(record);
    final phoneCompatible = decorated['mobile_compatible'] == true;
    final executionRoute = phoneCompatible
        ? 'phone'
        : pcDelegationAvailable
            ? 'pc'
            : 'unavailable';
    decorated['pc_delegation_available'] = pcDelegationAvailable;
    decorated['callable'] = phoneCompatible || pcDelegationAvailable;
    decorated['callable_on_current_device'] =
        phoneCompatible || pcDelegationAvailable;
    decorated['execution_route'] = executionRoute;
    decorated['automatic_routing'] = {
      'enabled': true,
      'one_tool_surface': true,
      'selected_route': executionRoute,
      'phone_local': phoneCompatible,
      'pc_delegation_available': pcDelegationAvailable,
      'pc_delegation_route': '/api/mobile/v1/tools/invoke',
    };
    if (!phoneCompatible) {
      decorated['pc_delegation'] = {
        'available': pcDelegationAvailable,
        'route': '/api/mobile/v1/tools/invoke',
        'required_setting': 'PC環境のtoolを使う',
        'execution_location': 'pc',
      };
      if (pcDelegationAvailable) {
        decorated['unavailable_reason'] =
            '${decorated['unavailable_reason'] ?? ''} PC接続と「PC環境のtoolを使う」が有効なので、tool_invoke経由で接続中PCのdefaultspack runtimeへ委譲できます。';
      }
    }
    return decorated;
  }

  MobileToolResult _agentPlan(Map<String, dynamic> args) {
    final action = '${args['action'] ?? 'create'}'.trim().toLowerCase();
    if (action == 'clear') {
      final count = _mobileAgentPlans.length;
      _mobileAgentPlans.clear();
      return MobileToolResult(
        ok: true,
        summary: 'cleared $count plans',
        output: jsonEncode({
          'status': 'ok',
          'data': {'cleared': count, 'plans': _mobileAgentPlans},
        }),
      );
    }
    if (action == 'list' || action == 'show' || action == 'status') {
      return _agentStatus(args, 'agent_plan');
    }
    final objective =
        '${args['objective'] ?? args['title'] ?? args['task'] ?? ''}'.trim();
    final steps = _normalizePlanSteps(args['steps'] ?? args['plan']);
    final plan = {
      'id': _nextToolId('plan'),
      'title': objective.isEmpty ? 'Mobile agent plan' : objective,
      'objective': objective,
      'steps': steps,
      'status': 'active',
      'created_at': DateTime.now().millisecondsSinceEpoch,
      'updated_at': DateTime.now().millisecondsSinceEpoch,
    };
    _mobileAgentPlans.add(plan);
    return MobileToolResult(
      ok: true,
      summary: '${steps.length} step plan',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'plan': plan,
          'agent_template': _agentTemplateRecord(),
        },
      }),
    );
  }

  MobileToolResult _agentStatus(Map<String, dynamic> args, String toolName) {
    final openTodos =
        _mobileTodos.where((todo) => todo['status'] != 'done').length;
    final activePlans = _mobileAgentPlans
        .where((plan) => '${plan['status'] ?? ''}' != 'done')
        .toList();
    final data = {
      'tool': toolName,
      'status':
          activePlans.isEmpty && _mobileTaskCards.isEmpty ? 'idle' : 'active',
      'agent_template': _agentTemplateRecord(),
      'plans': _mobileAgentPlans,
      'task_board': _taskBoardSnapshot(),
      'todos': _mobileTodos,
      'summary': {
        'plans': _mobileAgentPlans.length,
        'active_plans': activePlans.length,
        'task_cards': _mobileTaskCards.length,
        'todos': _mobileTodos.length,
        'open_todos': openTodos,
      },
    };
    return MobileToolResult(
      ok: true,
      summary:
          '${activePlans.length} active plans, ${_mobileTaskCards.length} cards, $openTodos open todos',
      output: jsonEncode({
        'status': 'ok',
        'data': data,
      }),
    );
  }

  MobileToolResult _assistantProgress(Map<String, dynamic> args) {
    final payload = normalizeAssistantProgressPayload(args);
    final summary = '${payload['summary']}';
    return MobileToolResult(
      ok: true,
      summary: summary,
      output: jsonEncode({
        'status': 'ok',
        'summary': summary,
        'next_action': payload['next_action'],
        'data': payload,
      }),
    );
  }

  String _unsupportedReason(String name) {
    final normalized = name.trim().toLowerCase();
    for (final tool in unavailableDefaultspackTools) {
      if (normalized == tool.name ||
          tool.tags.contains(normalized) ||
          tool.aliases.contains(normalized)) {
        return tool.unavailableReason;
      }
    }
    if (normalized == 'media_clipboard_read' ||
        normalized == 'media_clipboard_write') {
      return 'このdefaultspack toolはiOS Swift/Android Kotlinのclipboard bridgeでスマホ実装可能ですが、clipboard読み書き用のモバイル承認UIがまだないため、このスマホ単体では実行しません。PC接続時はPC側runtimeへ委譲できます。';
    }
    final catalogEntry = _findDefaultspackCatalogEntry(normalized);
    if (catalogEntry != null) {
      return _unsupportedReasonForTags(normalized, catalogEntry.tags);
    }
    if (normalized.startsWith('coding_') ||
        normalized.startsWith('sandbox_') ||
        normalized.contains('terminal') ||
        normalized.contains('workspace') ||
        normalized.contains('git_')) {
      return 'このdefaultspack toolはPC側のcoding/workspace/terminal runtimeに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
    }
    if (normalized.startsWith('browser_')) {
      return 'このdefaultspack toolはPC側のbrowser sessionに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
    }
    if (normalized.startsWith('computer_')) {
      return 'このdefaultspack toolはPC画面の操作権限が必要なため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
    }
    if (normalized.startsWith('agent_')) {
      return 'このdefaultspack toolはPC側のagent serviceまたはagent queueに依存するため、このスマホ単体では実行できません。スマホ内agentではmobile-compatible toolだけを実行します。';
    }
    if (normalized.startsWith('ai_')) {
      return 'このdefaultspack toolはPC側のAI provider catalog/routing/key管理に依存します。スマホ単体では設定済みモデルへのチャットとmobile-compatible tool実行に対応しています。';
    }
    if (normalized.startsWith('chat_')) {
      return 'このdefaultspack toolはPC側の会話storeに依存します。PC接続時はPCスペースで実行し、スマホ単体ではローカル会話として送信してください。';
    }
    if (normalized.startsWith('media_') ||
        normalized.startsWith('ambient_') ||
        normalized.startsWith('input_endpoint_')) {
      return 'このdefaultspack toolはPC側のOS/media/input runtimeに依存するため、このスマホ単体ではまだ実行できません。';
    }
    if (normalized.startsWith('memory_') ||
        normalized.startsWith('knowledge_') ||
        normalized.startsWith('artifact_')) {
      return 'このdefaultspack toolはPC側のprofile/workspace storageに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
    }
    if (normalized.startsWith('tool_')) {
      return 'このdefaultspack toolはPC側のtool registryまたは外部serviceに依存するため、このスマホ単体では未対応です。mobile-compatible tag付きtoolだけをスマホ内で実行できます。';
    }
    return 'このtoolはこのスマホのmobile-compatible runtimeに未登録です。PC接続時はPC側のtool catalogを確認してください。';
  }
}

String _canonicalToolName(String name) {
  final normalized = name.trim().toLowerCase();
  for (final tool in [
    ...MobileToolRuntime.supportedTools,
    ...MobileToolRuntime.unavailableDefaultspackTools,
  ]) {
    if (normalized == tool.name || tool.aliases.contains(normalized)) {
      return tool.name;
    }
  }
  return normalized;
}

bool _isAsyncPhoneToolName(String name) {
  return const {
    'media_clipboard_read',
    'media_clipboard_write',
    'media_file_pick',
    'mobile_url_open',
  }.contains(name.trim().toLowerCase());
}

bool _isOpenAiFunctionName(String name) {
  final trimmed = name.trim();
  return RegExp(r'^[a-zA-Z0-9_-]{1,64}$').hasMatch(trimmed);
}

Map<String, dynamic> _agentTemplateRecord() => {
      'template_id': mobileAgentTemplateId,
      'ai_input_id': mobileAgentAiInputId,
      'tool_policy_id': mobileAgentToolPolicyId,
    };

Map<String, dynamic> _toolSurfaceRecord(bool pcDelegationAvailable) => {
      'mode': 'unified',
      'one_tool_surface': true,
      'phone_local_route': 'phone',
      'pc_delegation_route': '/api/mobile/v1/tools/invoke',
      'pc_delegation_available': pcDelegationAvailable,
      'routing':
          'Call the defaultspack tool name directly. Phone-compatible tools run locally; host-bound tools route to the connected PC when PC delegation is available.',
    };

MobileToolDefinition? _findToolDefinition(String name) {
  final normalized = name.trim().toLowerCase();
  for (final tool in [
    ...MobileToolRuntime.supportedTools,
    ...MobileToolRuntime.unavailableDefaultspackTools,
  ]) {
    if (normalized == tool.name || tool.aliases.contains(normalized)) {
      return tool;
    }
  }
  return null;
}

DefaultspackToolAgentManifestEntry? _findDefaultspackCatalogEntry(String name) {
  final normalized = name.trim().toLowerCase();
  if (normalized.isEmpty) return null;
  for (final entry in _defaultspackToolAgentManifestCatalog) {
    if (entry.id == normalized || entry.aliases.contains(normalized)) {
      return entry;
    }
  }
  return null;
}

List<Map<String, dynamic>> _catalogRecords({
  required bool includeUnavailable,
}) {
  final records = <Map<String, dynamic>>[];
  final seenFunctionIds = <String>{};
  for (final entry in _defaultspackToolAgentManifestCatalog) {
    final record = _catalogEntryRecord(entry);
    if (includeUnavailable || record['mobile_compatible'] == true) {
      records.add(record);
    }
    seenFunctionIds.add(entry.id);
  }

  for (final tool in MobileToolRuntime.supportedTools) {
    final coveredByManifest = seenFunctionIds.contains(tool.name) ||
        tool.aliases.any((alias) => seenFunctionIds.contains(alias));
    if (coveredByManifest) continue;
    records.add(_toolRecord(tool, functionId: tool.name));
    seenFunctionIds.add(tool.name);
  }

  if (includeUnavailable) {
    for (final tool in MobileToolRuntime.unavailableDefaultspackTools) {
      final coveredByManifest = seenFunctionIds.contains(tool.name) ||
          tool.aliases.any((alias) => seenFunctionIds.contains(alias));
      if (coveredByManifest) continue;
      records.add(_toolRecord(tool, functionId: tool.name));
      seenFunctionIds.add(tool.name);
    }
  }

  return records;
}

Map<String, dynamic> _catalogEntryRecord(
  DefaultspackToolAgentManifestEntry entry, {
  String requestedName = '',
}) {
  final canonical = _canonicalToolName(entry.id);
  final tool = _findToolDefinition(canonical);
  if (tool != null) {
    final record = _toolRecord(
      tool,
      functionId: entry.id,
      requestedName: requestedName.isEmpty ? entry.id : requestedName,
    );
    record['summary'] =
        entry.description.isEmpty ? record['summary'] : entry.description;
    record['manifest_tags'] = entry.tags;
    record['aliases'] = {
      ...entry.aliases,
      ...(record['aliases'] as List? ?? const []),
    }.map((alias) => '$alias').toList()
      ..sort();
    if (!tool.available) {
      record['parameters'] = entry.inputSchema;
    }
    record['tags'] = _orderedStrings([
      ...entry.tags,
      ...(record['tags'] as List? ?? const []),
    ]);
    return record;
  }
  final record = _unsupportedToolRecord(entry.id);
  record['function_id'] = entry.id;
  if (requestedName.trim().isNotEmpty) {
    record['requested_name'] = requestedName.trim();
  }
  record['aliases'] = entry.aliases;
  record['summary'] =
      entry.description.isEmpty ? record['summary'] : entry.description;
  record['manifest_tags'] = entry.tags;
  record['tags'] = _orderedStrings([
    ...entry.tags,
    ...(record['tags'] as List? ?? const []),
  ]);
  record['parameters'] = entry.inputSchema;
  return record;
}

Map<String, dynamic> _toolRecord(
  MobileToolDefinition tool, {
  String functionId = '',
  String requestedName = '',
}) {
  final mobile = _mobileRuntimeRecordForTool(tool);
  return {
    'function_id': functionId.trim().isEmpty ? tool.name : functionId.trim(),
    'tool_id': tool.name,
    if (requestedName.trim().isNotEmpty) 'requested_name': requestedName,
    'aliases': tool.aliases,
    'tags': _orderedStrings([
      ...tool.tags,
      ...(mobile['tags'] as List? ?? const []),
    ]),
    'mobile_compatible': tool.available,
    'mobile': mobile,
    'execution_location': mobile['execution_location'],
    'execution_platforms': mobile['platforms'],
    'mobile_runtime_layers': mobile['runtime_layers'],
    'native_layers': mobile['native_layers'],
    'requires_mobile_approval': tool.requiresMobileApproval,
    'unavailable_reason': tool.unavailableReason,
    'summary': tool.description,
    'parameters': tool.parameters,
  };
}

Map<String, dynamic> _mobileRuntimeRecordForTool(MobileToolDefinition tool) {
  if (!tool.available) {
    return _mobileRuntimeRecordForUnavailable(
      tool.name,
      tool.tags,
      tool.unavailableReason,
    );
  }
  return {
    'compatible': true,
    'available': true,
    'execution_location': 'phone',
    'platforms': tool.executionPlatforms,
    'runtime_layers': tool.runtimeLayers,
    'native_layers': tool.nativeLayers,
    'requires_pc': false,
    'requires_mobile_approval': tool.requiresMobileApproval,
    'implementation_status': 'implemented',
    'tags': _mobilePlatformTags(
      platforms: tool.executionPlatforms,
      runtimeLayers: tool.runtimeLayers,
      pcDelegated: false,
    ),
  };
}

Map<String, dynamic> _mobileRuntimeRecordForUnavailable(
  String name,
  List<String> tags,
  String reason,
) {
  final plan = _mobilePortPlan(name, tags);
  return {
    'compatible': false,
    'available': false,
    'execution_location': 'pc',
    'platforms': plan['platforms'],
    'runtime_layers': plan['runtime_layers'],
    'native_layers': plan['native_layers'],
    'requires_pc': true,
    'requires_mobile_approval': plan['requires_mobile_approval'],
    'implementation_status': plan['implementation_status'],
    'unavailable_reason': reason,
    'tags': _mobilePlatformTags(
      platforms: (plan['platforms'] as List? ?? const []).map((e) => '$e'),
      runtimeLayers:
          (plan['runtime_layers'] as List? ?? const []).map((e) => '$e'),
      pcDelegated: true,
    ),
  };
}

Map<String, dynamic> _mobilePortPlan(String name, List<String> tags) {
  final normalized = name.trim().toLowerCase();
  final tagSet = tags.map((tag) => tag.trim().toLowerCase()).toSet();
  final isClipboard = normalized == 'media_clipboard_read' ||
      normalized == 'media_clipboard_write';
  final isMediaPicker = normalized == 'media_file_pick';
  if (isClipboard) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': ['flutter', 'ios-swift', 'android-kotlin'],
      'native_layers': [
        'ios:Swift UIPasteboard',
        'android:Kotlin ClipboardManager',
      ],
      'requires_mobile_approval': true,
      'implementation_status': 'implemented',
    };
  }
  if (isMediaPicker) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _nativeMediaPickerRuntimeLayers,
      'native_layers': [
        'ios:Swift UIDocumentPickerViewController',
        'android:Kotlin Intent.ACTION_OPEN_DOCUMENT',
      ],
      'requires_mobile_approval': true,
      'implementation_status': 'implemented',
    };
  }
  if (tagSet.contains('media') ||
      normalized.startsWith('audio_') ||
      normalized.startsWith('image_') ||
      normalized.startsWith('ocr_')) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': ['flutter', 'ios-swift', 'android-kotlin', 'provider'],
      'native_layers': [
        'ios:Swift media/photo permission bridge',
        'android:Kotlin media permission bridge',
      ],
      'requires_mobile_approval': true,
      'implementation_status': 'feasible_needs_picker_permission_or_provider',
    };
  }
  if (tagSet.contains('browser') && normalized != 'browser_open_url') {
    return const {
      'platforms': [],
      'runtime_layers': ['pc-browser-session'],
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'pc_browser_session_only',
    };
  }
  if (tagSet.any({
    'desktop',
    'computer',
    'computer_use',
    'workspace',
    'sandbox',
    'terminal',
    'agent_os',
  }.contains)) {
    return const {
      'platforms': [],
      'runtime_layers': ['pc-defaultspack-runtime'],
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'pc_only',
    };
  }
  if (tagSet.contains('agent')) {
    return const {
      'platforms': [],
      'runtime_layers': ['pc-agent-service'],
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'pc_agent_runtime_only',
    };
  }
  if (tagSet.any({'connector', 'integration', 'external'}.contains)) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': ['flutter', 'oauth-or-provider'],
      'native_layers': [],
      'requires_mobile_approval': true,
      'implementation_status': 'feasible_needs_mobile_oauth_or_connector',
    };
  }
  return const {
    'platforms': [],
    'runtime_layers': ['pc-defaultspack-runtime'],
    'native_layers': [],
    'requires_mobile_approval': false,
    'implementation_status': 'pc_delegation_required',
  };
}

List<String> _mobilePlatformTags({
  required Iterable<String> platforms,
  required Iterable<String> runtimeLayers,
  required bool pcDelegated,
}) {
  final normalizedPlatforms =
      platforms.map((value) => value.trim().toLowerCase()).toSet();
  final normalizedLayers =
      runtimeLayers.map((value) => value.trim().toLowerCase()).toSet();
  final tags = <String>[
    if (normalizedLayers.contains('flutter') ||
        normalizedLayers.contains('dart'))
      mobileFlutterTag,
    if (normalizedPlatforms.contains('ios')) mobileIosTag,
    if (normalizedPlatforms.contains('android')) mobileAndroidTag,
    if (normalizedLayers.any((layer) => layer.contains('swift')))
      mobileSwiftNativeTag,
    if (normalizedLayers.any((layer) => layer.contains('kotlin')))
      mobileKotlinNativeTag,
    if (pcDelegated) mobilePcDelegatedTag,
  ];
  return _orderedStrings(tags);
}

String _openAiCatalogDescription(Map<String, dynamic> record) {
  final summary = '${record['summary'] ?? ''}'.trim();
  final location = '${record['execution_location'] ?? ''}'.trim();
  final route = '${record['execution_route'] ?? ''}'.trim();
  final platforms =
      (record['execution_platforms'] as List? ?? const []).join(', ');
  final runtimeLayers =
      (record['mobile_runtime_layers'] as List? ?? const []).join(', ');
  if (record['mobile_compatible'] == true) {
    return [
      if (summary.isNotEmpty) summary,
      'Execution: phone-local defaultspack-compatible runtime.',
      if (platforms.isNotEmpty) 'Mobile platforms: $platforms.',
      if (runtimeLayers.isNotEmpty) 'Runtime layers: $runtimeLayers.',
    ].join(' ');
  }
  final reason = '${record['unavailable_reason'] ?? ''}'.trim();
  if (record['callable'] == true && route == 'pc') {
    return [
      if (summary.isNotEmpty) summary,
      'Execution: same mobile tool surface, delegated to the connected PC defaultspack runtime.',
      if (runtimeLayers.isNotEmpty) 'Runtime layers: $runtimeLayers.',
      if (reason.isNotEmpty) 'Phone-local note: $reason',
    ].join(' ');
  }
  return [
    if (summary.isNotEmpty) summary,
    'Execution: not phone-executable; calling this function returns the unavailable reason.',
    if (location.isNotEmpty) 'Required runtime: $location.',
    if (platforms.isNotEmpty) 'Potential mobile platforms: $platforms.',
    if (runtimeLayers.isNotEmpty) 'Runtime layers: $runtimeLayers.',
    if (reason.isNotEmpty) 'Reason: $reason',
  ].join(' ');
}

bool _shouldExportCatalogRecordAsNativeTool(Map<String, dynamic> record) {
  if (record['mobile_compatible'] == true) return true;
  final tags =
      (record['manifest_tags'] as List? ?? record['tags'] as List? ?? const [])
          .map((tag) => '$tag')
          .toSet();
  if (tags.contains('agent')) return true;
  return tags.contains('tool') && !tags.contains('tool_registry');
}

String? _normalizePlatformFilter(Object? value) {
  final text = '${value ?? ''}'.trim().toLowerCase();
  if (text.isEmpty || text == 'all') return null;
  return switch (text) {
    'ios' || 'iphone' || 'ipad' || 'swift' || 'swift-native' => 'ios',
    'android' || 'kotlin' || 'kotlin-native' => 'android',
    'flutter' || 'dart' => 'flutter',
    'pc' || 'desktop' || 'host' || 'defaultspack' => 'pc',
    _ => text,
  };
}

bool _recordMatchesPlatform(Map<String, dynamic> record, String? platform) {
  if (platform == null) return true;
  final mobile = record['mobile'] is Map ? record['mobile'] as Map : const {};
  final values = {
    '${record['execution_location'] ?? ''}',
    ...(record['execution_platforms'] as List? ?? const []).map((e) => '$e'),
    ...(record['mobile_runtime_layers'] as List? ?? const []).map((e) => '$e'),
    ...(record['native_layers'] as List? ?? const []).map((e) => '$e'),
    ...(record['tags'] as List? ?? const []).map((e) => '$e'),
    ...(mobile['platforms'] as List? ?? const []).map((e) => '$e'),
    ...(mobile['runtime_layers'] as List? ?? const []).map((e) => '$e'),
    ...(mobile['native_layers'] as List? ?? const []).map((e) => '$e'),
    ...(mobile['tags'] as List? ?? const []).map((e) => '$e'),
  }.map((value) => value.trim().toLowerCase()).toSet();
  if (platform == 'pc') {
    return values.contains('pc') ||
        values.contains('pc-delegated') ||
        values.contains(mobilePcDelegatedTag);
  }
  if (platform == 'flutter') {
    return values.contains('flutter') ||
        values.contains('dart') ||
        values.contains(mobileFlutterTag);
  }
  if (platform == 'ios') {
    return values.contains('ios') ||
        values.any((value) => value.contains('swift')) ||
        values.contains(mobileIosTag);
  }
  if (platform == 'android') {
    return values.contains('android') ||
        values.any((value) => value.contains('kotlin')) ||
        values.contains(mobileAndroidTag);
  }
  return values.contains(platform);
}

String _recordSearchText(Map<String, dynamic> record) {
  final mobile = record['mobile'] is Map ? record['mobile'] as Map : const {};
  return [
    record['function_id'],
    record['tool_id'],
    record['requested_name'],
    record['summary'],
    record['execution_location'],
    ...(record['execution_platforms'] as List? ?? const []),
    ...(record['mobile_runtime_layers'] as List? ?? const []),
    ...(record['native_layers'] as List? ?? const []),
    ...(record['tags'] as List? ?? const []),
    ...(record['aliases'] as List? ?? const []),
    mobile['implementation_status'],
    ...(mobile['platforms'] as List? ?? const []),
    ...(mobile['runtime_layers'] as List? ?? const []),
    ...(mobile['native_layers'] as List? ?? const []),
  ].join(' ').toLowerCase();
}

Map<String, dynamic> _platformSummary(List<Map<String, dynamic>> records) {
  int count(String platform) => records
      .where((record) => _recordMatchesPlatform(record, platform))
      .length;
  return {
    'flutter': count('flutter'),
    'ios': count('ios'),
    'android': count('android'),
    'pc': count('pc'),
  };
}

List<String> _orderedStrings(Iterable<Object?> values) {
  final output = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final text = '$value'.trim();
    if (text.isEmpty || seen.contains(text)) continue;
    seen.add(text);
    output.add(text);
  }
  return output;
}

String _currentMobilePlatform() {
  if (Platform.isIOS) return 'ios';
  if (Platform.isAndroid) return 'android';
  return Platform.operatingSystem;
}

String _unsupportedReasonForTags(String name, List<String> tags) {
  final normalized = name.trim().toLowerCase();
  final tagSet = tags.map((tag) => tag.trim().toLowerCase()).toSet();
  bool hasAny(Iterable<String> values) => values.any(tagSet.contains);

  if (normalized == 'media_clipboard_read' ||
      normalized == 'media_clipboard_write') {
    return 'このdefaultspack-compatible toolはiOS Swift/Android Kotlinのclipboard bridgeとモバイル承認UIでスマホ実装済みです。';
  }
  if (normalized == 'media_file_pick') {
    return 'このdefaultspack-compatible toolはiOS Swift/Android KotlinのOSファイルピッカーでスマホ実装済みです。';
  }
  if (hasAny(['desktop', 'computer_use', 'computer'])) {
    return 'このdefaultspack toolはPC側のdesktop/computer-use権限と画面状態に依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
  }
  if (hasAny(['browser'])) {
    return 'このdefaultspack toolはPC側のbrowser sessionに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
  }
  if (hasAny(['connector', 'integration', 'external'])) {
    return 'このdefaultspack toolはPC側のconnector認証、外部連携、または送信承認に依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
  }
  if (hasAny(['sandbox', 'agent_os', 'artifact_workspace']) ||
      normalized.endsWith('_exec')) {
    return 'このdefaultspack toolはPC側のagent OS、sandbox、artifact workspace、または実行承認に依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
  }
  if (hasAny([
    'artifact',
    'document',
    'spreadsheet',
    'presentation',
    'export',
    'media',
    'preview',
    'research',
    'source',
    'webapp',
    'workflow',
    'job',
  ])) {
    return 'このdefaultspack toolはPC側のartifact/media/workflow runtimeまたは外部providerに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
  }
  if (hasAny(['agent'])) {
    return 'このdefaultspack toolはPC側のagent serviceまたはagent queueに依存するため、このスマホ単体では実行できません。スマホ内agentではmobile-compatible toolだけを実行します。';
  }
  if (hasAny(['tool_registry', 'tool'])) {
    return 'このdefaultspack toolはPC側のtool registryまたはdefaultspack runtimeに依存するため、このスマホ単体では実行できません。mobile-compatible tag付きtoolだけをスマホ内で実行できます。';
  }
  return 'このdefaultspack toolはPC側defaultspack runtimeに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。';
}

Map<String, dynamic> _asObjectSchema(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.map((key, value) => MapEntry('$key', value));
  return const {'type': 'object', 'additionalProperties': true};
}

Map<String, dynamic> _invokeArguments(Map<String, dynamic> args) {
  for (final key in ['arguments', 'args', 'input']) {
    final value = args[key];
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return value.map((key, value) => MapEntry('$key', value));
    if (value is String && value.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(value);
        if (decoded is Map<String, dynamic>) return decoded;
        if (decoded is Map) {
          return decoded.map((key, value) => MapEntry('$key', value));
        }
      } catch (_) {
        return {'input': value.trim()};
      }
    }
  }
  return {
    for (final entry in args.entries)
      if (!{'tool_name', 'tool_id', 'name', 'context'}.contains(entry.key))
        entry.key: entry.value,
  };
}

Map<String, dynamic> _unsupportedToolRecord(String name) {
  final normalized = name.trim();
  final tags = _inferredDefaultspackTags(normalized);
  final reason = const MobileToolRuntime()._unsupportedReason(normalized);
  final mobile = _mobileRuntimeRecordForUnavailable(normalized, tags, reason);
  return {
    'function_id': normalized,
    'tool_id': normalized,
    'aliases': const <String>[],
    'tags': _orderedStrings([
      ...tags,
      ...(mobile['tags'] as List? ?? const []),
    ]),
    'mobile_compatible': false,
    'mobile': mobile,
    'execution_location': mobile['execution_location'],
    'execution_platforms': mobile['platforms'],
    'mobile_runtime_layers': mobile['runtime_layers'],
    'native_layers': mobile['native_layers'],
    'requires_mobile_approval': mobile['requires_mobile_approval'],
    'unavailable_reason': reason,
    'summary':
        'Defaultspack function is not executable in the phone-local runtime.',
    'parameters': {'type': 'object', 'additionalProperties': true},
  };
}

List<String> _inferredDefaultspackTags(String name) {
  final tags = <String>[];
  if (name.startsWith('agent_')) tags.add('agent');
  if (name.startsWith('tool_')) tags.add('tool');
  if (name.startsWith('browser_')) tags.addAll(['tool', 'browser']);
  if (name.startsWith('computer_')) tags.addAll(['tool', 'computer']);
  if (name.startsWith('media_')) tags.addAll(['tool', 'media']);
  if (name.startsWith('audio_')) tags.addAll(['tool', 'media', 'audio']);
  if (name.startsWith('image_')) tags.addAll(['tool', 'media', 'image']);
  if (name.startsWith('ocr_')) tags.addAll(['tool', 'media', 'ocr']);
  if (name.startsWith('coding_') || name.startsWith('sandbox_')) {
    tags.addAll(['tool', 'workspace']);
  }
  if (tags.isEmpty) tags.add('defaultspack');
  return tags.toSet().toList();
}

Map<String, dynamic> _decodeObject(String raw) {
  try {
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) {
      return decoded.map((key, value) => MapEntry('$key', value));
    }
  } catch (_) {
    return const {};
  }
  return const {};
}

String _clampText(Object? value, int limit) {
  final text = '$value'.trim();
  if (text.isEmpty || text == 'null') return '';
  if (text.length <= limit) return text;
  return text.substring(0, limit);
}

String _normalizeMediaPickKind(Object? value) {
  final raw = '${value ?? ''}'.trim().toLowerCase();
  if (raw == 'image' ||
      raw == 'photo' ||
      raw == 'picture' ||
      raw == 'png' ||
      raw == 'jpg' ||
      raw == 'jpeg') {
    return 'image';
  }
  if (raw == 'audio' || raw == 'sound' || raw == 'voice') {
    return 'audio';
  }
  return 'file';
}

int _boundedMediaPickMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardMediaPickMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardMediaPickMaxBytes, parsed));
  }
  return _defaultMediaPickMaxBytes;
}

final List<Map<String, dynamic>> _mobileTodos = [];
final Map<String, dynamic> _mobileTaskBoard = {
  'board_id': 'mobile-default',
  'title': 'Mobile Task Board',
  'columns': _taskBoardDefaultColumns,
};
final List<Map<String, dynamic>> _mobileTaskCards = [];
final List<Map<String, dynamic>> _mobileAgentPlans = [];
final Map<String, Map<String, dynamic>> _mobileConsents = {};
int _mobileToolIdSequence = 0;

String _nextToolId(String prefix) {
  _mobileToolIdSequence += 1;
  return '${prefix}_${DateTime.now().microsecondsSinceEpoch}_$_mobileToolIdSequence';
}

String _argId(Map<String, dynamic> args, String primaryKey) {
  return '${args[primaryKey] ?? args['id'] ?? ''}'.trim();
}

Map<String, dynamic>? _findById(
  List<Map<String, dynamic>> records,
  String id,
) {
  if (id.isEmpty) return null;
  for (final record in records) {
    if (record['id'] == id) return record;
  }
  return null;
}

List<String> _normalizeColumns(Object? raw) {
  if (raw is List) {
    final columns = raw
        .map((item) => '$item'.trim())
        .where((item) => item.isNotEmpty)
        .toList();
    if (columns.isNotEmpty) return columns;
  }
  if (raw is String && raw.trim().isNotEmpty) {
    final columns = raw
        .split(RegExp(r'[,|\n]'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
    if (columns.isNotEmpty) return columns;
  }
  return List<String>.from(_taskBoardDefaultColumns);
}

String _resolveColumn(Map<String, dynamic> args) {
  final requested = '${args['column'] ?? args['column_id'] ?? ''}'.trim();
  final columns = List<String>.from(_mobileTaskBoard['columns'] as List);
  if (requested.isEmpty) return columns.first;
  for (final column in columns) {
    if (column.toLowerCase() == requested.toLowerCase()) return column;
  }
  return requested;
}

List<Map<String, dynamic>> _subtasks(Map<String, dynamic> card) {
  final raw = card['subtasks'];
  if (raw is List<Map<String, dynamic>>) return raw;
  if (raw is List) {
    final subtasks = raw
        .whereType<Map>()
        .map((item) => item.map((key, value) => MapEntry('$key', value)))
        .toList();
    card['subtasks'] = subtasks;
    return subtasks;
  }
  final subtasks = <Map<String, dynamic>>[];
  card['subtasks'] = subtasks;
  return subtasks;
}

Map<String, dynamic> _taskBoardSnapshot() {
  return {
    'board_id': _mobileTaskBoard['board_id'],
    'title': _mobileTaskBoard['title'],
    'columns': _mobileTaskBoard['columns'],
    'cards': _mobileTaskCards,
  };
}

String _taskBoardSummary(String action) {
  final columns = List<String>.from(_mobileTaskBoard['columns'] as List);
  final counts = {
    for (final column in columns)
      column: _mobileTaskCards.where((card) => card['column'] == column).length,
  };
  final countsText =
      counts.entries.map((entry) => '${entry.key}:${entry.value}').join(', ');
  return '$action: ${_mobileTaskCards.length} cards ($countsText)';
}

List<String> _normalizePlanSteps(Object? raw) {
  final steps = <String>[];
  if (raw is List) {
    for (final item in raw) {
      final value = '$item'.trim();
      if (value.isNotEmpty) steps.add(value);
    }
  } else if (raw is String && raw.trim().isNotEmpty) {
    for (final line in raw.split(RegExp(r'[\n;]+'))) {
      final normalized =
          line.replaceFirst(RegExp(r'^\s*[-*\d.)]+\s*'), '').trim();
      if (normalized.isNotEmpty) steps.add(normalized);
    }
  }
  if (steps.isNotEmpty) return steps;
  return const ['状況を確認する', '必要な作業を実行する', '結果を検証する'];
}

String _formatNumber(double value) {
  if (value.isFinite && value == value.roundToDouble()) {
    return value.toInt().toString();
  }
  final fixed = value.toStringAsPrecision(12);
  return fixed.replaceFirst(RegExp(r'\.?0+$'), '');
}

class _ExpressionParser {
  _ExpressionParser(this.source);

  final String source;
  int _index = 0;

  double parse() {
    final value = _parseExpression();
    _skipWhitespace();
    if (_index != source.length) {
      throw FormatException('unexpected token "${source[_index]}"');
    }
    if (!value.isFinite) throw const FormatException('result is not finite');
    return value;
  }

  double _parseExpression() {
    var value = _parseTerm();
    while (true) {
      _skipWhitespace();
      if (_match('+')) {
        value += _parseTerm();
      } else if (_match('-')) {
        value -= _parseTerm();
      } else {
        return value;
      }
    }
  }

  double _parseTerm() {
    var value = _parsePower();
    while (true) {
      _skipWhitespace();
      if (_match('*')) {
        value *= _parsePower();
      } else if (_match('/')) {
        final rhs = _parsePower();
        if (rhs == 0) throw const FormatException('division by zero');
        value /= rhs;
      } else {
        return value;
      }
    }
  }

  double _parsePower() {
    var value = _parseUnary();
    _skipWhitespace();
    if (_match('^')) {
      value = math.pow(value, _parsePower()).toDouble();
    }
    return value;
  }

  double _parseUnary() {
    _skipWhitespace();
    if (_match('+')) return _parseUnary();
    if (_match('-')) return -_parseUnary();
    return _parsePrimary();
  }

  double _parsePrimary() {
    _skipWhitespace();
    if (_match('(')) {
      final value = _parseExpression();
      _skipWhitespace();
      if (!_match(')')) throw const FormatException('missing ")"');
      return value;
    }
    final start = _index;
    var sawDigit = false;
    while (_index < source.length) {
      final code = source.codeUnitAt(_index);
      final isDigit = code >= 48 && code <= 57;
      if (isDigit) {
        sawDigit = true;
        _index += 1;
        continue;
      }
      if (source[_index] == '.') {
        _index += 1;
        continue;
      }
      break;
    }
    if (!sawDigit) throw const FormatException('number expected');
    return double.parse(source.substring(start, _index));
  }

  bool _match(String char) {
    if (_index >= source.length || source[_index] != char) return false;
    _index += 1;
    return true;
  }

  void _skipWhitespace() {
    while (_index < source.length && source[_index].trim().isEmpty) {
      _index += 1;
    }
  }
}
