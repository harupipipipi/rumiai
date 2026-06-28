import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/data/local/defaultspack_tool_agent_manifest.g.dart';
import 'package:rumi_remote_app/src/data/local/mobile_tool_runtime.dart';
import 'package:rumi_remote_app/src/platform/platform_services.dart';

class _FakePcToolDelegate implements MobileToolDelegate {
  MobileToolCall? lastCall;

  @override
  Future<MobileToolResult> invoke(MobileToolCall call) async {
    lastCall = call;
    return MobileToolResult(
      ok: true,
      summary: 'PC ${call.name}',
      output: jsonEncode({
        'status': 'ok',
        'data': {
          'execution_location': 'pc',
          'tool_name': call.name,
          'result': 'ran on pc',
        },
      }),
    );
  }
}

class _FakeUrlLauncher extends PlatformUrlLauncher {
  _FakeUrlLauncher(this.opened);

  final List<Uri> opened;

  @override
  Future<bool> open(Uri uri) async {
    opened.add(uri);
    return true;
  }
}

class _FakeClipboard extends PlatformClipboard {
  _FakeClipboard(this.text);

  String? text;

  @override
  Future<String?> readText() async => text;

  @override
  Future<void> writeText(String text) async {
    this.text = text;
  }
}

class _FakeMediaPicker extends PlatformMediaPicker {
  _FakeMediaPicker(this.file);

  final PlatformPickedMediaFile? file;
  bool called = false;
  String? lastKind;
  int? lastMaxBytes;

  @override
  Future<PlatformPickedMediaFile?> pick({
    required String kind,
    required int maxBytes,
  }) async {
    called = true;
    lastKind = kind;
    lastMaxBytes = maxBytes;
    return file;
  }
}

class _FakeScreenshotCapture extends PlatformScreenshotCapture {
  _FakeScreenshotCapture(this.screenshot);

  final PlatformCapturedScreenshot screenshot;
  bool called = false;
  int? lastMaxBytes;
  int? lastMaxDimension;

  @override
  Future<PlatformCapturedScreenshot> capture({
    required int maxBytes,
    required int maxDimension,
  }) async {
    called = true;
    lastMaxBytes = maxBytes;
    lastMaxDimension = maxDimension;
    return screenshot;
  }
}

class _FakeMobileToolApproval implements MobileToolApprovalDelegate {
  _FakeMobileToolApproval(this.approved);

  final bool approved;
  MobileToolApprovalRequest? lastRequest;

  @override
  Future<bool> approve(MobileToolApprovalRequest request) async {
    lastRequest = request;
    return approved;
  }
}

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
          'tool_invoke',
          'tool_consent_check',
          'tool_consent_confirm',
          'media_clipboard_read',
          'media_clipboard_write',
          'media_file_pick',
          'media_screenshot',
          'media_image_read',
          'mobile_platform_info',
          'mobile_json',
          'mobile_base64',
          'mobile_uuid',
          'browser_open_url',
          'agent_plan',
          'agent_progress',
          'agent_status',
        ]),
      );
      expect(openAiNames, isNot(contains('defaultspack.tool.todo')));
    });

    test('runs phone-local platform utility tools', () {
      final platform = runtime.execute(
        const MobileToolCall(
          id: 'platform_1',
          name: 'mobile_platform_info',
          arguments: {},
        ),
      );
      expect(platform.ok, isTrue);
      final platformPayload =
          jsonDecode(platform.output) as Map<String, dynamic>;
      final platformData = platformPayload['data'] as Map<String, dynamic>;
      expect(
          platformData['supported_platforms'], containsAll(['ios', 'android']));
      expect(platformData['runtime_layers'], contains('flutter'));

      final jsonResult = runtime.execute(
        const MobileToolCall(
          id: 'json_1',
          name: 'mobile_json',
          arguments: {'action': 'minify', 'text': '{ "a": 1 }'},
        ),
      );
      expect(jsonResult.ok, isTrue);
      expect(jsonResult.output, '{"a":1}');

      final base64Result = runtime.execute(
        const MobileToolCall(
          id: 'base64_1',
          name: 'mobile_base64',
          arguments: {'action': 'decode', 'text': 'aGVsbG8='},
        ),
      );
      expect(base64Result.ok, isTrue);
      expect(base64Result.output, 'hello');

      final uuidResult = runtime.execute(
        const MobileToolCall(
          id: 'uuid_1',
          name: 'mobile_uuid',
          arguments: {'count': 2},
        ),
      );
      expect(uuidResult.ok, isTrue);
      final uuidPayload = jsonDecode(uuidResult.output) as Map<String, dynamic>;
      final uuidData = uuidPayload['data'] as Map<String, dynamic>;
      expect(uuidData['uuids'], hasLength(2));
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

    test('runs defaultspack consent check and confirm on phone', () {
      final check = runtime.execute(
        const MobileToolCall(
          id: 'consent_check_1',
          name: 'tool_consent_check',
          arguments: {
            'text': 'この株の投資判断について教えて',
          },
        ),
      );

      expect(check.ok, isTrue);
      final checkPayload = jsonDecode(check.output) as Map<String, dynamic>;
      final checkData = checkPayload['data'] as Map<String, dynamic>;
      expect(checkData['requires_consent'], isTrue);
      expect(checkData['categories'], contains('investment'));
      final consentId = checkData['consent_id'] as String;

      final confirm = runtime.execute(
        MobileToolCall(
          id: 'consent_confirm_1',
          name: 'defaultspack.tool.consent_confirm',
          arguments: {
            'consent_id': consentId,
            'accepted': true,
          },
        ),
      );

      expect(confirm.ok, isTrue);
      final confirmPayload = jsonDecode(confirm.output) as Map<String, dynamic>;
      final confirmData = confirmPayload['data'] as Map<String, dynamic>;
      expect(confirmData['consent_id'], consentId);
      expect(confirmData['accepted'], isTrue);

      final schema = runtime.execute(
        const MobileToolCall(
          id: 'consent_schema_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'tool_consent_check'},
        ),
      );
      final schemaPayload = jsonDecode(schema.output) as Map<String, dynamic>;
      final schemaData = schemaPayload['data'] as Map<String, dynamic>;
      expect(schemaData['mobile_compatible'], isTrue);
      expect(schemaData['execution_route'], 'phone');
      expect(schemaData['callable'], isTrue);
    });

    test('runs mobile clipboard tools after explicit phone approval', () async {
      final approval = _FakeMobileToolApproval(true);
      final clipboard = _FakeClipboard('clipboard secret');
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        clipboard: clipboard,
      );

      final read = await runtime.executeAsync(
        const MobileToolCall(
          id: 'clipboard_read_1',
          name: 'media_clipboard_read',
          arguments: {'reason': 'Use pasted text in the answer'},
        ),
      );

      expect(read.ok, isTrue);
      expect(approval.lastRequest?.toolName, 'media_clipboard_read');
      final readPayload = jsonDecode(read.output) as Map<String, dynamic>;
      final readData = readPayload['data'] as Map<String, dynamic>;
      expect(readData['content'], 'clipboard secret');
      expect(readData['requires_mobile_approval'], isTrue);

      final write = await runtime.executeAsync(
        const MobileToolCall(
          id: 'clipboard_write_1',
          name: 'defaultspack.media.clipboard_write',
          arguments: {'text': 'new clipboard', 'reason': 'Copy result'},
        ),
      );

      expect(write.ok, isTrue);
      expect(approval.lastRequest?.toolName, 'media_clipboard_write');
      expect(clipboard.text, 'new clipboard');
      final writePayload = jsonDecode(write.output) as Map<String, dynamic>;
      final writeData = writePayload['data'] as Map<String, dynamic>;
      expect(writeData['written'], isTrue);
    });

    test('mobile clipboard tools fail closed without approval', () async {
      final approval = _FakeMobileToolApproval(false);
      final clipboard = _FakeClipboard('private');
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        clipboard: clipboard,
      );

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'clipboard_denied_1',
          name: 'media_clipboard_read',
          arguments: {},
        ),
      );

      expect(result.ok, isFalse);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final error = payload['error'] as Map<String, dynamic>;
      expect(error['code'], 'MOBILE_APPROVAL_REQUIRED');
    });

    test('runs phone media picker tool after explicit phone approval',
        () async {
      final approval = _FakeMobileToolApproval(true);
      final picker = _FakeMediaPicker(
        const PlatformPickedMediaFile(
          name: 'voice-note.txt',
          mimeType: 'text/plain',
          size: 5,
          base64Data: 'aGVsbG8=',
        ),
      );
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        mediaPicker: picker,
      );

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'file_pick_1',
          name: 'defaultspack_media_file_pick',
          arguments: {
            'kind': 'photo',
            'reason': 'Use selected file in the answer',
            'max_bytes': 1024,
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(approval.lastRequest?.toolName, 'media_file_pick');
      expect(picker.called, isTrue);
      expect(picker.lastKind, 'image');
      expect(picker.lastMaxBytes, 1024);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['name'], 'voice-note.txt');
      expect(data['mime_type'], 'text/plain');
      expect(data['base64'], 'aGVsbG8=');
      expect(data['runtime_layers'],
          containsAll(['flutter', 'ios-swift', 'android-kotlin']));
      expect(data['requires_mobile_approval'], isTrue);
    });

    test('phone media picker fails closed without approval', () async {
      final approval = _FakeMobileToolApproval(false);
      final picker = _FakeMediaPicker(
        const PlatformPickedMediaFile(
          name: 'ignored.txt',
          mimeType: 'text/plain',
          size: 7,
          base64Data: 'aWdub3JlZA==',
        ),
      );
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        mediaPicker: picker,
      );

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'file_pick_denied_1',
          name: 'media_file_pick',
          arguments: {'kind': 'file'},
        ),
      );

      expect(result.ok, isFalse);
      expect(picker.called, isFalse);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final error = payload['error'] as Map<String, dynamic>;
      expect(error['code'], 'MOBILE_APPROVAL_REQUIRED');
    });

    test('runs phone app screenshot tool after explicit phone approval',
        () async {
      final approval = _FakeMobileToolApproval(true);
      final capture = _FakeScreenshotCapture(
        const PlatformCapturedScreenshot(
          mimeType: 'image/png',
          size: 12,
          width: 320,
          height: 640,
          base64Data: 'iVBORw0KGgo=',
        ),
      );
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        screenshotCapture: capture,
      );

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'screenshot_1',
          name: 'defaultspack.media.screenshot',
          arguments: {
            'reason': 'Inspect the current Rumi app screen',
            'max_bytes': 2048,
            'max_dimension': 900,
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(approval.lastRequest?.toolName, 'media_screenshot');
      expect(capture.called, isTrue);
      expect(capture.lastMaxBytes, 2048);
      expect(capture.lastMaxDimension, 900);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['mime_type'], 'image/png');
      expect(data['base64'], 'iVBORw0KGgo=');
      expect(data['capture_scope'], 'app_window');
      expect(data['runtime_layers'],
          containsAll(['flutter', 'ios-swift', 'android-kotlin']));
      expect(data['requires_mobile_approval'], isTrue);
    });

    test('phone app screenshot fails closed without approval', () async {
      final approval = _FakeMobileToolApproval(false);
      final capture = _FakeScreenshotCapture(
        const PlatformCapturedScreenshot(
          mimeType: 'image/png',
          size: 8,
          width: 100,
          height: 100,
          base64Data: 'ignored',
        ),
      );
      final runtime = MobileToolRuntime(
        approvalDelegate: approval,
        screenshotCapture: capture,
      );

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'screenshot_denied_1',
          name: 'media_screenshot',
          arguments: {},
        ),
      );

      expect(result.ok, isFalse);
      expect(capture.called, isFalse);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final error = payload['error'] as Map<String, dynamic>;
      expect(error['code'], 'MOBILE_APPROVAL_REQUIRED');
    });

    test('reads phone-provided image metadata through media_image_read', () {
      final pngHeader = base64Encode([
        0x89,
        0x50,
        0x4e,
        0x47,
        0x0d,
        0x0a,
        0x1a,
        0x0a,
        0x00,
        0x00,
        0x00,
        0x0d,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x02,
        0x00,
        0x00,
        0x00,
        0x03,
      ]);

      final result = runtime.execute(
        MobileToolCall(
          id: 'image_read_1',
          name: 'defaultspack.media.image_read',
          arguments: {
            'image': {
              'base64': 'data:image/png;base64,$pngHeader',
            },
          },
        ),
      );

      expect(result.ok, isTrue);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['width'], 2);
      expect(data['height'], 3);
      expect(data['format'], 'png');
      expect(data['mime_type'], 'image/png');
      expect(data['execution_location'], 'phone');
      expect(data['requires_mobile_approval'], isFalse);
    });

    test('media_image_read does not read host paths on phone', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'image_read_path_1',
          name: 'media_image_read',
          arguments: {'path': '/tmp/image.png'},
        ),
      );

      expect(result.ok, isFalse);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final error = payload['error'] as Map<String, dynamic>;
      expect(error['code'], 'UNSUPPORTED_PATH');
    });

    test('runs mobile-compatible tools through defaultspack tool_invoke', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'invoke_1',
          name: 'tool_invoke',
          arguments: {
            'tool_name': 'tool_calculator',
            'arguments': {'expression': '8 * 8'},
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(result.summary, contains('calculator'));
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['tool_name'], 'calculator');
      expect(data['execution_location'], 'phone');
      expect(data['result'], contains('8 * 8 = 64'));
    });

    test('runs browser_open_url as a phone native URL tool', () async {
      final opened = <Uri>[];
      final runtime = MobileToolRuntime(urlLauncher: _FakeUrlLauncher(opened));

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'url_1',
          name: 'tool_invoke',
          arguments: {
            'tool_name': 'browser_open_url',
            'arguments': {'url': 'https://example.com/mobile'},
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(opened.single.host, 'example.com');
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['tool_name'], 'mobile_url_open');
      expect(data['execution_location'], 'phone');

      final schema = runtime.execute(
        const MobileToolCall(
          id: 'schema_url_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'browser_open_url'},
        ),
      );
      final schemaPayload = jsonDecode(schema.output) as Map<String, dynamic>;
      final schemaData = schemaPayload['data'] as Map<String, dynamic>;
      final mobile = schemaData['mobile'] as Map<String, dynamic>;
      expect(schemaData['mobile_compatible'], isTrue);
      expect(schemaData['tool_id'], 'mobile_url_open');
      expect(mobile['runtime_layers'],
          containsAll(['ios-swift', 'android-kotlin']));
      expect(schemaData['tags'], contains(mobileSwiftNativeTag));
      expect(schemaData['tags'], contains(mobileKotlinNativeTag));
    });

    test('tool_invoke returns specific reasons for host-bound tools', () {
      final result = runtime.execute(
        const MobileToolCall(
          id: 'invoke_host_1',
          name: 'defaultspack.tool.invoke',
          arguments: {
            'tool_name': 'python_exec',
            'arguments': {'code': 'print(1)'},
          },
        ),
      );

      expect(result.ok, isFalse);
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final error = payload['error'] as Map<String, dynamic>;
      final details = error['details'] as Map<String, dynamic>;
      expect(error['code'], 'TOOL_UNAVAILABLE_ON_PHONE');
      expect(error['message'], contains('PC側'));
      expect(details['tool_id'], 'python_exec');
      expect(details['tags'], contains('tool_registry'));
    });

    test('executeAsync delegates host-bound tool_invoke to PC when enabled',
        () async {
      final delegate = _FakePcToolDelegate();
      final runtime = MobileToolRuntime(pcDelegate: delegate);

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'invoke_pc_1',
          name: 'tool_invoke',
          arguments: {
            'tool_name': 'python_exec',
            'arguments': {'code': 'print(1)'},
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(result.output, contains('execution_location'));
      expect(delegate.lastCall?.name, 'tool_invoke');
    });

    test('executeAsync delegates direct host-bound defaultspack tool names',
        () async {
      final delegate = _FakePcToolDelegate();
      final runtime = MobileToolRuntime(pcDelegate: delegate);

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'agent_multi_1',
          name: 'agent_multi_execute',
          arguments: {'task': 'summarize the current thread'},
        ),
      );

      expect(result.ok, isTrue);
      expect(delegate.lastCall?.name, 'agent_multi_execute');
      final payload = jsonDecode(result.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['execution_location'], 'pc');
    });

    test('executeAsync keeps phone-compatible tools on phone', () async {
      final delegate = _FakePcToolDelegate();
      final runtime = MobileToolRuntime(pcDelegate: delegate);

      final result = await runtime.executeAsync(
        const MobileToolCall(
          id: 'invoke_phone_1',
          name: 'tool_invoke',
          arguments: {
            'tool_name': 'tool_calculator',
            'arguments': {'expression': '7 * 6'},
          },
        ),
      );

      expect(result.ok, isTrue);
      expect(result.output, contains('execution_location":"phone'));
      expect(delegate.lastCall, isNull);
    });

    test('schemas explain PC delegation when it is available', () {
      final runtime = MobileToolRuntime(pcDelegate: _FakePcToolDelegate());

      final schema = runtime.execute(
        const MobileToolCall(
          id: 'schema_pc_delegate_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'python_exec'},
        ),
      );

      expect(schema.ok, isTrue);
      final payload = jsonDecode(schema.output) as Map<String, dynamic>;
      final data = payload['data'] as Map<String, dynamic>;
      expect(data['mobile_compatible'], isFalse);
      expect(data['callable'], isTrue);
      expect(data['execution_route'], 'pc');
      final routing = data['automatic_routing'] as Map<String, dynamic>;
      expect(routing['one_tool_surface'], isTrue);
      expect(routing['selected_route'], 'pc');
      expect(data['pc_delegation_available'], isTrue);
      expect(data['unavailable_reason'], contains('tool_invoke'));
      final delegation = data['pc_delegation'] as Map<String, dynamic>;
      expect(delegation['available'], isTrue);
      expect(delegation['route'], '/api/mobile/v1/tools/invoke');
    });

    test('classifies mobile platform layers separately from PC-only tools', () {
      final urlSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_platform_url_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'browser_open_url'},
        ),
      );
      final urlPayload = jsonDecode(urlSchema.output) as Map<String, dynamic>;
      final urlData = urlPayload['data'] as Map<String, dynamic>;
      expect(urlData['mobile_compatible'], isTrue);
      expect(urlData['execution_platforms'], containsAll(['ios', 'android']));
      expect(urlData['mobile_runtime_layers'], contains('flutter'));
      expect(urlData['mobile_runtime_layers'], contains('ios-swift'));

      final clipboardSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_clipboard_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'media_clipboard_read'},
        ),
      );
      final clipboardPayload =
          jsonDecode(clipboardSchema.output) as Map<String, dynamic>;
      final clipboardData = clipboardPayload['data'] as Map<String, dynamic>;
      final clipboardMobile = clipboardData['mobile'] as Map<String, dynamic>;
      expect(clipboardData['mobile_compatible'], isTrue);
      expect(clipboardData['execution_route'], 'phone');
      expect(clipboardMobile['implementation_status'], 'implemented');
      expect(clipboardMobile['requires_mobile_approval'], isTrue);
      expect(clipboardMobile['platforms'], containsAll(['ios', 'android']));
      expect(clipboardData['callable'], isTrue);

      final pickerSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_file_pick_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'media_file_pick'},
        ),
      );
      final pickerPayload =
          jsonDecode(pickerSchema.output) as Map<String, dynamic>;
      final pickerData = pickerPayload['data'] as Map<String, dynamic>;
      final pickerMobile = pickerData['mobile'] as Map<String, dynamic>;
      expect(pickerData['mobile_compatible'], isTrue);
      expect(pickerData['execution_route'], 'phone');
      expect(pickerMobile['runtime_layers'],
          containsAll(['flutter', 'ios-swift', 'android-kotlin']));
      expect(pickerData['tags'], contains(mobileSwiftNativeTag));
      expect(pickerData['tags'], contains(mobileKotlinNativeTag));

      final screenshotSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_screenshot_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'media_screenshot'},
        ),
      );
      final screenshotPayload =
          jsonDecode(screenshotSchema.output) as Map<String, dynamic>;
      final screenshotData = screenshotPayload['data'] as Map<String, dynamic>;
      final screenshotMobile = screenshotData['mobile'] as Map<String, dynamic>;
      expect(screenshotData['mobile_compatible'], isTrue);
      expect(screenshotData['execution_route'], 'phone');
      expect(screenshotMobile['requires_mobile_approval'], isTrue);
      expect(screenshotMobile['runtime_layers'],
          containsAll(['flutter', 'ios-swift', 'android-kotlin']));
      expect(screenshotData['tags'], contains(mobileSwiftNativeTag));
      expect(screenshotData['tags'], contains(mobileKotlinNativeTag));

      final imageReadSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_image_read_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'media_image_read'},
        ),
      );
      final imageReadPayload =
          jsonDecode(imageReadSchema.output) as Map<String, dynamic>;
      final imageReadData = imageReadPayload['data'] as Map<String, dynamic>;
      final imageReadMobile = imageReadData['mobile'] as Map<String, dynamic>;
      expect(imageReadData['mobile_compatible'], isTrue);
      expect(imageReadData['execution_route'], 'phone');
      expect(imageReadMobile['requires_mobile_approval'], isFalse);
      expect(
          imageReadMobile['runtime_layers'], containsAll(['flutter', 'dart']));
      expect(imageReadData['tags'], contains(mobileFlutterTag));

      final computerSchema = runtime.execute(
        const MobileToolCall(
          id: 'schema_computer_1',
          name: 'tool_schema',
          arguments: {'tool_name': 'computer_click'},
        ),
      );
      final computerPayload =
          jsonDecode(computerSchema.output) as Map<String, dynamic>;
      final computerData = computerPayload['data'] as Map<String, dynamic>;
      final computerMobile = computerData['mobile'] as Map<String, dynamic>;
      expect(computerData['mobile_compatible'], isFalse);
      expect(computerMobile['implementation_status'], 'pc_only');
      expect(computerMobile['platforms'], isEmpty);
    });

    test('filters catalog by mobile platform layer', () {
      final swiftTools = runtime.execute(
        const MobileToolCall(
          id: 'list_swift_1',
          name: 'tool_list',
          arguments: {'platform': 'swift'},
        ),
      );
      final swiftPayload =
          jsonDecode(swiftTools.output) as Map<String, dynamic>;
      final swiftData = swiftPayload['data'] as Map<String, dynamic>;
      final surface = swiftData['tool_surface'] as Map<String, dynamic>;
      expect(surface['mode'], 'unified');
      expect(surface['one_tool_surface'], isTrue);
      final swiftIds = (swiftData['tools'] as List)
          .map((entry) => '${entry['function_id'] ?? entry['tool_id']}')
          .toSet();
      expect(swiftIds, contains('browser_open_url'));

      final pcTools = runtime.execute(
        const MobileToolCall(
          id: 'list_pc_1',
          name: 'tool_list',
          arguments: {'platform': 'pc', 'limit': 20},
        ),
      );
      final pcPayload = jsonDecode(pcTools.output) as Map<String, dynamic>;
      final pcData = pcPayload['data'] as Map<String, dynamic>;
      expect(pcData['platform_filter'], 'pc');
      expect(pcData['tools'], isNotEmpty);
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
      expect(runtime.knownDefaultspackToolAgentCount, greaterThan(0));
      expect(runtime.knownUnavailableDefaultspackToolCount, greaterThan(0));

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
      final openAiNames = runtime
          .openAiTools()
          .map((tool) => tool['function']['name'] as String)
          .toSet();
      expect(openAiNames, containsAll(_nativeDefaultspackToolAgentIds()));
      final agentExecuteTool = runtime.openAiTools().singleWhere(
            (tool) => tool['function']['name'] == 'agent_execute',
          );
      expect(agentExecuteTool['function']['description'],
          contains('not phone-executable'));

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

    test('generated defaultspack tool catalog matches source manifests', () {
      final source = _defaultspackToolAgentRecords();
      final generated = {
        for (final entry in defaultspackToolAgentManifestCatalog)
          entry.id: entry,
      };

      expect(generated.keys.toList()..sort(), source.keys.toList()..sort());
      for (final id in source.keys) {
        final expected = source[id]!;
        final actual = generated[id]!;
        expect(actual.description, expected.description, reason: id);
        expect(actual.tags, expected.tags, reason: id);
        expect(actual.aliases, expected.aliases, reason: id);
        expect(
          _canonicalJson(actual.inputSchema),
          _canonicalJson(expected.inputSchema),
          reason: id,
        );
      }
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

    test('classifies every defaultspack tool or agent id', () {
      final ids = _defaultspackToolAgentIds();
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
  return _defaultspackToolAgentRecords().keys.toList()..sort();
}

List<String> _nativeDefaultspackToolAgentIds() {
  return _defaultspackToolAgentRecords()
      .entries
      .where((entry) {
        final tags = entry.value.tags.toSet();
        return tags.contains('agent') ||
            (tags.contains('tool') && !tags.contains('tool_registry'));
      })
      .map((entry) => entry.key)
      .toList()
    ..sort();
}

Map<String, _ManifestRecord> _defaultspackToolAgentRecords() {
  final functionsRoot = Directory('../defaultspack/functions');
  final toolsRoot = Directory('../defaultspack/tools');
  expect(functionsRoot.existsSync(), isTrue);
  expect(toolsRoot.existsSync(), isTrue);
  final records = <String, _ManifestRecord>{};

  void putRecord(String id, _ManifestRecord record) {
    if (id.isEmpty) return;
    records[id] = records[id]?.merge(record) ?? record;
  }

  final functionManifests = functionsRoot
      .listSync(recursive: true)
      .whereType<File>()
      .where((file) => file.path.endsWith('/manifest.json'));
  for (final file in functionManifests) {
    final manifest = jsonDecode(file.readAsStringSync());
    if (manifest is! Map<String, dynamic>) continue;
    final tags =
        (manifest['tags'] as List? ?? const []).map((tag) => '$tag').toSet();
    if (!tags.contains('tool') && !tags.contains('agent')) continue;
    final functionId = '${manifest['function_id'] ?? ''}'.trim();
    if (functionId.isEmpty) continue;
    final aliases = (manifest['vocab_aliases'] as List? ?? const [])
        .map((alias) => '$alias'.trim())
        .where((alias) => alias.isNotEmpty)
        .toList()
      ..sort();
    final inputSchema = manifest['input_schema'] is Map<String, dynamic>
        ? manifest['input_schema'] as Map<String, dynamic>
        : const <String, dynamic>{
            'type': 'object',
            'additionalProperties': true,
          };
    putRecord(
      functionId,
      _ManifestRecord(
        description: '${manifest['description'] ?? ''}',
        tags: tags.toList()..sort(),
        aliases: aliases,
        inputSchema: inputSchema,
      ),
    );
  }

  final toolManifests = toolsRoot
      .listSync(recursive: true)
      .whereType<File>()
      .where((file) => file.path.endsWith('/manifest.json'));
  for (final file in toolManifests) {
    final manifest = jsonDecode(file.readAsStringSync());
    if (manifest is! Map<String, dynamic>) continue;
    final config = manifest['config'] is Map<String, dynamic>
        ? manifest['config'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final id = '${config['tool_id'] ?? manifest['id'] ?? ''}'.trim();
    if (id.isEmpty) continue;
    final tags = <String>{
      'tool_registry',
      ...(config['tags'] as List? ?? const []).map((tag) => '$tag'),
    };
    if (config['requires_approval'] == true) tags.add('requires_approval');
    final category = '${config['tool_category'] ?? ''}'.trim();
    if (category.isNotEmpty) tags.add(category);
    final schema = config['schema'] is Map<String, dynamic>
        ? config['schema'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final parameters = schema['parameters'] is Map<String, dynamic>
        ? schema['parameters'] as Map<String, dynamic>
        : const <String, dynamic>{
            'type': 'object',
            'additionalProperties': true,
          };
    putRecord(
      id,
      _ManifestRecord(
        description:
            '${config['summary'] ?? manifest['description'] ?? ''}'.trim(),
        tags: tags.toList()..sort(),
        aliases: const [],
        inputSchema: parameters,
      ),
    );
  }
  return records;
}

String _canonicalJson(Object? value) => jsonEncode(_normalizeJson(value));

Object? _normalizeJson(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((key) => '$key').toList()..sort();
    return {
      for (final key in keys) key: _normalizeJson(value[key]),
    };
  }
  if (value is List) {
    return value.map(_normalizeJson).toList();
  }
  return value;
}

class _ManifestRecord {
  const _ManifestRecord({
    required this.description,
    required this.tags,
    required this.aliases,
    required this.inputSchema,
  });

  final String description;
  final List<String> tags;
  final List<String> aliases;
  final Map<String, dynamic> inputSchema;

  _ManifestRecord merge(_ManifestRecord other) {
    return _ManifestRecord(
      description:
          other.description.isNotEmpty ? other.description : description,
      tags: {...tags, ...other.tags}.toList()..sort(),
      aliases: {...aliases, ...other.aliases}.toList()..sort(),
      inputSchema:
          other.inputSchema.isNotEmpty ? other.inputSchema : inputSchema,
    );
  }
}
