import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/data/local/mobile_tool_runtime.dart';

void main() {
  group('MobileToolRuntime', () {
    const runtime = MobileToolRuntime();

    setUp(() {
      runtime.execute(
        const MobileToolCall(
          id: 'reset_todos',
          name: 'todo',
          arguments: {'action': 'clear'},
        ),
      );
      runtime.execute(
        const MobileToolCall(
          id: 'reset_board',
          name: 'tool_task_board',
          arguments: {'action': 'clear'},
        ),
      );
      runtime.execute(
        const MobileToolCall(
          id: 'reset_plans',
          name: 'agent_plan',
          arguments: {'action': 'clear'},
        ),
      );
    });

    test('marks local agent tools as mobile-compatible and advertises aliases',
        () {
      final tools = runtime.availableTools;
      expect(
        tools
            .where((tool) => [
                  'todo',
                  'tool_task_board',
                  'calculator',
                  'agent_plan',
                ].contains(tool.name))
            .every((tool) => tool.tags.contains(mobileCompatibleTag)),
        isTrue,
      );
      final openAiNames = runtime
          .openAiTools()
          .map((tool) => tool['function']['name'] as String)
          .toSet();
      expect(
        openAiNames,
        containsAll([
          'todo',
          'tool_todo',
          'tool_task_board',
          'tool_calculator',
          'tool_names',
          'tool_list',
          'tool_schema',
          'agent_plan',
          'agent_progress',
          'agent_status',
        ]),
      );
      expect(openAiNames, isNot(contains('defaultspack.tool.todo')));
    });

    test('runs defaultspack todo-compatible actions on phone', () {
      final added = runtime.execute(
        const MobileToolCall(
          id: 'todo_1',
          name: 'tool_todo',
          arguments: {
            'action': 'add',
            'title': 'Write mobile agent tests',
          },
        ),
      );

      expect(added.ok, isTrue);
      expect(added.summary, contains('Write mobile agent tests'));
      final payload = jsonDecode(added.output) as Map<String, dynamic>;
      final changed = payload['changed'] as Map<String, dynamic>;

      final completed = runtime.execute(
        MobileToolCall(
          id: 'todo_2',
          name: 'todo',
          arguments: {
            'action': 'complete',
            'todo_id': changed['id'],
          },
        ),
      );

      expect(completed.ok, isTrue);
      expect(completed.output, contains('"status":"done"'));
    });

    test('runs defaultspack calculator function alias on phone', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'calc_1',
          name: 'tool_calculator',
          arguments: {'expression': '6 * 7'},
        ),
      );

      expect(result.ok, isTrue);
      expect(result.output, contains('6 * 7 = 42'));
    });

    test('runs defaultspack task_board-compatible actions on phone', () {
      final created = runtime.execute(
        const MobileToolCall(
          id: 'board_1',
          name: 'tool_task_board',
          arguments: {
            'action': 'create',
            'title': 'Implement mobile tools',
            'column': 'Doing',
          },
        ),
      );

      expect(created.ok, isTrue);
      final payload = jsonDecode(created.output) as Map<String, dynamic>;
      final changed = payload['changed'] as Map<String, dynamic>;

      final moved = runtime.execute(
        MobileToolCall(
          id: 'board_2',
          name: 'task_board',
          arguments: {
            'action': 'move',
            'card_id': changed['id'],
            'column': 'Done',
          },
        ),
      );

      expect(moved.ok, isTrue);
      expect(moved.output, contains('"column":"Done"'));
    });

    test('explains host-bound defaultspack tools through tool_search', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'search_1',
          name: 'tool_search',
          arguments: {'query': 'tool_web_search'},
        ),
      );

      expect(result.ok, isTrue);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final tools = payload['tools'] as List;
      expect(tools.single['tool_id'], 'web_search');
      expect(tools.single['aliases'], contains('tool_web_search'));
      expect(tools.single['mobile_compatible'], isFalse);
      expect(tools.single['unavailable_reason'], contains('PC側defaultspack'));
    });

    test('tool_search maps defaultspack function aliases to phone tools', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'search_2',
          name: 'tool_search',
          arguments: {'query': 'tool_todo'},
        ),
      );

      expect(result.ok, isTrue);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final tools = payload['tools'] as List;
      expect(tools.single['tool_id'], 'todo');
      expect(tools.single['aliases'], contains('tool_todo'));
      expect(tools.single['mobile_compatible'], isTrue);
    });

    test('defaultspack catalog tools list names and schemas on phone', () {
      final manifestIds = _defaultspackToolAgentIds();
      final names = runtime.execute(
        const MobileToolCall(
          id: 'names_1',
          name: 'tool_names',
          arguments: {},
        ),
      );
      expect(names.ok, isTrue);
      final namesPayload = jsonDecode(names.output) as Map<String, dynamic>;
      final nameData = namesPayload['data'] as Map<String, dynamic>;
      expect(nameData['names'], containsAll(['tool_todo', 'agent_plan']));
      expect(nameData['names'], containsAll(manifestIds));

      final list = runtime.execute(
        const MobileToolCall(
          id: 'list_1',
          name: 'tool_list',
          arguments: {},
        ),
      );
      expect(list.ok, isTrue);
      final listPayload = jsonDecode(list.output) as Map<String, dynamic>;
      final listData = listPayload['data'] as Map<String, dynamic>;
      expect(listData['truncated'], isFalse);
      final functionIds = (listData['tools'] as List)
          .map((entry) => '${entry['function_id'] ?? entry['tool_id']}')
          .toSet();
      expect(functionIds, containsAll(manifestIds));

      final schema = runtime.execute(
        const MobileToolCall(
          id: 'schema_1',
          name: 'defaultspack.tool.schema',
          arguments: {'tool_name': 'agent_execute'},
        ),
      );
      expect(schema.ok, isTrue);
      final schemaPayload = jsonDecode(schema.output) as Map<String, dynamic>;
      final data = schemaPayload['data'] as Map<String, dynamic>;
      expect(data['tool_id'], 'agent_execute');
      expect(data['mobile_compatible'], isFalse);
      expect(data['unavailable_reason'], contains('PC側'));
    });

    test('defaultspack generated manifest aliases and schemas are exposed', () {
      final aliasSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_alias_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'defaultspack.agent.execute'},
        ),
      );
      expect(aliasSchema.ok, isTrue);
      final aliasPayload =
          jsonDecode(aliasSchema.output) as Map<String, dynamic>;
      final aliasData = aliasPayload['data'] as Map<String, dynamic>;
      expect(aliasData['function_id'], 'agent_execute');
      expect(aliasData['requested_name'], 'defaultspack.agent.execute');
      expect(aliasData['aliases'], contains('defaults.agent.execute'));

      final webSearchSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_web_search_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'tool_web_search'},
        ),
      );
      expect(webSearchSchema.ok, isTrue);
      final webPayload =
          jsonDecode(webSearchSchema.output) as Map<String, dynamic>;
      final webData = webPayload['data'] as Map<String, dynamic>;
      final parameters = webData['parameters'] as Map<String, dynamic>;
      expect(parameters['required'], contains('query'));
      expect(parameters['properties'], contains('query'));
      expect(webData['aliases'], contains('defaultspack.tool.web_search'));
    });

    test('runs phone-local defaultspack agent plan and status tools', () {
      final plan = runtime.execute(
        const MobileToolCall(
          id: 'agent_plan_1',
          name: 'agent_plan',
          arguments: {
            'objective': 'スマホでtool実行を確認する',
            'steps': ['toolを選ぶ', '実行する', '結果を見る'],
          },
        ),
      );
      expect(plan.ok, isTrue);
      expect(plan.summary, contains('3 step plan'));

      final status = runtime.execute(
        const MobileToolCall(
          id: 'agent_status_1',
          name: 'defaultspack.agent.status',
          arguments: {},
        ),
      );
      expect(status.ok, isTrue);
      final payload = jsonDecode(status.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['status'], 'active');
      expect(data['plans'], isNotEmpty);
      expect(data['agent_template']['template_id'], mobileAgentTemplateId);
    });

    test('explains defaultspack function ids even when not in local catalog',
        () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'missing_1',
          name: 'coding_git_status',
          arguments: {},
        ),
      );

      expect(result.ok, isFalse);
      expect(result.output, contains('defaultspack tool'));
      expect(result.output, contains('PC側'));
    });

    test('classifies every defaultspack tool or agent function id', () {
      final functionsRoot = Directory('../defaultspack/functions');
      expect(functionsRoot.existsSync(), isTrue);
      final manifests = functionsRoot
          .listSync(recursive: true)
          .whereType<File>()
          .where((file) => file.path.endsWith('/manifest.json'));
      final ids = <String>[];
      for (final file in manifests) {
        final manifest = jsonDecode(file.readAsStringSync());
        if (manifest is! Map<String, dynamic>) continue;
        final tags = (manifest['tags'] as List? ?? const [])
            .map((tag) => '$tag')
            .toSet();
        if (!tags.contains('tool') && !tags.contains('agent')) continue;
        final functionId = '${manifest['function_id'] ?? ''}'.trim();
        if (functionId.isNotEmpty) ids.add(functionId);
      }
      expect(ids, isNotEmpty);

      for (final id in ids) {
        final result = runtime.execute(
          MobileToolCall(id: 'classify_$id', name: id, arguments: const {}),
        );
        expect(
          result.output,
          isNot(contains('mobile-compatible runtimeに未登録')),
          reason: '$id must be executable on phone or classified with a reason',
        );
      }
    });

    test('returns schema or reason for every defaultspack tool or agent id',
        () {
      final ids = _defaultspackToolAgentIds();
      expect(ids, isNotEmpty);

      for (final id in ids) {
        final result = runtime.execute(
          MobileToolCall(
            id: 'schema_$id',
            name: 'tool_schema',
            arguments: {'tool_name': id},
          ),
        );
        expect(result.ok, isTrue, reason: '$id schema should be inspectable');
        final payload = jsonDecode(result.output) as Map<String, dynamic>;
        final data = payload['data'] as Map<String, dynamic>;
        final aliases = (data['aliases'] as List? ?? const [])
            .map((alias) => '$alias')
            .toSet();
        expect(
          data['tool_id'] == id ||
              data['requested_name'] == id ||
              aliases.contains(id),
          isTrue,
          reason: '$id must resolve directly or as a mobile alias',
        );
        expect(
          '${data['unavailable_reason'] ?? ''}',
          isNot(contains('mobile-compatible runtimeに未登録')),
          reason: '$id must have a specific phone/PC execution answer',
        );
      }
    });
  });
}

List<String> _defaultspackToolAgentIds() {
  final functionsRoot = Directory('../defaultspack/functions');
  expect(functionsRoot.existsSync(), isTrue);
  final manifests = functionsRoot
      .listSync(recursive: true)
      .whereType<File>()
      .where((file) => file.path.endsWith('/manifest.json'));
  final ids = <String>[];
  for (final file in manifests) {
    final manifest = jsonDecode(file.readAsStringSync());
    if (manifest is! Map<String, dynamic>) continue;
    final tags =
        (manifest['tags'] as List? ?? const []).map((tag) => '$tag').toSet();
    if (!tags.contains('tool') && !tags.contains('agent')) continue;
    final functionId = '${manifest['function_id'] ?? ''}'.trim();
    if (functionId.isNotEmpty) ids.add(functionId);
  }
  ids.sort();
  return ids;
}
