import 'dart:convert';
import 'dart:math' as math;

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
    this.unavailableReason = '',
  });

  final String name;
  final String description;
  final Map<String, dynamic> parameters;
  final List<String> tags;
  final String unavailableReason;

  bool get available => unavailableReason.trim().isEmpty;

  Map<String, dynamic> toOpenAiTool() => {
        'type': 'function',
        'function': {
          'name': name,
          'description': description,
          'parameters': parameters,
        },
      };
}

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
      unavailableReason:
          'このtoolはPC側defaultspackのresearch providerに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'reddit_search',
      description: 'Run the defaultspack reddit research tool.',
      tags: ['tool', 'research', 'reddit'],
      unavailableReason:
          'このtoolはPC側defaultspackのresearch providerに依存するため、このスマホ単体では実行できません。PC接続時にPC側runtimeで実行してください。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'file_reader',
      description: 'Read files from the host workspace.',
      tags: ['tool', 'file', 'workspace', 'host'],
      unavailableReason:
          'このtoolはPCのworkspace/file systemに依存するため、このスマホ単体では実行できません。',
      parameters: {'type': 'object', 'additionalProperties': true},
    ),
    MobileToolDefinition(
      name: 'subagent',
      description: 'Run the default delegation/subagent tool.',
      tags: ['tool', 'agent', 'host'],
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

  List<Map<String, dynamic>> openAiTools() =>
      supportedTools.map((tool) => tool.toOpenAiTool()).toList();

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
    switch (call.name) {
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
      case assistantProgressToolName:
        return _assistantProgress(call.arguments);
      default:
        return MobileToolResult(
          ok: false,
          summary: 'unsupported tool',
          output: _unsupportedReason(call.name),
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
    for (final tool in [...supportedTools, ...unavailableDefaultspackTools]) {
      final haystack = [
        tool.name,
        tool.description,
        ...tool.tags,
      ].join(' ').toLowerCase();
      if (query.isEmpty || haystack.contains(query)) {
        records.add({
          'tool_id': tool.name,
          'tags': tool.tags,
          'mobile_compatible': tool.available,
          'execution_location': tool.available ? 'phone' : 'pc',
          'unavailable_reason': tool.unavailableReason,
          'summary': tool.description,
        });
      }
      if (records.length >= limit) break;
    }
    if (records.isEmpty) {
      records.add({
        'tool_id': query,
        'mobile_compatible': false,
        'execution_location': 'unsupported',
        'unavailable_reason': _unsupportedReason(query),
      });
    }
    return MobileToolResult(
      ok: true,
      summary: '${records.length} tools',
      output: jsonEncode({
        'agent_template': {
          'template_id': mobileAgentTemplateId,
          'ai_input_id': mobileAgentAiInputId,
          'tool_policy_id': mobileAgentToolPolicyId,
        },
        'tools': records,
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
      if (normalized == tool.name || tool.tags.contains(normalized)) {
        return tool.unavailableReason;
      }
    }
    return 'このtoolはこのスマホのmobile-compatible runtimeに未登録です。PC接続時はPC側のtool catalogを確認してください。';
  }
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
