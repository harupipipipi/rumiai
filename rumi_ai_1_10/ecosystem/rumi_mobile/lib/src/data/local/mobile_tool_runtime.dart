import 'dart:convert';
import 'dart:math' as math;

import 'defaultspack_tool_agent_manifest.g.dart';

const mobileCompatibleTag = 'mobile-compatible';
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

class MobileToolDefinition {
  const MobileToolDefinition({
    required this.name,
    required this.description,
    required this.parameters,
    required this.tags,
    this.aliases = const [],
    this.unavailableReason = '',
  });

  final String name;
  final String description;
  final Map<String, dynamic> parameters;
  final List<String> tags;
  final List<String> aliases;
  final String unavailableReason;

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

class MobileToolRuntime {
  const MobileToolRuntime();

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
            'maximum': 100,
            'default': 50,
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

  List<Map<String, dynamic>> openAiTools() => [
        for (final tool in supportedTools)
          for (final name in tool.openAiNames)
            tool.toOpenAiTool(exportedName: name),
      ];

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
      case 'current_time':
        return _currentTime(call.arguments);
      case 'todo':
        return _todo(call.arguments);
      case 'tool_task_board':
      case 'task_board':
        return _taskBoard(call.arguments);
      case 'tool_search':
        return _toolSearch(call.arguments);
      case 'tool_names':
        return _toolNames(call.arguments);
      case 'tool_list':
        return _toolList(call.arguments);
      case 'tool_schema':
        return _toolSchema(call.arguments);
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

  MobileToolResult _toolSearch(Map<String, dynamic> args) {
    final query = '${args['query'] ?? ''}'.trim().toLowerCase();
    final limit = (args['limit'] is num)
        ? math.max(1, math.min(12, (args['limit'] as num).toInt()))
        : 6;
    final records = <Map<String, dynamic>>[];
    for (final record in _catalogRecords(includeUnavailable: true)) {
      final haystack = [
        record['function_id'],
        record['tool_id'],
        record['requested_name'],
        record['summary'],
        ...(record['tags'] as List? ?? const []),
        ...(record['aliases'] as List? ?? const []),
      ].join(' ').toLowerCase();
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
        'tools': records,
      }),
    );
  }

  MobileToolResult _toolNames(Map<String, dynamic> args) {
    final includeAliases = args['include_aliases'] != false;
    final includeUnavailable = args['include_unavailable'] != false;
    final names = <String>[];
    for (final record
        in _catalogRecords(includeUnavailable: includeUnavailable)) {
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
        },
      }),
    );
  }

  MobileToolResult _toolList(Map<String, dynamic> args) {
    final includeUnavailable = args['include_unavailable'] != false;
    final limit = (args['limit'] is num)
        ? math.max(1, math.min(200, (args['limit'] as num).toInt()))
        : 120;
    final allRecords = _catalogRecords(includeUnavailable: includeUnavailable);
    final records = allRecords.take(limit).toList();
    return MobileToolResult(
      ok: true,
      summary: '${records.length} tools',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'agent_template': _agentTemplateRecord(),
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
        ? _catalogEntryRecord(entry, requestedName: requested)
        : tool == null
            ? _unsupportedToolRecord(canonical)
            : _toolRecord(tool, requestedName: requested);
    return MobileToolResult(
      ok: true,
      summary: '${record['tool_id']} schema',
      output: jsonEncode({
        'status': 'ok',
        'data': record,
      }),
    );
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

bool _isOpenAiFunctionName(String name) {
  final trimmed = name.trim();
  return RegExp(r'^[a-zA-Z0-9_-]{1,64}$').hasMatch(trimmed);
}

Map<String, dynamic> _agentTemplateRecord() => {
      'template_id': mobileAgentTemplateId,
      'ai_input_id': mobileAgentAiInputId,
      'tool_policy_id': mobileAgentToolPolicyId,
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
    record['tags'] = {
      ...entry.tags,
      ...(record['tags'] as List? ?? const []),
    }.toList();
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
  record['tags'] = entry.tags;
  record['parameters'] = entry.inputSchema;
  return record;
}

Map<String, dynamic> _toolRecord(
  MobileToolDefinition tool, {
  String functionId = '',
  String requestedName = '',
}) {
  return {
    'function_id': functionId.trim().isEmpty ? tool.name : functionId.trim(),
    'tool_id': tool.name,
    if (requestedName.trim().isNotEmpty) 'requested_name': requestedName,
    'aliases': tool.aliases,
    'tags': tool.tags,
    'mobile_compatible': tool.available,
    'execution_location': tool.available ? 'phone' : 'pc',
    'unavailable_reason': tool.unavailableReason,
    'summary': tool.description,
    'parameters': tool.parameters,
  };
}

Map<String, dynamic> _unsupportedToolRecord(String name) {
  final normalized = name.trim();
  return {
    'function_id': normalized,
    'tool_id': normalized,
    'aliases': const <String>[],
    'tags': _inferredDefaultspackTags(normalized),
    'mobile_compatible': false,
    'execution_location': 'pc',
    'unavailable_reason': const MobileToolRuntime()._unsupportedReason(
      normalized,
    ),
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

final List<Map<String, dynamic>> _mobileTodos = [];
final Map<String, dynamic> _mobileTaskBoard = {
  'board_id': 'mobile-default',
  'title': 'Mobile Task Board',
  'columns': _taskBoardDefaultColumns,
};
final List<Map<String, dynamic>> _mobileTaskCards = [];
final List<Map<String, dynamic>> _mobileAgentPlans = [];
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
