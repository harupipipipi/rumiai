import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/qr/pairing_payload.dart';

void main() {
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
