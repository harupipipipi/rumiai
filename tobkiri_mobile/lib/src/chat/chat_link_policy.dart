/// The result of validating an untrusted assistant-provided link target.
enum ChatLinkDisposition {
  allowedWeb,
  malformed,
  blockedScheme,
  unsupportedScheme,
  blockedCredentials,
}

/// A normalized, fail-closed review of an untrusted link target.
class ChatLinkReview {
  const ChatLinkReview._({
    required this.rawTarget,
    required this.disposition,
    this.uri,
  });

  final String rawTarget;
  final ChatLinkDisposition disposition;
  final Uri? uri;

  /// Whether this target may be offered to the external URL launcher.
  bool get canOpen => disposition == ChatLinkDisposition.allowedWeb;

  /// The actual destination host, or an empty string when none is valid.
  String get host {
    final encoded = uri?.host ?? '';
    try {
      return Uri.decodeComponent(encoded);
    } on FormatException {
      return encoded;
    }
  }

  /// Whether the destination needs an IDN/lookalike identity warning.
  bool get needsIdentityWarning {
    final normalizedHost = host.toLowerCase();
    return normalizedHost.contains('xn--') ||
        RegExp(r'[^\x00-\x7f]').hasMatch(normalizedHost) ||
        RegExp(r'[^\x00-\x7f]').hasMatch(rawTarget);
  }

  /// Classifies [target] without launching it or consulting platform state.
  static ChatLinkReview evaluate(String target) {
    if (target.isEmpty ||
        target != target.trim() ||
        target.length > 4096 ||
        RegExp(r'[\x00-\x20\x7f]').hasMatch(target)) {
      return ChatLinkReview._(
        rawTarget: target,
        disposition: ChatLinkDisposition.malformed,
      );
    }

    final Uri? uri;
    try {
      uri = Uri.tryParse(target);
      if (uri == null || !uri.isAbsolute || uri.scheme.isEmpty) {
        return ChatLinkReview._(
          rawTarget: target,
          disposition: ChatLinkDisposition.malformed,
        );
      }
      // Accessing these properties also rejects malformed authorities/ports.
      uri.host;
      uri.port;
    } on FormatException {
      return ChatLinkReview._(
        rawTarget: target,
        disposition: ChatLinkDisposition.malformed,
      );
    }

    final scheme = uri.scheme.toLowerCase();
    if (scheme == 'file' ||
        scheme == 'data' ||
        scheme == 'javascript' ||
        scheme == 'vbscript') {
      return ChatLinkReview._(
        rawTarget: target,
        uri: uri,
        disposition: ChatLinkDisposition.blockedScheme,
      );
    }
    if (scheme != 'https' && scheme != 'http') {
      return ChatLinkReview._(
        rawTarget: target,
        uri: uri,
        disposition: ChatLinkDisposition.unsupportedScheme,
      );
    }
    if (!uri.hasAuthority || uri.host.isEmpty) {
      return ChatLinkReview._(
        rawTarget: target,
        uri: uri,
        disposition: ChatLinkDisposition.malformed,
      );
    }
    if (uri.userInfo.isNotEmpty) {
      return ChatLinkReview._(
        rawTarget: target,
        uri: uri,
        disposition: ChatLinkDisposition.blockedCredentials,
      );
    }
    return ChatLinkReview._(
      rawTarget: target,
      uri: uri,
      disposition: ChatLinkDisposition.allowedWeb,
    );
  }
}
