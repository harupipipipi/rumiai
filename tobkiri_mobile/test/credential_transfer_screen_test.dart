import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/credential_transfer_screen.dart';
import 'package:rumi_remote_app/src/credential_pairing_client.dart';
import 'package:rumi_remote_app/src/credential_transfer.dart';

class TestSecretStorage implements SecretStorage {
  final values = <String, String>{};
  @override
  Future<void> delete(String key) async => values.remove(key);
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

void main() {
  testWidgets('credential transfer route renders a fail-closed pairing surface',
      (tester) async {
    final storage = TestSecretStorage();
    await tester.pumpWidget(MaterialApp(
      home: CredentialTransferScreen(
        identityStore: MobileCredentialIdentityStore(storage: storage),
        deviceStore: PairedCredentialDeviceStore(storage: storage),
        vault: CredentialVault(storage: storage),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Credential transfers'), findsOneWidget);
    expect(find.text('Pair for credential transfer'), findsOneWidget);
    expect(find.text('Request pairing'), findsOneWidget);
    expect(find.textContaining('credentials.request'), findsOneWidget);
    expect(find.textContaining('device-token'), findsNothing);
  });
}
