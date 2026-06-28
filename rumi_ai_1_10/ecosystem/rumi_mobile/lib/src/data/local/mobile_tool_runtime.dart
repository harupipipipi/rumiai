import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

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
const _nativeScreenshotRuntimeLayers = <String>[
  'flutter',
  'ios-swift',
  'android-kotlin',
];
const _nativeImageTransformRuntimeLayers = <String>[
  'flutter',
  'ios-swift',
  'android-kotlin',
];
const _nativeOcrRuntimeLayers = <String>[
  'flutter',
  'ios-swift',
  'android-kotlin',
];
const _defaultMediaPickMaxBytes = 4 * 1024 * 1024;
const _hardMediaPickMaxBytes = 8 * 1024 * 1024;
const _defaultScreenshotMaxBytes = 6 * 1024 * 1024;
const _hardScreenshotMaxBytes = 12 * 1024 * 1024;
const _defaultScreenshotMaxDimension = 1600;
const _hardScreenshotMaxDimension = 4096;
const _defaultImageReadMaxBytes = 8 * 1024 * 1024;
const _hardImageReadMaxBytes = 16 * 1024 * 1024;
const _defaultImageTransformOutputMaxBytes = 8 * 1024 * 1024;
const _hardImageTransformOutputMaxBytes = 16 * 1024 * 1024;
const _hardImageTransformInputMaxBytes = 24 * 1024 * 1024;
const _defaultImageTransformMaxDimension = 2048;
const _hardImageTransformMaxDimension = 4096;
const _defaultOcrMaxBytes = 8 * 1024 * 1024;
const _hardOcrMaxBytes = 16 * 1024 * 1024;
const _defaultDocParseMaxBytes = 2 * 1024 * 1024;
const _hardDocParseMaxBytes = 8 * 1024 * 1024;
const _defaultDocParseMaxChars = 120000;
const _hardDocParseMaxChars = 400000;
const _defaultPdfParseMaxBytes = 8 * 1024 * 1024;
const _hardPdfParseMaxBytes = 16 * 1024 * 1024;
const _defaultPdfParseMaxChars = 120000;
const _hardPdfParseMaxChars = 400000;
const _defaultSourceExtractMaxChars = 120000;
const _hardSourceExtractMaxChars = 400000;
const _defaultTtsFallbackDurationMs = 100;
const _hardTtsFallbackDurationMs = 30000;
const _defaultTtsFallbackSampleRate = 16000;
const _hardTtsFallbackSampleRate = 48000;
const _minTtsFallbackSampleRate = 8000;

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
    this.implementationStatus = 'implemented',
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
  final String implementationStatus;

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
    PlatformScreenshotCapture screenshotCapture =
        const PlatformScreenshotCapture(),
    PlatformImageTransformer imageTransformer =
        const PlatformImageTransformer(),
    PlatformOcrRecognizer ocrRecognizer = const PlatformOcrRecognizer(),
  })  : _pcDelegate = pcDelegate,
        _approvalDelegate = approvalDelegate,
        _urlLauncher = urlLauncher,
        _clipboard = clipboard,
        _mediaPicker = mediaPicker,
        _screenshotCapture = screenshotCapture,
        _imageTransformer = imageTransformer,
        _ocrRecognizer = ocrRecognizer;

  final MobileToolDelegate? _pcDelegate;
  final MobileToolApprovalDelegate? _approvalDelegate;
  final PlatformUrlLauncher _urlLauncher;
  final PlatformClipboard _clipboard;
  final PlatformMediaPicker _mediaPicker;
  final PlatformScreenshotCapture _screenshotCapture;
  final PlatformImageTransformer _imageTransformer;
  final PlatformOcrRecognizer _ocrRecognizer;

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
      name: 'media_screenshot',
      description:
          'Capture a PNG screenshot of the visible Rumi app window on this phone after explicit mobile approval.',
      tags: ['tool', 'media', 'screenshot', mobileCompatibleTag],
      aliases: [
        'screenshot',
        'mobile_screenshot',
        'defaults_media_screenshot',
        'defaultspack_media_screenshot',
        'defaults.media.screenshot',
        'defaultspack.media.screenshot',
      ],
      runtimeLayers: _nativeScreenshotRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIWindow screenshot capture',
        'android:Kotlin View drawing cache capture',
      ],
      requiresMobileApproval: true,
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'reason': {
            'type': 'string',
            'description': 'Why the current app screen should be captured.',
          },
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardScreenshotMaxBytes,
            'default': _defaultScreenshotMaxBytes,
          },
          'max_dimension': {
            'type': 'integer',
            'minimum': 320,
            'maximum': _hardScreenshotMaxDimension,
            'default': _defaultScreenshotMaxDimension,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_image_read',
      description:
          'Read metadata from PNG, JPEG, GIF, WebP, or BMP image bytes already provided to this phone runtime.',
      tags: ['tool', 'media', 'image', mobileCompatibleTag],
      aliases: [
        'image_read',
        'defaults_media_image_read',
        'defaultspack_media_image_read',
        'defaults.media.image.read',
        'defaults.media.image_read',
        'defaultspack.media.image.read',
        'defaultspack.media.image_read',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardImageReadMaxBytes,
            'default': _defaultImageReadMaxBytes,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_image_transform',
      description:
          'Resize and encode image bytes already provided to this phone runtime. Does not read host file paths.',
      tags: ['tool', 'media', 'image', 'transform', mobileCompatibleTag],
      aliases: [
        'image_transform',
        'defaults_media_image_transform',
        'defaultspack_media_image_transform',
        'defaults.media.image.transform',
        'defaults.media.image_transform',
        'defaultspack.media.image.transform',
        'defaultspack.media.image_transform',
      ],
      runtimeLayers: _nativeImageTransformRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIImage resize/encode',
        'android:Kotlin Bitmap resize/encode',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'operations': {
            'type': 'array',
            'items': {'type': 'object'},
          },
          'width': {'type': 'integer', 'minimum': 1},
          'height': {'type': 'integer', 'minimum': 1},
          'max_width': {'type': 'integer', 'minimum': 1},
          'max_height': {'type': 'integer', 'minimum': 1},
          'max_dimension': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardImageTransformMaxDimension,
            'default': _defaultImageTransformMaxDimension,
          },
          'format': {
            'type': 'string',
            'enum': ['jpeg', 'jpg', 'png'],
            'default': 'png',
          },
          'quality': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 100,
            'default': 90,
          },
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardImageTransformOutputMaxBytes,
            'default': _defaultImageTransformOutputMaxBytes,
          },
          'max_input_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardImageTransformInputMaxBytes,
            'default': _hardImageTransformInputMaxBytes,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_ocr',
      description:
          'Extract OCR text from image bytes already provided to this phone runtime using native iOS Vision or Android ML Kit.',
      tags: ['tool', 'media', 'image', 'ocr', mobileCompatibleTag],
      aliases: [
        'ocr',
        'defaults_media_ocr',
        'defaultspack_media_ocr',
        'defaults.media.ocr',
        'defaultspack.media.ocr',
      ],
      runtimeLayers: _nativeOcrRuntimeLayers,
      nativeLayers: [
        'ios:Swift Vision VNRecognizeTextRequest',
        'android:Kotlin ML Kit TextRecognition',
      ],
      implementationStatus: 'implemented_native_ocr_bridge',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'language_hint': {'type': 'string'},
          'language': {'type': 'string'},
          'locale': {'type': 'string'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardOcrMaxBytes,
            'default': _defaultOcrMaxBytes,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'ocr_extract',
      description:
          'Extract OCR text from image bytes already provided to this phone runtime. PC artifact paths are delegated to the PC runtime.',
      tags: [
        'tool',
        'media',
        'image',
        'ocr',
        'artifact_workspace',
        mobileCompatibleTag,
      ],
      aliases: [
        'defaults_ocr_extract',
        'defaultspack_ocr_extract',
        'defaults.ocr.extract',
        'defaultspack.ocr.extract',
      ],
      runtimeLayers: _nativeOcrRuntimeLayers,
      nativeLayers: [
        'ios:Swift Vision VNRecognizeTextRequest',
        'android:Kotlin ML Kit TextRecognition',
      ],
      implementationStatus: 'implemented_payload_only_native_ocr',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'path': {'type': 'string'},
          'language_hint': {'type': 'string'},
          'language': {'type': 'string'},
          'locale': {'type': 'string'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardOcrMaxBytes,
            'default': _defaultOcrMaxBytes,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'image_resize',
      description:
          'Resize image bytes already provided to this phone runtime using the native iOS Swift / Android Kotlin image bridge. Does not read or write PC artifact paths.',
      tags: ['tool', 'media', 'image', 'resize', mobileCompatibleTag],
      aliases: [
        'defaults_image_resize',
        'defaultspack_image_resize',
        'defaults.image.resize',
        'defaultspack.image.resize',
      ],
      runtimeLayers: _nativeImageTransformRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIImage resize/encode',
        'android:Kotlin Bitmap resize/encode',
      ],
      implementationStatus: 'implemented_payload_only',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'path': {'type': 'string'},
          'output_path': {'type': 'string'},
          'width': {'type': 'integer', 'minimum': 1},
          'height': {'type': 'integer', 'minimum': 1},
          'format': {
            'type': 'string',
            'enum': ['jpeg', 'jpg', 'png'],
            'default': 'png',
          },
          'quality': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 100,
            'default': 90,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'image_convert',
      description:
          'Convert image bytes already provided to this phone runtime using the native iOS Swift / Android Kotlin image bridge. Does not read or write PC artifact paths.',
      tags: ['tool', 'media', 'image', 'convert', mobileCompatibleTag],
      aliases: [
        'defaults_image_convert',
        'defaultspack_image_convert',
        'defaults.image.convert',
        'defaultspack.image.convert',
      ],
      runtimeLayers: _nativeImageTransformRuntimeLayers,
      nativeLayers: [
        'ios:Swift UIImage resize/encode',
        'android:Kotlin Bitmap resize/encode',
      ],
      implementationStatus: 'implemented_payload_only',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'image_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'image': {'type': 'object'},
          'file': {'type': 'object'},
          'path': {'type': 'string'},
          'output_path': {'type': 'string'},
          'format': {
            'type': 'string',
            'enum': ['jpeg', 'jpg', 'png'],
            'default': 'png',
          },
          'quality': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 100,
            'default': 90,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'tts_generate',
      description:
          'Generate a phone-local fallback WAV audio payload in Flutter/Dart. This does not synthesize spoken speech yet and does not write PC artifact paths.',
      tags: ['tool', 'media', 'audio', 'tts', mobileCompatibleTag],
      aliases: [
        'defaults_tts_generate',
        'defaultspack_tts_generate',
        'defaults.tts.generate',
        'defaultspack.tts.generate',
      ],
      implementationStatus: 'implemented_silent_wav_fallback',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'text': {'type': 'string'},
          'output_path': {'type': 'string'},
          'duration_ms': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardTtsFallbackDurationMs,
            'default': _defaultTtsFallbackDurationMs,
          },
          'sample_rate': {
            'type': 'integer',
            'minimum': _minTtsFallbackSampleRate,
            'maximum': _hardTtsFallbackSampleRate,
            'default': _defaultTtsFallbackSampleRate,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'tts_generate_local',
      description:
          'Generate a phone-local fallback WAV audio payload in Flutter/Dart. This mirrors defaultspack local TTS fallback without writing PC artifact paths.',
      tags: ['tool', 'media', 'audio', 'tts', mobileCompatibleTag],
      aliases: [
        'defaults_tts_generate_local',
        'defaultspack_tts_generate_local',
        'defaults.tts.generate_local',
        'defaultspack.tts.generate_local',
      ],
      implementationStatus: 'implemented_silent_wav_fallback',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'text': {'type': 'string'},
          'output_path': {'type': 'string'},
          'duration_ms': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardTtsFallbackDurationMs,
            'default': _defaultTtsFallbackDurationMs,
          },
          'sample_rate': {
            'type': 'integer',
            'minimum': _minTtsFallbackSampleRate,
            'maximum': _hardTtsFallbackSampleRate,
            'default': _defaultTtsFallbackSampleRate,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_doc_parse',
      description:
          'Parse text-like document bytes or text already provided to this phone runtime. Supports txt, markdown, json, csv, html, xml, and similar UTF text; does not read host file paths.',
      tags: ['tool', 'media', 'document', 'text', mobileCompatibleTag],
      aliases: [
        'doc_parse',
        'document_parse',
        'defaults_media_doc_parse',
        'defaultspack_media_doc_parse',
        'defaults.media.doc.parse',
        'defaults.media.doc_parse',
        'defaultspack.media.doc.parse',
        'defaultspack.media.doc_parse',
      ],
      implementationStatus: 'implemented_text_documents',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'text': {'type': 'string'},
          'content': {'type': 'string'},
          'base64': {'type': 'string'},
          'document_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'file': {'type': 'object'},
          'document': {'type': 'object'},
          'name': {'type': 'string'},
          'mime_type': {'type': 'string'},
          'format': {'type': 'string'},
          'encoding': {'type': 'string'},
          'strip_html': {'type': 'boolean', 'default': true},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardDocParseMaxBytes,
            'default': _defaultDocParseMaxBytes,
          },
          'max_chars': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardDocParseMaxChars,
            'default': _defaultDocParseMaxChars,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'media_pdf_parse',
      description:
          'Extract best-effort text from PDF bytes already provided to this phone runtime. Does not read host file paths and does not perform full layout/table parsing.',
      tags: ['tool', 'media', 'pdf', 'document', mobileCompatibleTag],
      aliases: [
        'pdf_parse',
        'defaults_media_pdf_parse',
        'defaultspack_media_pdf_parse',
        'defaults.media.pdf.parse',
        'defaults.media.pdf_parse',
        'defaultspack.media.pdf.parse',
        'defaultspack.media.pdf_parse',
      ],
      implementationStatus: 'implemented_best_effort_bytes',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'pdf_base64': {'type': 'string'},
          'document_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'file': {'type': 'object'},
          'document': {'type': 'object'},
          'name': {'type': 'string'},
          'mime_type': {'type': 'string'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardPdfParseMaxBytes,
            'default': _defaultPdfParseMaxBytes,
          },
          'max_chars': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardPdfParseMaxChars,
            'default': _defaultPdfParseMaxChars,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'pdf_extract',
      description:
          'Extract best-effort text from PDF bytes already provided to this phone runtime. Does not read PC artifact paths.',
      tags: ['tool', 'media', 'pdf', 'document', mobileCompatibleTag],
      aliases: [
        'defaults_pdf_extract',
        'defaultspack_pdf_extract',
        'defaults.pdf.extract',
        'defaultspack.pdf.extract',
      ],
      implementationStatus: 'implemented_best_effort_bytes',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'pdf_base64': {'type': 'string'},
          'document_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'file': {'type': 'object'},
          'document': {'type': 'object'},
          'path': {'type': 'string'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardPdfParseMaxBytes,
            'default': _defaultPdfParseMaxBytes,
          },
          'max_chars': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardPdfParseMaxChars,
            'default': _defaultPdfParseMaxChars,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'pdf_extract_tables',
      description:
          'Return a phone-local PDF table extraction fallback for PDF bytes already provided to this phone runtime. Full table extraction remains PC/provider-only.',
      tags: ['tool', 'media', 'pdf', 'table', mobileCompatibleTag],
      aliases: [
        'defaults_pdf_extract_tables',
        'defaultspack_pdf_extract_tables',
        'defaults.pdf.extract_tables',
        'defaultspack.pdf.extract_tables',
      ],
      implementationStatus: 'implemented_empty_table_fallback',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'base64': {'type': 'string'},
          'pdf_base64': {'type': 'string'},
          'document_base64': {'type': 'string'},
          'data_url': {'type': 'string'},
          'file': {'type': 'object'},
          'document': {'type': 'object'},
          'path': {'type': 'string'},
          'max_bytes': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardPdfParseMaxBytes,
            'default': _defaultPdfParseMaxBytes,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'source_extract',
      description:
          'Extract text and title metadata from source text, HTML, or URL payloads already provided to this phone runtime. Does not read PC workspace paths.',
      tags: ['tool', 'research', 'source', 'text', mobileCompatibleTag],
      aliases: [
        'defaults_source_extract',
        'defaultspack_source_extract',
        'defaults.source.extract',
        'defaultspack.source.extract',
      ],
      implementationStatus: 'implemented_payload_only',
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'source': {'type': 'string'},
          'path': {'type': 'string'},
          'url': {'type': 'string'},
          'title': {'type': 'string'},
          'text': {'type': 'string'},
          'content': {'type': 'string'},
          'html': {'type': 'string'},
          'strip_html': {'type': 'boolean', 'default': true},
          'max_chars': {
            'type': 'integer',
            'minimum': 1,
            'maximum': _hardSourceExtractMaxChars,
            'default': _defaultSourceExtractMaxChars,
          },
        },
      },
    ),
    MobileToolDefinition(
      name: 'source_rank',
      description:
          'Rank provided source snippets by query term frequency locally on this phone.',
      tags: ['tool', 'research', 'source', 'ranking', mobileCompatibleTag],
      aliases: [
        'defaults_source_rank',
        'defaultspack_source_rank',
        'defaults.source.rank',
        'defaultspack.source.rank',
      ],
      parameters: {
        'type': 'object',
        'additionalProperties': true,
        'properties': {
          'query': {'type': 'string'},
          'sources': {
            'type': 'array',
            'items': {
              'type': 'object',
              'additionalProperties': true,
              'properties': {
                'title': {'type': 'string'},
                'content': {'type': 'string'},
                'source': {'type': 'string'},
              },
            },
          },
        },
        'required': ['query', 'sources'],
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
      case 'media_screenshot':
      case 'media_image_transform':
      case 'media_ocr':
      case 'ocr_extract':
      case 'image_resize':
      case 'image_convert':
        return _asyncOnlyTool(name);
      case 'media_image_read':
        return _mediaImageRead(call.arguments);
      case 'media_doc_parse':
        return _mediaDocParse(call.arguments);
      case 'media_pdf_parse':
        return _mediaPdfParse(call.arguments);
      case 'pdf_extract':
        return _pdfExtract(call.arguments);
      case 'pdf_extract_tables':
        return _pdfExtractTables(call.arguments);
      case 'tts_generate':
      case 'tts_generate_local':
        return _ttsGenerate(call.arguments, toolName: name);
      case 'source_extract':
        return _sourceExtract(call.arguments);
      case 'source_rank':
        return _sourceRank(call.arguments);
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
      case 'media_screenshot':
        return _mediaScreenshot(call.arguments);
      case 'media_image_transform':
        return _mediaImageTransform(call.arguments);
      case 'media_ocr':
      case 'ocr_extract':
        return _mediaOcr(call.arguments, toolName: name);
      case 'image_resize':
      case 'image_convert':
        return _mediaImageTransform(
          _imageToolTransformArguments(call.arguments, toolName: name),
        );
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
      'media_screenshot',
      'media_image_transform',
      'media_ocr',
      'ocr_extract',
      'media_image_read',
      'media_doc_parse',
      'media_pdf_parse',
      'source_rank',
      'tts_generate',
      'tts_generate_local',
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

  MobileToolResult _mediaImageRead(Map<String, dynamic> args) {
    final maxBytes = _boundedImageReadMaxBytes(args['max_bytes']);
    final base64Image = _extractImageBase64(args);
    if (base64Image == null || base64Image.trim().isEmpty) {
      final path = '${args['path'] ?? ''}'.trim();
      return MobileToolResult(
        ok: false,
        summary: 'image bytes are required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': path.isEmpty ? 'MISSING_IMAGE_BYTES' : 'UNSUPPORTED_PATH',
            'message': path.isEmpty
                ? 'base64, image_base64, data_url, image.base64, or file.base64 is required.'
                : 'Phone-local media_image_read cannot read host file paths. Use media_file_pick or pass base64 image bytes.',
            if (path.isNotEmpty) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }
    try {
      final bytes = base64Decode(_stripDataUrlPrefix(base64Image));
      if (bytes.length > maxBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'image is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'IMAGE_TOO_LARGE',
              'message': 'Image bytes are larger than max_bytes.',
              'size_bytes': bytes.length,
              'max_bytes': maxBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }
      final metadata = _readImageHeader(bytes);
      if (metadata == null) {
        return MobileToolResult(
          ok: false,
          summary: 'unsupported image format',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'UNSUPPORTED_IMAGE_FORMAT',
              'message':
                  'Only PNG, JPEG, GIF, WebP, and BMP headers are supported on this phone.',
              'size_bytes': bytes.length,
              'execution_location': 'phone',
            },
          }),
        );
      }
      return MobileToolResult(
        ok: true,
        summary: '${metadata.format} ${metadata.width}x${metadata.height}',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'width': metadata.width,
            'height': metadata.height,
            'format': metadata.format,
            'mime_type': metadata.mimeType,
            'size_bytes': bytes.length,
            'execution_location': 'phone',
            'runtime_layers': _flutterRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'image read failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'IMAGE_READ_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  Future<MobileToolResult> _mediaImageTransform(
    Map<String, dynamic> args,
  ) async {
    final base64Image = _extractImageBase64(args);
    if (base64Image == null || base64Image.trim().isEmpty) {
      final path = '${args['path'] ?? ''}'.trim();
      return MobileToolResult(
        ok: false,
        summary: 'image bytes are required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': path.isEmpty ? 'MISSING_IMAGE_BYTES' : 'UNSUPPORTED_PATH',
            'message': path.isEmpty
                ? 'base64, image_base64, data_url, image.base64, or file.base64 is required.'
                : 'Phone-local media_image_transform cannot read host file paths. Use media_file_pick or pass base64 image bytes.',
            if (path.isNotEmpty) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }

    try {
      final bytes = base64Decode(_stripDataUrlPrefix(base64Image));
      final maxInputBytes =
          _boundedImageTransformInputMaxBytes(args['max_input_bytes']);
      if (bytes.length > maxInputBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'image is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'IMAGE_TOO_LARGE',
              'message': 'Image bytes are larger than max_input_bytes.',
              'size_bytes': bytes.length,
              'max_input_bytes': maxInputBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }

      final format = _normalizeImageTransformFormat(
        args['format'] ?? args['output_format'] ?? args['mime_type'],
      );
      final quality = _boundedImageQuality(args['quality']);
      final dimensions = _imageTransformDimensions(args);
      final maxBytes = _boundedImageTransformOutputMaxBytes(args['max_bytes']);
      final transformed = await _imageTransformer.transform(
        base64Data: base64Encode(bytes),
        outputFormat: format,
        quality: quality,
        maxWidth: dimensions.maxWidth,
        maxHeight: dimensions.maxHeight,
        maxBytes: maxBytes,
      );
      if (transformed.size > maxBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'transformed image is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'IMAGE_TRANSFORM_TOO_LARGE',
              'message': 'Transformed image is larger than max_bytes.',
              'size': transformed.size,
              'max_bytes': maxBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }
      final metadata = _readImageHeader(bytes);
      final operations = _imageTransformOperationsApplied(
        args,
        format: format,
        dimensions: dimensions,
      );
      return MobileToolResult(
        ok: true,
        summary: 'transformed image ${transformed.width}x${transformed.height}',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'mime_type': transformed.mimeType,
            'format': _mimeToImageFormat(transformed.mimeType, format),
            'size': transformed.size,
            'size_bytes': transformed.size,
            'width': transformed.width,
            'height': transformed.height,
            'base64': transformed.base64Data,
            'encoding': 'base64',
            'operations_applied': operations,
            'quality': quality,
            'input': {
              'size_bytes': bytes.length,
              if (metadata != null) 'width': metadata.width,
              if (metadata != null) 'height': metadata.height,
              if (metadata != null) 'format': metadata.format,
              if (metadata != null) 'mime_type': metadata.mimeType,
            },
            'execution_location': 'phone',
            'runtime_layers': _nativeImageTransformRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'image transform failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'IMAGE_TRANSFORM_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  Future<MobileToolResult> _mediaOcr(
    Map<String, dynamic> args, {
    required String toolName,
  }) async {
    final base64Image = _extractImageBase64(args);
    if (base64Image == null || base64Image.trim().isEmpty) {
      final path = '${args['path'] ?? ''}'.trim();
      return MobileToolResult(
        ok: false,
        summary: 'image bytes are required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': path.isEmpty ? 'MISSING_IMAGE_BYTES' : 'UNSUPPORTED_PATH',
            'message': path.isEmpty
                ? 'base64, image_base64, data_url, image.base64, or file.base64 is required.'
                : 'Phone-local $toolName cannot read host artifact paths. Use media_file_pick/pass image bytes or route this call to the connected PC runtime.',
            if (path.isNotEmpty) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }

    try {
      final bytes = base64Decode(_stripDataUrlPrefix(base64Image));
      final maxBytes = _boundedOcrMaxBytes(args['max_bytes']);
      if (bytes.length > maxBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'image is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'IMAGE_TOO_LARGE',
              'message': 'Image bytes are larger than max_bytes.',
              'size_bytes': bytes.length,
              'max_bytes': maxBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }
      final metadata = _readImageHeader(bytes);
      final languageHint = _stringOrNull(
        args['language_hint'] ?? args['language'] ?? args['locale'],
      );
      final recognized = await _ocrRecognizer.recognize(
        base64Data: base64Encode(bytes),
        maxBytes: maxBytes,
        languageHint: languageHint,
      );
      final text = recognized.text.trim();
      return MobileToolResult(
        ok: true,
        summary: text.isEmpty
            ? 'OCR found no text'
            : 'OCR ${text.length} chars: ${_clampText(text.replaceAll(RegExp(r'\s+'), ' '), 80)}',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'text': text,
            'content': text,
            'length': text.length,
            'blocks': recognized.blocks.map((block) => block.toJson()).toList(),
            'block_count': recognized.blocks.length,
            if (recognized.languageCode != null)
              'language_code': recognized.languageCode,
            'input': {
              'size_bytes': bytes.length,
              if (metadata != null) 'width': metadata.width,
              if (metadata != null) 'height': metadata.height,
              if (metadata != null) 'format': metadata.format,
              if (metadata != null) 'mime_type': metadata.mimeType,
            },
            'metadata': {
              'tool': toolName,
              'payload_only': true,
              'native_ocr': true,
              if (languageHint != null) 'language_hint': languageHint,
            },
            'execution_location': 'phone',
            'runtime_layers': _nativeOcrRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'OCR failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'OCR_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  MobileToolResult _mediaDocParse(Map<String, dynamic> args) {
    final _DocumentPayload? payload;
    try {
      payload = _extractDocumentPayload(args);
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'document content is invalid',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'INVALID_DOCUMENT_CONTENT',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
    if (payload == null) {
      final path = '${args['path'] ?? ''}'.trim();
      return MobileToolResult(
        ok: false,
        summary: 'document content is required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code':
                path.isEmpty ? 'MISSING_DOCUMENT_CONTENT' : 'UNSUPPORTED_PATH',
            'message': path.isEmpty
                ? 'text, content, base64, data_url, file.base64, or document.base64 is required.'
                : 'Phone-local media_doc_parse cannot read host file paths. Use media_file_pick or pass document text/base64.',
            if (path.isNotEmpty) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }

    final maxBytes = _boundedDocParseMaxBytes(args['max_bytes']);
    final maxChars = _boundedDocParseMaxChars(args['max_chars']);
    if (payload.sizeBytes > maxBytes) {
      return MobileToolResult(
        ok: false,
        summary: 'document is too large',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'DOCUMENT_TOO_LARGE',
            'message': 'Document content is larger than max_bytes.',
            'size_bytes': payload.sizeBytes,
            'max_bytes': maxBytes,
            'execution_location': 'phone',
          },
        }),
      );
    }
    final format = _normalizeDocumentFormat(
      args['format'] ?? payload.format,
      mimeType: '${args['mime_type'] ?? payload.mimeType ?? ''}',
      name: '${args['name'] ?? payload.name ?? ''}',
    );
    final unsupportedReason = _unsupportedPhoneDocumentReason(
      format: format,
      mimeType: payload.mimeType,
      name: payload.name,
      explicitText: payload.text != null,
    );
    if (unsupportedReason != null) {
      return MobileToolResult(
        ok: false,
        summary: 'document format is unsupported on phone',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'UNSUPPORTED_DOCUMENT_FORMAT',
            'message': unsupportedReason,
            'format': format,
            if (payload.mimeType != null) 'mime_type': payload.mimeType,
            if (payload.name != null) 'name': payload.name,
            'execution_location': 'phone',
          },
        }),
      );
    }

    try {
      final decoded = payload.text == null
          ? _decodeDocumentBytes(payload.bytes ?? Uint8List(0), maxBytes)
          : null;
      final decodedText = payload.text ?? decoded!.text;
      final parsed = _parsePhoneDocumentText(
        decodedText,
        format: format,
        stripHtml: args['strip_html'] != false,
      );
      final truncated = parsed.length > maxChars;
      final content = truncated ? parsed.substring(0, maxChars) : parsed;
      return MobileToolResult(
        ok: true,
        summary: 'parsed ${content.length} chars',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'content': content,
            'truncated': truncated,
            'length': parsed.length,
            'returned_length': content.length,
            'metadata': {
              'format': format,
              if (payload.name != null) 'name': payload.name,
              if (payload.mimeType != null) 'mime_type': payload.mimeType,
              'encoding': payload.text != null ? 'string' : decoded!.encoding,
              'source': payload.source,
              'size_bytes': payload.sizeBytes,
              'supported_formats': _phoneTextDocumentFormats.toList()..sort(),
            },
            'execution_location': 'phone',
            'runtime_layers': _flutterRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    } on _UnsupportedDocumentEncoding catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'document encoding unsupported',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'UNSUPPORTED_DOCUMENT_ENCODING',
            'message': error.message,
            'execution_location': 'phone',
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'document parse failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'DOCUMENT_PARSE_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  MobileToolResult _mediaPdfParse(Map<String, dynamic> args) {
    final _DocumentPayload? payload;
    try {
      payload = _extractDocumentPayload(args);
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'PDF content is invalid',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'INVALID_PDF_CONTENT',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
    if (payload == null) {
      final path = '${args['path'] ?? ''}'.trim();
      return MobileToolResult(
        ok: false,
        summary: 'PDF bytes are required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': path.isEmpty ? 'MISSING_PDF_BYTES' : 'UNSUPPORTED_PATH',
            'message': path.isEmpty
                ? 'base64, pdf_base64, data_url, file.base64, or document.base64 is required.'
                : 'Phone-local media_pdf_parse cannot read host file paths. Use media_file_pick or pass PDF base64 bytes.',
            if (path.isNotEmpty) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }
    final maxBytes = _boundedPdfParseMaxBytes(args['max_bytes']);
    final maxChars = _boundedPdfParseMaxChars(args['max_chars']);
    if (payload.sizeBytes > maxBytes) {
      return MobileToolResult(
        ok: false,
        summary: 'PDF is too large',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'PDF_TOO_LARGE',
            'message': 'PDF content is larger than max_bytes.',
            'size_bytes': payload.sizeBytes,
            'max_bytes': maxBytes,
            'execution_location': 'phone',
          },
        }),
      );
    }

    try {
      final bytes = payload.bytes ??
          Uint8List.fromList(latin1.encode(payload.text ?? ''));
      final raw = _decodePdfBytesForScan(bytes);
      final looksPdf = raw.startsWith('%PDF') ||
          (payload.mimeType ?? '').trim().toLowerCase() == 'application/pdf' ||
          (payload.name ?? '').trim().toLowerCase().endsWith('.pdf');
      final extraction = _extractBestEffortPdfText(raw);
      final text = extraction.text;
      final truncated = text.length > maxChars;
      final content = truncated ? text.substring(0, maxChars) : text;
      return MobileToolResult(
        ok: true,
        summary: content.isEmpty
            ? 'PDF parsed with no extractable text'
            : 'parsed PDF ${content.length} chars',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'content': content,
            'text': content,
            'truncated': truncated,
            'length': text.length,
            'returned_length': content.length,
            'metadata': {
              'format': 'pdf',
              if (payload.name != null) 'name': payload.name,
              if (payload.mimeType != null) 'mime_type': payload.mimeType,
              'source': payload.source,
              'size_bytes': payload.sizeBytes,
              'looks_like_pdf': looksPdf,
              'method': extraction.method,
              'best_effort': true,
              'full_layout_supported': false,
              'tables_supported': false,
            },
            'execution_location': 'phone',
            'runtime_layers': _flutterRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'PDF parse failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'PDF_PARSE_FAILED',
            'message': '$error',
            'execution_location': 'phone',
          },
        }),
      );
    }
  }

  MobileToolResult _pdfExtract(Map<String, dynamic> args) {
    final parsed = _mediaPdfParse(args);
    if (!parsed.ok) return parsed;
    final payload = _decodeObject(parsed.output);
    final data = payload['data'];
    final parsedData = data is Map<String, dynamic>
        ? data
        : data is Map
            ? data.map((key, value) => MapEntry('$key', value))
            : const <String, dynamic>{};
    final metadataRaw = parsedData['metadata'];
    final metadata = metadataRaw is Map<String, dynamic>
        ? metadataRaw
        : metadataRaw is Map
            ? metadataRaw.map((key, value) => MapEntry('$key', value))
            : const <String, dynamic>{};
    final text = '${parsedData['text'] ?? parsedData['content'] ?? ''}';
    return MobileToolResult(
      ok: true,
      summary: 'extracted PDF ${text.length} chars',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'text': text,
          'content': text,
          'fallback': metadata['method'] ?? 'best_effort_phone_pdf_scan',
          'length': parsedData['length'] ?? text.length,
          'returned_length': parsedData['returned_length'] ?? text.length,
          'truncated': parsedData['truncated'] ?? false,
          'metadata': {
            ...metadata,
            'payload_only': true,
            'tables_supported': false,
          },
          'execution_location': 'phone',
          'runtime_layers': _flutterRuntimeLayers,
          'requires_mobile_approval': false,
        },
      }),
    );
  }

  MobileToolResult _pdfExtractTables(Map<String, dynamic> args) {
    final parsed = _mediaPdfParse({...args, 'max_chars': 4000});
    if (!parsed.ok) return parsed;
    final payload = _decodeObject(parsed.output);
    final data = payload['data'];
    final parsedData = data is Map<String, dynamic>
        ? data
        : data is Map
            ? data.map((key, value) => MapEntry('$key', value))
            : const <String, dynamic>{};
    return MobileToolResult(
      ok: true,
      summary: 'PDF table extraction fallback returned 0 tables',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'tables': const <dynamic>[],
          'table_count': 0,
          'text_preview': parsedData['content'] ?? '',
          'missing_dependency':
              'Full PDF table extraction requires the connected PC/provider runtime.',
          'metadata': {
            'payload_only': true,
            'best_effort': true,
            'tables_supported': false,
          },
          'execution_location': 'phone',
          'runtime_layers': _flutterRuntimeLayers,
          'requires_mobile_approval': false,
        },
      }),
    );
  }

  MobileToolResult _ttsGenerate(
    Map<String, dynamic> args, {
    required String toolName,
  }) {
    final text = '${args['text'] ?? ''}';
    final durationMs = _boundedTtsFallbackDurationMs(args['duration_ms']);
    final sampleRate = _boundedTtsFallbackSampleRate(args['sample_rate']);
    final wav = _silentWavBytes(
      durationMs: durationMs,
      sampleRate: sampleRate,
    );
    final outputPath = _stringOrNull(args['output_path']);
    return MobileToolResult(
      ok: true,
      summary: 'generated fallback WAV ${wav.length} bytes',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'mime_type': 'audio/wav',
          'format': 'wav',
          'encoding': 'base64',
          'base64': base64Encode(wav),
          'size': wav.length,
          'size_bytes': wav.length,
          'sample_rate': sampleRate,
          'channels': 1,
          'bits_per_sample': 16,
          'duration_ms': durationMs,
          'fallback': 'silent_wav',
          'text_length': text.length,
          if (outputPath != null) 'requested_output_path': outputPath,
          'metadata': {
            'tool': toolName,
            'payload_only': true,
            'real_tts_supported': false,
            'native_tts_bridge': false,
          },
          'execution_location': 'phone',
          'runtime_layers': _flutterRuntimeLayers,
          'requires_mobile_approval': false,
        },
      }),
    );
  }

  MobileToolResult _sourceExtract(Map<String, dynamic> args) {
    final maxChars = _boundedSourceExtractMaxChars(args['max_chars']);
    final url = _stringOrNull(args['url']) ??
        (_looksLikeHttpUrl('${args['source'] ?? ''}')
            ? '${args['source']}'.trim()
            : null);
    if (url != null) {
      return MobileToolResult(
        ok: true,
        summary: 'source url placeholder',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'source': url,
            'title': _stringOrNull(args['title']) ?? url,
            'content': '',
            'length': 0,
            'network_required': true,
            'metadata': {
              'input_kind': 'url',
              'payload_only': true,
            },
            'execution_location': 'phone',
            'runtime_layers': _flutterRuntimeLayers,
            'requires_mobile_approval': false,
          },
        }),
      );
    }

    final rawHtml = _stringOrNull(args['html']);
    final rawText = _stringOrNull(args['text']) ??
        _stringOrNull(args['content']) ??
        _sourceArgumentAsInlineText(args['source']);
    final path = _stringOrNull(args['path']) ??
        ((rawText == null && url == null)
            ? _stringOrNull(args['source'])
            : null);
    if (rawHtml == null && rawText == null) {
      return MobileToolResult(
        ok: false,
        summary: 'source payload is required',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code':
                path == null ? 'MISSING_SOURCE_PAYLOAD' : 'UNSUPPORTED_PATH',
            'message': path == null
                ? 'text, content, html, url, or inline source text is required.'
                : 'Phone-local source_extract cannot read PC workspace paths. PC接続時はPC側runtimeへ委譲できます。',
            if (path != null) 'path': path,
            'execution_location': 'phone',
          },
        }),
      );
    }

    final input = rawHtml ?? rawText ?? '';
    final title = _stringOrNull(args['title']) ??
        (rawHtml == null ? null : _extractHtmlTitle(rawHtml)) ??
        'Phone source';
    final content = (rawHtml != null && args['strip_html'] != false)
        ? _stripHtmlToText(rawHtml)
        : input;
    final clean = _normalizeSourceText(content);
    final truncated = clean.length > maxChars;
    final returned = truncated ? clean.substring(0, maxChars) : clean;
    return MobileToolResult(
      ok: true,
      summary: 'source extracted ${returned.length} chars',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'source': rawHtml != null ? 'arguments.html' : 'arguments.text',
          'title': title,
          'content': returned,
          'length': clean.length,
          'returned_length': returned.length,
          'truncated': truncated,
          'network_required': false,
          'metadata': {
            'input_kind': rawHtml != null ? 'html' : 'text',
            'payload_only': true,
          },
          'execution_location': 'phone',
          'runtime_layers': _flutterRuntimeLayers,
          'requires_mobile_approval': false,
        },
      }),
    );
  }

  MobileToolResult _sourceRank(Map<String, dynamic> args) {
    final query = '${args['query'] ?? ''}'.toLowerCase();
    final rawSources = args['sources'];
    final sources = rawSources is List ? rawSources : const [];
    final terms = _splitSourceRankTerms(query);
    final ranked = <Map<String, dynamic>>[];
    for (var index = 0; index < sources.length; index += 1) {
      final source = sources[index];
      final text = _sourceRankText(source).toLowerCase();
      final score = terms.fold<int>(
        0,
        (sum, term) =>
            sum + RegExp(RegExp.escape(term)).allMatches(text).length,
      );
      ranked.add({
        'source': _sourceRankSourceObject(source),
        'score': score,
        '_index': index,
      });
    }
    ranked.sort((left, right) {
      final scoreCompare =
          (right['score'] as int).compareTo(left['score'] as int);
      if (scoreCompare != 0) return scoreCompare;
      return (left['_index'] as int).compareTo(right['_index'] as int);
    });
    for (final item in ranked) {
      item.remove('_index');
    }
    return MobileToolResult(
      ok: true,
      summary: 'ranked ${ranked.length} sources',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'query': query,
          'ranked_sources': ranked,
          'terms': terms,
          'execution_location': 'phone',
          'runtime_layers': _flutterRuntimeLayers,
          'requires_mobile_approval': false,
        },
      }),
    );
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

  Future<MobileToolResult> _mediaScreenshot(Map<String, dynamic> args) async {
    final maxBytes = _boundedScreenshotMaxBytes(args['max_bytes']);
    final maxDimension = _boundedScreenshotMaxDimension(args['max_dimension']);
    final approved = await _requestMobileApproval(
      toolName: 'media_screenshot',
      risk: 'high',
      arguments: {
        ...args,
        'max_bytes': maxBytes,
        'max_dimension': maxDimension,
        'capture_scope': 'app_window',
      },
      prompt: 'このスマホで表示中のRumiアプリ画面をPNG画像として取得します。画面内の会話や設定がAIのtool結果として渡されます。',
    );
    if (!approved) return _mobileApprovalRequired('media_screenshot');

    try {
      final screenshot = await _screenshotCapture.capture(
        maxBytes: maxBytes,
        maxDimension: maxDimension,
      );
      if (screenshot.size > maxBytes) {
        return MobileToolResult(
          ok: false,
          summary: 'screenshot is too large',
          output: jsonEncode({
            'status': 'error',
            'error': {
              'code': 'MEDIA_SCREENSHOT_TOO_LARGE',
              'message': 'Captured screenshot is larger than max_bytes.',
              'size': screenshot.size,
              'max_bytes': maxBytes,
              'execution_location': 'phone',
            },
          }),
        );
      }
      return MobileToolResult(
        ok: true,
        summary:
            'captured app screenshot ${screenshot.width}x${screenshot.height}',
        output: jsonEncode({
          'status': 'ok',
          'data': {
            'name': 'rumi-app-screenshot.png',
            'mime_type': screenshot.mimeType,
            'size': screenshot.size,
            'width': screenshot.width,
            'height': screenshot.height,
            'base64': screenshot.base64Data,
            'encoding': 'base64',
            'capture_scope': 'app_window',
            'execution_location': 'phone',
            'runtime_layers': _nativeScreenshotRuntimeLayers,
            'requires_mobile_approval': true,
          },
        }),
      );
    } catch (error) {
      return MobileToolResult(
        ok: false,
        summary: 'screenshot capture failed',
        output: jsonEncode({
          'status': 'error',
          'error': {
            'code': 'MEDIA_SCREENSHOT_FAILED',
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
    'media_screenshot',
    'media_image_transform',
    'media_ocr',
    'ocr_extract',
    'image_resize',
    'image_convert',
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
    'implementation_status': tool.implementationStatus,
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
  final isScreenshot = normalized == 'media_screenshot';
  final isImageRead = normalized == 'media_image_read';
  final isImageTransform = normalized == 'media_image_transform';
  final isImagePayloadTool =
      normalized == 'image_resize' || normalized == 'image_convert';
  final isOcrTool = normalized == 'media_ocr' || normalized == 'ocr_extract';
  final isDocParse = normalized == 'media_doc_parse';
  final isPdfParse = normalized == 'media_pdf_parse';
  final isPdfPayloadTool =
      normalized == 'pdf_extract' || normalized == 'pdf_extract_tables';
  final isSourcePayloadTool =
      normalized == 'source_extract' || normalized == 'source_rank';
  final isTtsFallbackTool =
      normalized == 'tts_generate' || normalized == 'tts_generate_local';
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
  if (isScreenshot) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _nativeScreenshotRuntimeLayers,
      'native_layers': [
        'ios:Swift UIWindow screenshot capture',
        'android:Kotlin View drawing cache capture',
      ],
      'requires_mobile_approval': true,
      'implementation_status': 'implemented',
    };
  }
  if (isImageRead) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented',
    };
  }
  if (isImageTransform) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _nativeImageTransformRuntimeLayers,
      'native_layers': [
        'ios:Swift UIImage resize/encode',
        'android:Kotlin Bitmap resize/encode',
      ],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented',
    };
  }
  if (isImagePayloadTool) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _nativeImageTransformRuntimeLayers,
      'native_layers': [
        'ios:Swift UIImage resize/encode',
        'android:Kotlin Bitmap resize/encode',
      ],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented_payload_only',
    };
  }
  if (isOcrTool) {
    return {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _nativeOcrRuntimeLayers,
      'native_layers': const [
        'ios:Swift Vision VNRecognizeTextRequest',
        'android:Kotlin ML Kit TextRecognition',
      ],
      'requires_mobile_approval': false,
      'implementation_status': normalized == 'ocr_extract'
          ? 'implemented_payload_only_native_ocr'
          : 'implemented_native_ocr_bridge',
    };
  }
  if (isDocParse) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented_text_documents',
    };
  }
  if (isPdfParse) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented_best_effort_bytes',
    };
  }
  if (isPdfPayloadTool) {
    return {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': normalized == 'pdf_extract_tables'
          ? 'implemented_empty_table_fallback'
          : 'implemented_best_effort_bytes',
    };
  }
  if (isSourcePayloadTool) {
    return {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': normalized == 'source_extract'
          ? 'implemented_payload_only'
          : 'implemented',
    };
  }
  if (isTtsFallbackTool) {
    return const {
      'platforms': _defaultMobilePlatforms,
      'runtime_layers': _flutterRuntimeLayers,
      'native_layers': [],
      'requires_mobile_approval': false,
      'implementation_status': 'implemented_silent_wav_fallback',
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
  if (normalized == 'media_screenshot') {
    return 'このdefaultspack-compatible toolはiOS Swift/Android KotlinのRumiアプリ画面captureでスマホ実装済みです。';
  }
  if (normalized == 'media_image_read') {
    return 'このdefaultspack-compatible toolはDartの画像ヘッダー解析でスマホ実装済みです。';
  }
  if (normalized == 'media_image_transform') {
    return 'このdefaultspack-compatible toolはiOS Swift/Android Kotlinの画像resize/encode bridgeでスマホ実装済みです。';
  }
  if (normalized == 'image_resize' || normalized == 'image_convert') {
    return 'このdefaultspack-compatible toolはiOS Swift/Android Kotlinの画像resize/encode bridgeで渡されたimage bytesのpayload-only変換にスマホ対応済みです。PC artifact path入出力はPC runtimeへ委譲してください。';
  }
  if (normalized == 'media_ocr') {
    return 'このdefaultspack-compatible toolはiOS Swift Vision / Android Kotlin ML KitのOCR bridgeでスマホ実装済みです。';
  }
  if (normalized == 'ocr_extract') {
    return 'このdefaultspack-compatible toolはiOS Swift Vision / Android Kotlin ML Kitで渡されたimage bytesのpayload-only OCRにスマホ対応済みです。PC artifact pathはPC runtimeへ委譲してください。';
  }
  if (normalized == 'media_doc_parse') {
    return 'このdefaultspack-compatible toolはDartでtext/markdown/json/csv/html/xml等のテキスト系document parseをスマホ実装済みです。PDF/docx等はPC runtimeへ委譲してください。';
  }
  if (normalized == 'media_pdf_parse') {
    return 'このdefaultspack-compatible toolはDartで渡されたPDF bytesのbest-effort text抽出にスマホ対応済みです。フルlayout/table抽出はPC runtimeへ委譲してください。';
  }
  if (normalized == 'pdf_extract') {
    return 'このdefaultspack-compatible toolはDartで渡されたPDF bytesのbest-effort text抽出にスマホ対応済みです。PC artifact pathはPC runtimeへ委譲してください。';
  }
  if (normalized == 'pdf_extract_tables') {
    return 'このdefaultspack-compatible toolはスマホでは空table fallbackまで対応済みです。フルPDF table抽出はPC runtimeへ委譲してください。';
  }
  if (normalized == 'source_extract') {
    return 'このdefaultspack-compatible toolはDartで渡されたtext/html/url payloadの抽出にスマホ対応済みです。PC workspace pathはPC runtimeへ委譲してください。';
  }
  if (normalized == 'source_rank') {
    return 'このdefaultspack-compatible toolはDartで渡されたsource snippetsのterm frequency rankingにスマホ対応済みです。';
  }
  if (normalized == 'tts_generate' || normalized == 'tts_generate_local') {
    return 'このdefaultspack-compatible toolはFlutter/Dartでsilent WAV fallback payload生成にスマホ対応済みです。実音声TTS合成とPC artifact保存はPC/native runtimeへ委譲してください。';
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

int _boundedScreenshotMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardScreenshotMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardScreenshotMaxBytes, parsed));
  }
  return _defaultScreenshotMaxBytes;
}

int _boundedScreenshotMaxDimension(Object? value) {
  if (value is num) {
    return math.max(320, math.min(_hardScreenshotMaxDimension, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(320, math.min(_hardScreenshotMaxDimension, parsed));
  }
  return _defaultScreenshotMaxDimension;
}

int _boundedImageReadMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardImageReadMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardImageReadMaxBytes, parsed));
  }
  return _defaultImageReadMaxBytes;
}

int _boundedImageTransformOutputMaxBytes(Object? value) {
  if (value is num) {
    return math.max(
      1,
      math.min(_hardImageTransformOutputMaxBytes, value.toInt()),
    );
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardImageTransformOutputMaxBytes, parsed));
  }
  return _defaultImageTransformOutputMaxBytes;
}

int _boundedImageTransformInputMaxBytes(Object? value) {
  if (value is num) {
    return math.max(
      1,
      math.min(_hardImageTransformInputMaxBytes, value.toInt()),
    );
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardImageTransformInputMaxBytes, parsed));
  }
  return _hardImageTransformInputMaxBytes;
}

int _boundedImageQuality(Object? value) {
  if (value is num) {
    return math.max(1, math.min(100, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) return math.max(1, math.min(100, parsed));
  return 90;
}

int _boundedOcrMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardOcrMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardOcrMaxBytes, parsed));
  }
  return _defaultOcrMaxBytes;
}

int? _positiveImageTransformDimension(Object? value) {
  if (value is num) {
    return math.max(
      1,
      math.min(_hardImageTransformMaxDimension, value.toInt()),
    );
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed == null) return null;
  return math.max(1, math.min(_hardImageTransformMaxDimension, parsed));
}

String _normalizeImageTransformFormat(Object? value) {
  final raw = '${value ?? ''}'.trim().toLowerCase();
  if (raw == 'jpg' || raw == 'jpeg' || raw == 'image/jpeg') return 'jpeg';
  if (raw == 'png' || raw == 'image/png' || raw.isEmpty) return 'png';
  return 'png';
}

_ImageTransformDimensions _imageTransformDimensions(Map<String, dynamic> args) {
  int? maxWidth;
  int? maxHeight;

  void apply(Object? width, Object? height, Object? maxDimension) {
    final dimension = _positiveImageTransformDimension(maxDimension);
    maxWidth = _positiveImageTransformDimension(width) ?? maxWidth;
    maxHeight = _positiveImageTransformDimension(height) ?? maxHeight;
    if (dimension != null) {
      maxWidth ??= dimension;
      maxHeight ??= dimension;
    }
  }

  final operations = args['operations'];
  if (operations is List) {
    for (final operation in operations) {
      if (operation is! Map) continue;
      final type =
          '${operation['type'] ?? operation['op'] ?? ''}'.trim().toLowerCase();
      if (type.isNotEmpty &&
          !{'resize', 'scale', 'thumbnail', 'fit', 'encode', 'convert'}
              .contains(type)) {
        continue;
      }
      apply(
        operation['width'] ?? operation['max_width'],
        operation['height'] ?? operation['max_height'],
        operation['max_dimension'] ?? operation['max_size'],
      );
    }
  }

  apply(
    args['width'] ?? args['max_width'],
    args['height'] ?? args['max_height'],
    args['max_dimension'],
  );

  final defaultDimension =
      _positiveImageTransformDimension(args['max_dimension']) ??
          _defaultImageTransformMaxDimension;
  maxWidth ??= defaultDimension;
  maxHeight ??= defaultDimension;
  return _ImageTransformDimensions(maxWidth: maxWidth, maxHeight: maxHeight);
}

Map<String, dynamic> _imageToolTransformArguments(
  Map<String, dynamic> args, {
  required String toolName,
}) {
  final normalized = Map<String, dynamic>.from(args);
  if (toolName == 'image_convert' &&
      _stringOrNull(normalized['format']) == null) {
    final inferred = _imageFormatFromPath(
      _stringOrNull(normalized['output_path']),
    );
    if (inferred != null) normalized['format'] = inferred;
  }
  return normalized;
}

String? _imageFormatFromPath(String? path) {
  if (path == null) return null;
  final lower = path.trim().toLowerCase();
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'jpeg';
  if (lower.endsWith('.png')) return 'png';
  return null;
}

List<String> _imageTransformOperationsApplied(
  Map<String, dynamic> args, {
  required String format,
  required _ImageTransformDimensions dimensions,
}) {
  final operations = <String>[];
  final raw = args['operations'];
  if (raw is List) {
    for (final operation in raw) {
      if (operation is! Map) continue;
      final type =
          '${operation['type'] ?? operation['op'] ?? ''}'.trim().toLowerCase();
      if (type.isNotEmpty && !operations.contains(type)) {
        operations.add(type);
      }
    }
  }
  if (dimensions.maxWidth != null || dimensions.maxHeight != null) {
    final label = [
      'resize_fit',
      if (dimensions.maxWidth != null) 'w${dimensions.maxWidth}',
      if (dimensions.maxHeight != null) 'h${dimensions.maxHeight}',
    ].join(':');
    if (!operations.contains(label)) operations.add(label);
  }
  final encode = 'encode:$format';
  if (!operations.contains(encode)) operations.add(encode);
  return operations;
}

String _mimeToImageFormat(String mimeType, String fallback) {
  final mime = mimeType.trim().toLowerCase();
  if (mime == 'image/jpeg') return 'jpeg';
  if (mime == 'image/png') return 'png';
  return fallback;
}

int _boundedDocParseMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardDocParseMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardDocParseMaxBytes, parsed));
  }
  return _defaultDocParseMaxBytes;
}

int _boundedDocParseMaxChars(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardDocParseMaxChars, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardDocParseMaxChars, parsed));
  }
  return _defaultDocParseMaxChars;
}

int _boundedPdfParseMaxBytes(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardPdfParseMaxBytes, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardPdfParseMaxBytes, parsed));
  }
  return _defaultPdfParseMaxBytes;
}

int _boundedPdfParseMaxChars(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardPdfParseMaxChars, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardPdfParseMaxChars, parsed));
  }
  return _defaultPdfParseMaxChars;
}

int _boundedSourceExtractMaxChars(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardSourceExtractMaxChars, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardSourceExtractMaxChars, parsed));
  }
  return _defaultSourceExtractMaxChars;
}

int _boundedTtsFallbackDurationMs(Object? value) {
  if (value is num) {
    return math.max(1, math.min(_hardTtsFallbackDurationMs, value.toInt()));
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(1, math.min(_hardTtsFallbackDurationMs, parsed));
  }
  return _defaultTtsFallbackDurationMs;
}

int _boundedTtsFallbackSampleRate(Object? value) {
  if (value is num) {
    return math.max(
      _minTtsFallbackSampleRate,
      math.min(_hardTtsFallbackSampleRate, value.toInt()),
    );
  }
  final parsed = int.tryParse('${value ?? ''}'.trim());
  if (parsed != null) {
    return math.max(
      _minTtsFallbackSampleRate,
      math.min(_hardTtsFallbackSampleRate, parsed),
    );
  }
  return _defaultTtsFallbackSampleRate;
}

Uint8List _silentWavBytes({
  required int durationMs,
  required int sampleRate,
}) {
  const channels = 1;
  const bitsPerSample = 16;
  final samples = math.max(1, (sampleRate * durationMs / 1000).round());
  final dataBytes = samples * channels * (bitsPerSample ~/ 8);
  final bytes = Uint8List(44 + dataBytes);
  final data = ByteData.sublistView(bytes);
  _writeAscii(bytes, 0, 'RIFF');
  data.setUint32(4, 36 + dataBytes, Endian.little);
  _writeAscii(bytes, 8, 'WAVE');
  _writeAscii(bytes, 12, 'fmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, channels, Endian.little);
  data.setUint32(24, sampleRate, Endian.little);
  data.setUint32(
      28, sampleRate * channels * (bitsPerSample ~/ 8), Endian.little);
  data.setUint16(32, channels * (bitsPerSample ~/ 8), Endian.little);
  data.setUint16(34, bitsPerSample, Endian.little);
  _writeAscii(bytes, 36, 'data');
  data.setUint32(40, dataBytes, Endian.little);
  return bytes;
}

void _writeAscii(Uint8List bytes, int offset, String value) {
  for (var index = 0; index < value.length; index += 1) {
    bytes[offset + index] = value.codeUnitAt(index);
  }
}

bool _looksLikeHttpUrl(String value) {
  final text = value.trim().toLowerCase();
  return text.startsWith('http://') || text.startsWith('https://');
}

String? _sourceArgumentAsInlineText(Object? value) {
  final text = _stringOrNull(value);
  if (text == null || _looksLikeHttpUrl(text)) return null;
  if (text.contains('\n') ||
      text.contains('\t') ||
      text.contains('<') ||
      text.split(RegExp(r'\s+')).length >= 8) {
    return text;
  }
  return null;
}

String? _extractHtmlTitle(String html) {
  final match =
      RegExp(r'<title[^>]*>(.*?)</title>', caseSensitive: false, dotAll: true)
          .firstMatch(html);
  final raw = match?.group(1);
  if (raw == null) return null;
  final title = _normalizeSourceText(_stripHtmlToText(raw));
  return title.isEmpty ? null : title;
}

String _normalizeSourceText(String text) {
  return text
      .replaceAll('\r\n', '\n')
      .replaceAll('\r', '\n')
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\s*\n\s*'), '\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}

List<String> _splitSourceRankTerms(String query) {
  return query
      .split(RegExp(r'\W+'))
      .map((term) => term.trim().toLowerCase())
      .where((term) => term.isNotEmpty)
      .toList();
}

String _sourceRankText(Object? source) {
  if (source is Map) {
    for (final key in const [
      'content',
      'text',
      'snippet',
      'summary',
      'title'
    ]) {
      final value = _stringOrNull(source[key]);
      if (value != null) return value;
    }
    return jsonEncode(source);
  }
  return '$source';
}

Object _sourceRankSourceObject(Object? source) {
  if (source is Map<String, dynamic>) return source;
  if (source is Map) {
    return source.map((key, value) => MapEntry('$key', value));
  }
  return {'content': '$source'};
}

String _decodePdfBytesForScan(Uint8List bytes) {
  return latin1.decode(bytes, allowInvalid: true);
}

_PdfTextExtraction _extractBestEffortPdfText(String raw) {
  final literalStrings = _extractPdfLiteralStrings(raw);
  final hexStrings = _extractPdfHexStrings(raw);
  final candidates = <String>[
    ...literalStrings,
    ...hexStrings,
  ].map(_cleanPdfExtractedText).where((text) => text.isNotEmpty).toList();
  if (candidates.isNotEmpty) {
    return _PdfTextExtraction(
      _dedupeAdjacentLines(candidates).join('\n').trim(),
      'literal_and_hex_strings',
    );
  }
  final fallback = _printablePdfScan(raw);
  return _PdfTextExtraction(fallback, 'latin1_printable_scan');
}

List<String> _extractPdfLiteralStrings(String raw) {
  final strings = <String>[];
  var index = 0;
  while (index < raw.length && strings.length < 5000) {
    if (raw.codeUnitAt(index) != 0x28) {
      index += 1;
      continue;
    }
    final buffer = StringBuffer();
    var depth = 1;
    var cursor = index + 1;
    var escaped = false;
    while (cursor < raw.length && depth > 0) {
      final code = raw.codeUnitAt(cursor);
      final char = raw[cursor];
      if (escaped) {
        if (char == 'n') {
          buffer.write('\n');
        } else if (char == 'r') {
          buffer.write('\r');
        } else if (char == 't') {
          buffer.write('\t');
        } else if (char == 'b') {
          buffer.write('\b');
        } else if (char == 'f') {
          buffer.write('\f');
        } else if (_isOctalDigit(code)) {
          var octal = char;
          var lookahead = cursor + 1;
          while (lookahead < raw.length &&
              octal.length < 3 &&
              _isOctalDigit(raw.codeUnitAt(lookahead))) {
            octal += raw[lookahead];
            lookahead += 1;
          }
          buffer.writeCharCode(
            int.parse(octal, radix: 8).clamp(0, 255).toInt(),
          );
          cursor = lookahead - 1;
        } else {
          buffer.write(char);
        }
        escaped = false;
      } else if (code == 0x5c) {
        escaped = true;
      } else if (code == 0x28) {
        depth += 1;
        buffer.write(char);
      } else if (code == 0x29) {
        depth -= 1;
        if (depth > 0) buffer.write(char);
      } else {
        buffer.write(char);
      }
      cursor += 1;
      if (buffer.length > 20000) break;
    }
    if (depth == 0) {
      final value = buffer.toString();
      if (_looksLikeHumanText(value)) strings.add(value);
      index = cursor;
    } else {
      index += 1;
    }
  }
  return strings;
}

List<String> _extractPdfHexStrings(String raw) {
  final output = <String>[];
  final pattern = RegExp(r'<([0-9A-Fa-f\s]{4,})>');
  for (final match in pattern.allMatches(raw).take(1000)) {
    final start = match.start;
    final end = match.end;
    if ((start > 0 && raw[start - 1] == '<') ||
        (end < raw.length && raw[end] == '>')) {
      continue;
    }
    final hex = match.group(1)?.replaceAll(RegExp(r'\s+'), '') ?? '';
    if (hex.length < 4 || hex.length.isOdd) continue;
    final bytes = <int>[];
    for (var index = 0; index + 1 < hex.length; index += 2) {
      bytes.add(int.parse(hex.substring(index, index + 2), radix: 16));
    }
    final decoded = _decodePdfHexBytes(Uint8List.fromList(bytes));
    if (_looksLikeHumanText(decoded)) output.add(decoded);
  }
  return output;
}

String _decodePdfHexBytes(Uint8List bytes) {
  if (bytes.length >= 2 && bytes[0] == 0xfe && bytes[1] == 0xff) {
    return _decodeUtf16(bytes.sublist(2), littleEndian: false);
  }
  if (bytes.length >= 2 && bytes[0] == 0xff && bytes[1] == 0xfe) {
    return _decodeUtf16(bytes.sublist(2), littleEndian: true);
  }
  final hasUtf16Nulls = bytes.length >= 4 &&
      bytes.length.isEven &&
      Iterable<int>.generate(math.min(bytes.length ~/ 2, 20))
              .where((index) => bytes[index * 2] == 0)
              .length >=
          2;
  if (hasUtf16Nulls) {
    return _decodeUtf16(bytes, littleEndian: false);
  }
  return utf8.decode(bytes, allowMalformed: true);
}

String _printablePdfScan(String raw) {
  final chunks = RegExp(r'[\x09\x0A\x0D\x20-\x7E]{4,}')
      .allMatches(raw)
      .map((match) => match.group(0) ?? '')
      .map(_cleanPdfExtractedText)
      .where((text) => text.length >= 4 && !_isPdfSyntaxNoise(text))
      .take(2000)
      .toList();
  return _dedupeAdjacentLines(chunks).join('\n').trim();
}

String _cleanPdfExtractedText(String value) {
  return value
      .replaceAll('\u0000', '')
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\s*\n\s*'), '\n')
      .trim();
}

List<String> _dedupeAdjacentLines(List<String> values) {
  final output = <String>[];
  for (final value in values) {
    final text = value.trim();
    if (text.isEmpty) continue;
    if (output.isNotEmpty && output.last == text) continue;
    output.add(text);
  }
  return output;
}

bool _looksLikeHumanText(String value) {
  final text = value.trim();
  if (text.length < 2) return false;
  final printable = text.codeUnits.where((code) {
    return code == 0x09 || code == 0x0a || code == 0x0d || code >= 0x20;
  }).length;
  return printable / math.max(1, text.length) > 0.8 && !_isPdfSyntaxNoise(text);
}

bool _isPdfSyntaxNoise(String value) {
  final text = value.trim();
  if (text.isEmpty) return true;
  if (RegExp(r'^(obj|endobj|stream|endstream|xref|trailer|startxref)$')
      .hasMatch(text)) {
    return true;
  }
  if (RegExp(r'^/?[A-Za-z0-9]+\s+\d+(\.\d+)?$').hasMatch(text)) return true;
  if (RegExp(r'^[<>{}\[\]/\d\s\.\-]+$').hasMatch(text)) return true;
  return false;
}

bool _isOctalDigit(int code) => code >= 0x30 && code <= 0x37;

_DocumentPayload? _extractDocumentPayload(Map<String, dynamic> args) {
  return _documentPayloadFromMap(args, source: 'arguments');
}

_DocumentPayload? _documentPayloadFromMap(
  Map<dynamic, dynamic> value, {
  required String source,
  int depth = 0,
}) {
  if (depth > 4) return null;
  final name = _stringOrNull(
    value['name'] ?? value['filename'] ?? value['file_name'] ?? value['path'],
  );
  final mimeType = _stringOrNull(
    value['mime_type'] ?? value['mimeType'] ?? value['content_type'],
  );
  final format = _stringOrNull(value['format'] ?? value['extension']);

  for (final key in const [
    'base64',
    'pdf_base64',
    'document_base64',
    'data_base64',
    'file_base64',
  ]) {
    final encoded = _stringOrNull(value[key]);
    if (encoded != null) {
      return _documentPayloadFromEncoded(
        encoded,
        name: name,
        mimeType: mimeType,
        format: format,
        source: '$source.$key',
      );
    }
  }

  final dataUrl = _stringOrNull(value['data_url']);
  if (dataUrl != null) {
    return _documentPayloadFromEncoded(
      dataUrl,
      name: name,
      mimeType: mimeType,
      format: format,
      source: '$source.data_url',
    );
  }

  for (final key in const ['file', 'document', 'doc', 'result', 'output']) {
    final nested = value[key];
    if (nested is Map) {
      final found = _documentPayloadFromMap(
        nested,
        source: '$source.$key',
        depth: depth + 1,
      );
      if (found != null) {
        return found.withFallbacks(
          name: name,
          mimeType: mimeType,
          format: format,
        );
      }
    }
  }

  for (final key in const ['text', 'content', 'markdown', 'html']) {
    final text = _stringOrNull(value[key]);
    if (text == null) continue;
    final encoding = '${value['encoding'] ?? ''}'.trim().toLowerCase();
    if (encoding == 'base64' || text.startsWith('data:')) {
      return _documentPayloadFromEncoded(
        text,
        name: name,
        mimeType: mimeType,
        format: format ?? (key == 'html' ? 'html' : null),
        source: '$source.$key',
      );
    }
    return _DocumentPayload(
      text: text,
      name: name,
      mimeType: mimeType,
      format: format ?? (key == 'html' ? 'html' : null),
      source: '$source.$key',
    );
  }

  return null;
}

_DocumentPayload _documentPayloadFromEncoded(
  String raw, {
  required String? name,
  required String? mimeType,
  required String? format,
  required String source,
}) {
  final text = raw.trim();
  if (text.startsWith('data:')) {
    final comma = text.indexOf(',');
    if (comma <= 5) {
      throw const FormatException('Invalid data URL');
    }
    final meta = text.substring(5, comma);
    final data = text.substring(comma + 1);
    final parts = meta.split(';').where((part) => part.isNotEmpty).toList();
    final dataMime = parts.isNotEmpty && !parts.first.contains('=')
        ? parts.first.trim()
        : null;
    final isBase64 = parts.any((part) => part.toLowerCase() == 'base64');
    if (!isBase64) {
      return _DocumentPayload(
        text: Uri.decodeComponent(data),
        name: name,
        mimeType: mimeType ?? dataMime,
        format: format,
        source: source,
      );
    }
    return _DocumentPayload(
      bytes: base64Decode(_normalizeBase64ForDecode(data)),
      name: name,
      mimeType: mimeType ?? dataMime,
      format: format,
      source: source,
    );
  }
  return _DocumentPayload(
    bytes: base64Decode(_normalizeBase64ForDecode(text)),
    name: name,
    mimeType: mimeType,
    format: format,
    source: source,
  );
}

String _normalizeBase64ForDecode(String value) {
  var text = value
      .replaceAll(RegExp(r'\s+'), '')
      .replaceAll('-', '+')
      .replaceAll('_', '/');
  final padding = text.length % 4;
  if (padding != 0) text = text.padRight(text.length + (4 - padding), '=');
  return text;
}

String _normalizeDocumentFormat(
  Object? value, {
  required String mimeType,
  required String name,
}) {
  final explicit = _stringOrNull(value);
  if (explicit != null) return _canonicalDocumentFormat(explicit);
  final mime = mimeType.trim().toLowerCase();
  if (mime.startsWith('text/')) {
    final subtype = mime.substring('text/'.length).split(';').first;
    return _canonicalDocumentFormat(subtype.isEmpty ? 'txt' : subtype);
  }
  const mimeFormats = {
    'application/json': 'json',
    'application/ld+json': 'json',
    'application/xml': 'xml',
    'application/xhtml+xml': 'html',
    'application/javascript': 'javascript',
    'application/x-javascript': 'javascript',
    'application/x-yaml': 'yaml',
    'application/yaml': 'yaml',
    'text/yaml': 'yaml',
    'text/x-yaml': 'yaml',
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        'docx',
  };
  if (mimeFormats.containsKey(mime)) return mimeFormats[mime]!;
  final filename = name.trim();
  final dot = filename.lastIndexOf('.');
  if (dot >= 0 && dot + 1 < filename.length) {
    return _canonicalDocumentFormat(filename.substring(dot + 1));
  }
  return '';
}

String _canonicalDocumentFormat(String value) {
  final format = value.trim().toLowerCase().replaceFirst(RegExp(r'^\.'), '');
  return switch (format) {
    'text' => 'txt',
    'mdown' => 'markdown',
    'md' => 'markdown',
    'htm' => 'html',
    'xhtml' => 'html',
    'yml' => 'yaml',
    'js' => 'javascript',
    _ => format,
  };
}

String? _unsupportedPhoneDocumentReason({
  required String format,
  required String? mimeType,
  required String? name,
  required bool explicitText,
}) {
  if (explicitText) return null;
  final mime = (mimeType ?? '').trim().toLowerCase();
  if (format.isEmpty &&
      (mime.isEmpty ||
          mime == 'application/octet-stream' ||
          mime == 'binary/octet-stream')) {
    return null;
  }
  if (_phoneTextDocumentFormats.contains(format)) return null;
  if (mime.startsWith('text/')) return null;
  if (mime.contains('json') ||
      mime.contains('xml') ||
      mime.contains('yaml') ||
      mime.contains('csv') ||
      mime.contains('javascript')) {
    return null;
  }
  final label = [
    if (format.isNotEmpty) format,
    if (mime.isNotEmpty) mime,
    if ((name ?? '').trim().isNotEmpty) name,
  ].join(' / ');
  return 'Phone-local media_doc_parse supports UTF text documents only. $label requires PC/provider parsing.';
}

_DecodedDocumentText _decodeDocumentBytes(Uint8List bytes, int maxBytes) {
  if (bytes.length > maxBytes) {
    throw const _UnsupportedDocumentEncoding(
      'Document content is larger than max_bytes.',
    );
  }
  if (bytes.isEmpty) return const _DecodedDocumentText('', 'utf-8');
  if (bytes.length >= 2 && bytes[0] == 0xff && bytes[1] == 0xfe) {
    return _DecodedDocumentText(
        _decodeUtf16(bytes.sublist(2), littleEndian: true), 'utf-16le');
  }
  if (bytes.length >= 2 && bytes[0] == 0xfe && bytes[1] == 0xff) {
    return _DecodedDocumentText(
        _decodeUtf16(bytes.sublist(2), littleEndian: false), 'utf-16be');
  }
  if (bytes.length >= 3 &&
      bytes[0] == 0xef &&
      bytes[1] == 0xbb &&
      bytes[2] == 0xbf) {
    return _DecodedDocumentText(
        utf8.decode(bytes.sublist(3), allowMalformed: true), 'utf-8-bom');
  }
  if (_looksBinaryDocumentBytes(bytes)) {
    throw const _UnsupportedDocumentEncoding(
      'Document bytes look binary, not UTF text.',
    );
  }
  try {
    return _DecodedDocumentText(utf8.decode(bytes), 'utf-8');
  } on FormatException {
    return _DecodedDocumentText(
        utf8.decode(bytes, allowMalformed: true), 'utf-8-lossy');
  }
}

String _decodeUtf16(Uint8List bytes, {required bool littleEndian}) {
  final codes = <int>[];
  for (var index = 0; index + 1 < bytes.length; index += 2) {
    final code = littleEndian
        ? bytes[index] | (bytes[index + 1] << 8)
        : (bytes[index] << 8) | bytes[index + 1];
    codes.add(code);
  }
  return String.fromCharCodes(codes);
}

bool _looksBinaryDocumentBytes(Uint8List bytes) {
  final scanLength = math.min(bytes.length, 4096);
  if (scanLength == 0) return false;
  var suspicious = 0;
  for (var index = 0; index < scanLength; index += 1) {
    final byte = bytes[index];
    final allowedControl =
        byte == 0x09 || byte == 0x0a || byte == 0x0d || byte == 0x1b;
    if (byte == 0 || (byte < 0x08 && !allowedControl)) suspicious += 1;
  }
  return suspicious > math.max(4, scanLength ~/ 20);
}

String _parsePhoneDocumentText(
  String text, {
  required String format,
  required bool stripHtml,
}) {
  var output = text.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
  if (stripHtml && format == 'html') {
    output = _stripHtmlToText(output);
  }
  return output.trim();
}

String _stripHtmlToText(String html) {
  var text = html
      .replaceAll(
          RegExp(r'<script\b[^>]*>.*?</script>',
              caseSensitive: false, dotAll: true),
          ' ')
      .replaceAll(
          RegExp(r'<style\b[^>]*>.*?</style>',
              caseSensitive: false, dotAll: true),
          ' ')
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(RegExp(r'</p\s*>', caseSensitive: false), '\n')
      .replaceAll(RegExp(r'<[^>]+>'), ' ');
  const entities = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&nbsp;': ' ',
  };
  for (final entry in entities.entries) {
    text = text.replaceAll(entry.key, entry.value);
  }
  return text
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n');
}

String? _stringOrNull(Object? value) {
  if (value == null) return null;
  final text = '$value'.trim();
  if (text.isEmpty || text == 'null') return null;
  return text;
}

String? _extractImageBase64(Object? value, [int depth = 0]) {
  if (depth > 4 || value == null) return null;
  if (value is String) {
    final text = value.trim();
    if (text.isEmpty) return null;
    if (text.startsWith('data:image/') || _looksLikeBase64(text)) return text;
    try {
      final decoded = jsonDecode(text);
      return _extractImageBase64(decoded, depth + 1);
    } catch (_) {
      return null;
    }
  }
  if (value is Map) {
    for (final key in const [
      'base64',
      'image_base64',
      'data_base64',
      'data_url',
      'content',
      'data',
    ]) {
      final found = _extractImageBase64(value[key], depth + 1);
      if (found != null) return found;
    }
    for (final key in const ['image', 'file', 'result', 'output']) {
      final found = _extractImageBase64(value[key], depth + 1);
      if (found != null) return found;
    }
  }
  return null;
}

String _stripDataUrlPrefix(String value) {
  final text = value.trim();
  final comma = text.indexOf(',');
  if (text.startsWith('data:image/') && comma >= 0) {
    return text.substring(comma + 1).trim();
  }
  return text;
}

bool _looksLikeBase64(String value) {
  final text = _stripDataUrlPrefix(value).replaceAll(RegExp(r'\s+'), '');
  if (text.length < 16) return false;
  return RegExp(r'^[A-Za-z0-9+/=_-]+$').hasMatch(text);
}

_MobileImageMetadata? _readImageHeader(Uint8List bytes) {
  if (_isPng(bytes)) {
    return _MobileImageMetadata(
      width: _readUint32Be(bytes, 16),
      height: _readUint32Be(bytes, 20),
      format: 'png',
      mimeType: 'image/png',
    );
  }
  if (_isGif(bytes)) {
    return _MobileImageMetadata(
      width: _readUint16Le(bytes, 6),
      height: _readUint16Le(bytes, 8),
      format: 'gif',
      mimeType: 'image/gif',
    );
  }
  if (_isBmp(bytes)) {
    return _MobileImageMetadata(
      width: _readInt32Le(bytes, 18).abs(),
      height: _readInt32Le(bytes, 22).abs(),
      format: 'bmp',
      mimeType: 'image/bmp',
    );
  }
  final jpeg = _readJpegHeader(bytes);
  if (jpeg != null) return jpeg;
  final webp = _readWebpHeader(bytes);
  if (webp != null) return webp;
  return null;
}

bool _isPng(Uint8List bytes) =>
    bytes.length >= 24 &&
    bytes[0] == 0x89 &&
    bytes[1] == 0x50 &&
    bytes[2] == 0x4e &&
    bytes[3] == 0x47 &&
    bytes[4] == 0x0d &&
    bytes[5] == 0x0a &&
    bytes[6] == 0x1a &&
    bytes[7] == 0x0a;

bool _isGif(Uint8List bytes) =>
    bytes.length >= 10 &&
    bytes[0] == 0x47 &&
    bytes[1] == 0x49 &&
    bytes[2] == 0x46 &&
    bytes[3] == 0x38;

bool _isBmp(Uint8List bytes) =>
    bytes.length >= 26 && bytes[0] == 0x42 && bytes[1] == 0x4d;

_MobileImageMetadata? _readJpegHeader(Uint8List bytes) {
  if (bytes.length < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) return null;
  var offset = 2;
  while (offset + 4 < bytes.length) {
    while (offset < bytes.length && bytes[offset] == 0xff) {
      offset += 1;
    }
    if (offset >= bytes.length) return null;
    final marker = bytes[offset];
    offset += 1;
    if (marker == 0xd9 || marker == 0xda) return null;
    if (offset + 2 > bytes.length) return null;
    final length = _readUint16Be(bytes, offset);
    if (length < 2 || offset + length > bytes.length) return null;
    if (_jpegSofMarkers.contains(marker)) {
      if (offset + 7 > bytes.length) return null;
      return _MobileImageMetadata(
        width: _readUint16Be(bytes, offset + 5),
        height: _readUint16Be(bytes, offset + 3),
        format: 'jpeg',
        mimeType: 'image/jpeg',
      );
    }
    offset += length;
  }
  return null;
}

const _jpegSofMarkers = <int>{
  0xc0,
  0xc1,
  0xc2,
  0xc3,
  0xc5,
  0xc6,
  0xc7,
  0xc9,
  0xca,
  0xcb,
  0xcd,
  0xce,
  0xcf,
};

_MobileImageMetadata? _readWebpHeader(Uint8List bytes) {
  if (bytes.length < 30 ||
      !_asciiAt(bytes, 0, 'RIFF') ||
      !_asciiAt(bytes, 8, 'WEBP')) {
    return null;
  }
  if (_asciiAt(bytes, 12, 'VP8X')) {
    return _MobileImageMetadata(
      width: 1 + _readUint24Le(bytes, 24),
      height: 1 + _readUint24Le(bytes, 27),
      format: 'webp',
      mimeType: 'image/webp',
    );
  }
  if (_asciiAt(bytes, 12, 'VP8 ') && bytes.length >= 30) {
    return _MobileImageMetadata(
      width: _readUint16Le(bytes, 26) & 0x3fff,
      height: _readUint16Le(bytes, 28) & 0x3fff,
      format: 'webp',
      mimeType: 'image/webp',
    );
  }
  if (_asciiAt(bytes, 12, 'VP8L') && bytes.length >= 25 && bytes[20] == 0x2f) {
    final b1 = bytes[21];
    final b2 = bytes[22];
    final b3 = bytes[23];
    final b4 = bytes[24];
    return _MobileImageMetadata(
      width: 1 + (((b2 & 0x3f) << 8) | b1),
      height: 1 + (((b4 & 0x0f) << 10) | (b3 << 2) | ((b2 & 0xc0) >> 6)),
      format: 'webp',
      mimeType: 'image/webp',
    );
  }
  return null;
}

bool _asciiAt(Uint8List bytes, int offset, String text) {
  if (offset < 0 || offset + text.length > bytes.length) return false;
  for (var i = 0; i < text.length; i += 1) {
    if (bytes[offset + i] != text.codeUnitAt(i)) return false;
  }
  return true;
}

int _readUint16Be(Uint8List bytes, int offset) =>
    (bytes[offset] << 8) | bytes[offset + 1];

int _readUint16Le(Uint8List bytes, int offset) =>
    bytes[offset] | (bytes[offset + 1] << 8);

int _readUint24Le(Uint8List bytes, int offset) =>
    bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16);

int _readUint32Be(Uint8List bytes, int offset) =>
    (bytes[offset] << 24) |
    (bytes[offset + 1] << 16) |
    (bytes[offset + 2] << 8) |
    bytes[offset + 3];

int _readInt32Le(Uint8List bytes, int offset) {
  final value = bytes[offset] |
      (bytes[offset + 1] << 8) |
      (bytes[offset + 2] << 16) |
      (bytes[offset + 3] << 24);
  return value >= 0x80000000 ? value - 0x100000000 : value;
}

class _MobileImageMetadata {
  const _MobileImageMetadata({
    required this.width,
    required this.height,
    required this.format,
    required this.mimeType,
  });

  final int width;
  final int height;
  final String format;
  final String mimeType;
}

class _ImageTransformDimensions {
  const _ImageTransformDimensions({
    required this.maxWidth,
    required this.maxHeight,
  });

  final int? maxWidth;
  final int? maxHeight;
}

class _DocumentPayload {
  const _DocumentPayload({
    this.text,
    this.bytes,
    this.name,
    this.mimeType,
    this.format,
    required this.source,
  });

  final String? text;
  final Uint8List? bytes;
  final String? name;
  final String? mimeType;
  final String? format;
  final String source;

  int get sizeBytes => bytes?.length ?? utf8.encode(text ?? '').length;

  _DocumentPayload withFallbacks({
    required String? name,
    required String? mimeType,
    required String? format,
  }) {
    return _DocumentPayload(
      text: text,
      bytes: bytes,
      name: this.name ?? name,
      mimeType: this.mimeType ?? mimeType,
      format: this.format ?? format,
      source: source,
    );
  }
}

class _DecodedDocumentText {
  const _DecodedDocumentText(this.text, this.encoding);

  final String text;
  final String encoding;
}

class _UnsupportedDocumentEncoding implements Exception {
  const _UnsupportedDocumentEncoding(this.message);

  final String message;
}

class _PdfTextExtraction {
  const _PdfTextExtraction(this.text, this.method);

  final String text;
  final String method;
}

const _phoneTextDocumentFormats = <String>{
  '',
  'txt',
  'text',
  'markdown',
  'json',
  'jsonl',
  'csv',
  'tsv',
  'html',
  'xml',
  'yaml',
  'toml',
  'ini',
  'log',
  'javascript',
  'css',
  'svg',
};

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
