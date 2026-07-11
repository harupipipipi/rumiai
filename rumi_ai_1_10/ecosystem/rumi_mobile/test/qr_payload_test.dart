import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/qr/qr_payload.dart';

void main() {
  test('parses rumi_pc connection payload', () {
    final payload = parseQrPayload(
        '{"kind":"rumi_pc","baseUrl":"http://192.168.1.10:8765","token":"abc"}');
    expect(payload, isA<QrPcConnection>());
    final pc = payload as QrPcConnection;
    expect(pc.baseUrl, 'http://192.168.1.10:8765');
    expect(pc.token, 'abc');
  });

  test('rejects legacy rumi_api payload containing a raw credential', () {
    final payload = parseQrPayload(
        '{"kind":"rumi_api","baseUrl":"https://api.openai.com/v1","api_'
        'key":"fake-test-value","model":"gpt-4o-mini","label":"main"}');
    expect(payload, isA<QrUnknown>());
  });

  test('rejects legacy provider QR payload', () {
    final payload = parseQrPayload(
      '{"kind":"rumi_api","providerId":"google","apiId":"main","baseUrl":"https://generativelanguage.googleapis.com/v1beta/openai","api'
      'Key":"fake-test-value","model":"gemini-2.5-pro","label":"Google","apiCompatibility":"openai"}',
    );
    expect(payload, isA<QrUnknown>());
  });

  test('parses plain url as QrUrl', () {
    final payload = parseQrPayload('https://rumi-mobile.pages.dev');
    expect(payload, isA<QrUrl>());
    expect((payload as QrUrl).url, 'https://rumi-mobile.pages.dev');
  });

  test('returns unknown for arbitrary text', () {
    expect(parseQrPayload('hello world'), isA<QrUnknown>());
    expect(parseQrPayload(''), isA<QrUnknown>());
  });

  test('returns unknown for malformed json', () {
    expect(parseQrPayload('{not json'), isA<QrUnknown>());
  });
}
