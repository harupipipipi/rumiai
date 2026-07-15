import 'package:flutter/material.dart';

import 'credential_pairing_client.dart';
import 'credential_transfer.dart';
import 'pairing_payload.dart';

class CredentialTransferScreen extends StatefulWidget {
  const CredentialTransferScreen({
    super.key,
    this.identityStore,
    this.deviceStore,
    this.vault,
  });

  final MobileCredentialIdentityStore? identityStore;
  final PairedCredentialDeviceStore? deviceStore;
  final CredentialVault? vault;

  @override
  State<CredentialTransferScreen> createState() =>
      _CredentialTransferScreenState();
}

class _CredentialTransferScreenState extends State<CredentialTransferScreen> {
  final _pairingController = TextEditingController();
  late final MobileCredentialIdentityStore _identityStore;
  late final PairedCredentialDeviceStore _deviceStore;
  late final CredentialVault _vault;

  PairedCredentialDevice? _device;
  CredentialTransferClient? _transferSession;
  MobilePairingPayload? _activePairing;
  List<PendingCredentialTransfer> _transfers = const [];
  String? _error;
  bool _busy = true;

  @override
  void initState() {
    super.initState();
    _identityStore = widget.identityStore ?? MobileCredentialIdentityStore();
    _deviceStore = widget.deviceStore ?? PairedCredentialDeviceStore();
    _vault = widget.vault ?? CredentialVault();
    _loadDevice();
  }

  @override
  void dispose() {
    _transferSession?.close();
    _pairingController.clear();
    _pairingController.dispose();
    super.dispose();
  }

  Future<void> _loadDevice() async {
    try {
      final device = await _deviceStore.load();
      if (!mounted) return;
      setState(() {
        _device = device;
        _transferSession =
            device == null ? null : _createTransferClient(device);
        _busy = false;
      });
      if (device != null) await _refreshTransfers();
    } catch (error) {
      _fail(error);
    }
  }

  Future<void> _claimPairing() async {
    _start();
    final client = CredentialPairingClient(
      identityStore: _identityStore,
      deviceStore: _deviceStore,
    );
    try {
      final pairing = MobilePairingPayload.parse(_pairingController.text);
      await client.claim(pairing);
      if (!mounted) return;
      setState(() {
        _activePairing = pairing;
        _busy = false;
      });
      _message('Pairing request sent. Approve it on the PC.');
    } catch (error) {
      _fail(error);
    } finally {
      client.close();
    }
  }

  Future<void> _pickupPairing() async {
    final pairing = _activePairing;
    if (pairing == null) return;
    _start();
    final client = CredentialPairingClient(
      identityStore: _identityStore,
      deviceStore: _deviceStore,
    );
    try {
      final ready = await client.pickupApproved(pairing);
      if (!ready) {
        throw StateError('Pairing is still waiting for PC approval');
      }
      final device = await _deviceStore.load();
      _pairingController.clear();
      if (!mounted) return;
      setState(() {
        _device = device;
        _transferSession =
            device == null ? null : _createTransferClient(device);
        _activePairing = null;
        _busy = false;
      });
      await _refreshTransfers();
    } catch (error) {
      _fail(error);
    } finally {
      client.close();
    }
  }

  CredentialTransferClient _createTransferClient(
          PairedCredentialDevice device) =>
      CredentialTransferClient(
        baseUrl: device.baseUrl,
        deviceToken: device.deviceToken,
        identityStore: _identityStore,
        vault: _vault,
      );

  Future<void> _refreshTransfers() async {
    final device = _device;
    if (device == null) return;
    _start();
    final client = _transferSession ??= _createTransferClient(device);
    try {
      final transfers = await client.listPending();
      if (!mounted) return;
      setState(() {
        _transfers = transfers;
        _busy = false;
      });
    } catch (error) {
      _fail(error);
    }
  }

  Future<void> _redeem(PendingCredentialTransfer transfer) async {
    if (!await _confirm(
      title: 'Receive credential?',
      message: 'Receive the credential for ${transfer.providerId} / '
          '${transfer.accountId} into OS secure storage?',
      action: 'Receive',
    )) {
      return;
    }
    final device = _device;
    if (device == null) return;
    _start();
    final client = _transferSession ??= _createTransferClient(device);
    try {
      await client.redeemAndPersist(transfer);
      if (!mounted) return;
      _message('Credential stored and receipt acknowledged.');
      await _refreshTransfers();
    } catch (error) {
      _fail(error);
    }
  }

  Future<void> _reject(PendingCredentialTransfer transfer) async {
    if (!await _confirm(
      title: 'Reject transfer?',
      message:
          'The PC will be told that this credential transfer was rejected.',
      action: 'Reject',
      destructive: true,
    )) {
      return;
    }
    final device = _device;
    if (device == null) return;
    _start();
    final client = _transferSession ??= _createTransferClient(device);
    try {
      await client.reject(transfer);
      await _refreshTransfers();
    } catch (error) {
      _fail(error);
    }
  }

  Future<bool> _confirm({
    required String title,
    required String message,
    required String action,
    bool destructive = false,
  }) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: destructive
                ? FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                  )
                : null,
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(action),
          ),
        ],
      ),
    );
    return result == true;
  }

  void _start() {
    if (!mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
  }

  void _fail(Object error) {
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = error.toString().replaceFirst('Bad state: ', '');
    });
  }

  void _message(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Credential transfers'),
        actions: [
          IconButton(
            tooltip: 'Refresh transfers',
            onPressed: _busy || _device == null ? null : _refreshTransfers,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(_error!),
                ),
              ),
            if (_busy) const LinearProgressIndicator(),
            if (_device == null) ...[
              Text(
                'Pair for credential transfer',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              const Text(
                'Paste the current pairing QR payload. Only public device keys '
                'and the credentials.request scope are sent to the PC.',
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _pairingController,
                enabled: !_busy,
                minLines: 3,
                maxLines: 6,
                autocorrect: false,
                enableSuggestions: false,
                smartQuotesType: SmartQuotesType.disabled,
                decoration: const InputDecoration(
                  labelText: 'Pairing payload',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: _busy ? null : _claimPairing,
                icon: const Icon(Icons.link),
                label: const Text('Request pairing'),
              ),
              if (_activePairing != null)
                OutlinedButton.icon(
                  onPressed: _busy ? null : _pickupPairing,
                  icon: const Icon(Icons.verified_user_outlined),
                  label: const Text('Check PC approval'),
                ),
            ] else ...[
              Card(
                child: ListTile(
                  leading: const Icon(Icons.phonelink_lock),
                  title: const Text('Device-bound connection active'),
                  subtitle: Text(
                    _device!.baseUrl,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Pending transfers',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              if (!_busy && _transfers.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text('No pending credential transfers.'),
                ),
              for (final transfer in _transfers)
                Card(
                  child: ListTile(
                    title: Text(transfer.providerId),
                    subtitle: Text(
                      '${transfer.accountId} • ${transfer.status}',
                    ),
                    trailing: Wrap(
                      children: [
                        IconButton(
                          tooltip: 'Reject transfer',
                          onPressed: _busy ? null : () => _reject(transfer),
                          icon: const Icon(Icons.close),
                        ),
                        IconButton(
                          tooltip: transfer.status == 'accepted'
                              ? 'Retry secure storage'
                              : 'Receive credential',
                          onPressed: _busy ? null : () => _redeem(transfer),
                          icon: const Icon(Icons.download_for_offline_outlined),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
