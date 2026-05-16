class RumiApiException implements Exception {
  const RumiApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() {
    final code = statusCode == null ? '' : ' ($statusCode)';
    return 'RumiApiException$code: $message';
  }
}

class RumiHealth {
  const RumiHealth({
    required this.status,
    required this.raw,
    this.pack,
    this.timestamp,
  });

  final String status;
  final String? pack;
  final DateTime? timestamp;
  final Map<String, dynamic> raw;

  bool get isHealthy {
    final normalized = status.toLowerCase();
    return normalized == 'healthy' || normalized == 'ok';
  }

  factory RumiHealth.fromJson(Object? value) {
    final map = asMap(value);
    return RumiHealth(
      status: asString(map['status'], fallback: 'unknown'),
      pack: blankToNull(asString(map['pack'] ?? map['service'])),
      timestamp: parseDate(map['ts'] ?? map['timestamp']),
      raw: map,
    );
  }
}

class RumiModule {
  const RumiModule({
    required this.id,
    required this.kind,
    required this.state,
    required this.displayName,
    required this.description,
    required this.dependencies,
    required this.experimental,
    required this.raw,
    this.updatedAt,
    this.lastError,
  });

  final String id;
  final String kind;
  final String state;
  final String displayName;
  final String description;
  final List<String> dependencies;
  final bool experimental;
  final DateTime? updatedAt;
  final String? lastError;
  final Map<String, dynamic> raw;

  bool get enabled => state == 'enabled' || state == 'experimental';
  bool get degraded => state == 'degraded' || state == 'error_disabled';

  factory RumiModule.fromJson(Object? value) {
    final map = asMap(value);
    final id = asString(map['module_id'] ?? map['id']);
    return RumiModule(
      id: id,
      kind: asString(map['kind'], fallback: 'backend'),
      state: asString(map['state'], fallback: 'unknown'),
      displayName: asString(
        map['display_name'] ?? map['name'],
        fallback: id.isEmpty ? 'unknown' : id,
      ),
      description: asString(map['description']),
      dependencies: asStringList(map['dependencies']),
      experimental: map['experimental'] == true,
      updatedAt: parseDate(map['updated_at'] ?? map['updatedAt']),
      lastError: blankToNull(asString(map['last_error'])),
      raw: map,
    );
  }
}

class ModuleCatalog {
  const ModuleCatalog({
    required this.modules,
    required this.raw,
  });

  final List<RumiModule> modules;
  final Map<String, dynamic> raw;

  int get count => modules.length;

  factory ModuleCatalog.fromJson(Object? value) {
    final map = asMap(value);
    final source = map.containsKey('modules') ? map['modules'] : value;
    final list = asList(source);
    return ModuleCatalog(
      modules: list.map(RumiModule.fromJson).toList(growable: false),
      raw: map,
    );
  }
}

class MigrationStatus {
  const MigrationStatus({
    required this.summary,
    required this.raw,
  });

  final String summary;
  final Map<String, dynamic> raw;

  factory MigrationStatus.fromJson(Object? value) {
    final map = asMap(value);
    final status = asString(
      map['status'] ?? map['state'] ?? map['message'],
      fallback: 'unknown',
    );
    final migrated = map['migrated'];
    final total = map['total'];
    final suffix =
        migrated == null || total == null ? '' : ' ($migrated/$total)';
    return MigrationStatus(summary: '$status$suffix', raw: map);
  }
}

class PackRequest {
  const PackRequest({
    required this.id,
    required this.kind,
    required this.status,
    required this.summary,
    required this.raw,
    this.createdAt,
  });

  final String id;
  final String kind;
  final String status;
  final String summary;
  final DateTime? createdAt;
  final Map<String, dynamic> raw;

  factory PackRequest.fromJson(Object? value) {
    final map = asMap(value);
    final id = asString(map['request_id'] ?? map['id']);
    return PackRequest(
      id: id,
      kind: asString(map['kind'] ?? map['type'], fallback: 'request'),
      status: asString(map['status'] ?? map['state'], fallback: 'unknown'),
      summary: asString(
        map['summary'] ?? map['description'] ?? map['reason'],
        fallback: id.isEmpty ? 'Pack request' : id,
      ),
      createdAt: parseDate(map['created_at'] ?? map['createdAt']),
      raw: map,
    );
  }
}

Map<String, dynamic> asMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, item) => MapEntry('$key', item));
  }
  return {};
}

List<Object?> asList(Object? value) {
  if (value is List) {
    return value;
  }
  return const [];
}

String asString(Object? value, {String fallback = ''}) {
  if (value == null) {
    return fallback;
  }
  final text = '$value'.trim();
  return text.isEmpty ? fallback : text;
}

List<String> asStringList(Object? value) {
  return asList(value)
      .map((item) => asString(item))
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String? blankToNull(String value) {
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

DateTime? parseDate(Object? value) {
  if (value == null) {
    return null;
  }
  return DateTime.tryParse('$value');
}
