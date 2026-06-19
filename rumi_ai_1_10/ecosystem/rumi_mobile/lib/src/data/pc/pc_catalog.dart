class ProviderEntry {
  const ProviderEntry({
    required this.providerId,
    required this.displayName,
    required this.kind,
    required this.configured,
    required this.openaiCompatible,
    required this.local,
    required this.catalogOnly,
    required this.defaultModel,
    required this.capabilities,
    required this.envVars,
    required this.baseUrlEnvs,
    required this.configuredApiCount,
  });

  final String providerId;
  final String displayName;
  final String kind;
  final bool configured;
  final bool openaiCompatible;
  final bool local;
  final bool catalogOnly;
  final String defaultModel;
  final List<String> capabilities;
  final List<String> envVars;
  final List<String> baseUrlEnvs;
  final int configuredApiCount;

  bool get isCloud => !local && !catalogOnly;

  factory ProviderEntry.fromJson(Map<String, dynamic> json) {
    return ProviderEntry(
      providerId: json['provider_id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      configured: json['configured'] as bool? ?? false,
      openaiCompatible: json['openai_compatible'] as bool? ?? false,
      local: json['local'] as bool? ?? false,
      catalogOnly: json['catalog_only'] as bool? ?? false,
      defaultModel: json['default_model'] as String? ?? '',
      capabilities: (json['capabilities'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
      envVars:
          (json['env_vars'] as List? ?? []).map((e) => e.toString()).toList(),
      baseUrlEnvs: (json['base_url_envs'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
      configuredApiCount: (json['configured_api_count'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'provider_id': providerId,
        'display_name': displayName,
        'kind': kind,
        'configured': configured,
        'openai_compatible': openaiCompatible,
        'local': local,
        'catalog_only': catalogOnly,
        'default_model': defaultModel,
        'capabilities': capabilities,
        'env_vars': envVars,
        'base_url_envs': baseUrlEnvs,
        'configured_api_count': configuredApiCount,
      };
}

class ModelEntry {
  const ModelEntry({
    required this.id,
    required this.providerId,
    required this.modelId,
    required this.displayName,
    required this.type,
    required this.enabled,
    required this.maxContext,
    required this.supportsThinking,
    required this.supportsVision,
    required this.supportsToolCalling,
    required this.thinkingLevels,
    required this.defaultThinkingLevel,
    required this.speedTier,
    required this.costTier,
    required this.capabilityTags,
  });

  final String id;
  final String providerId;
  final String modelId;
  final String displayName;
  final String type;
  final bool enabled;
  final int maxContext;
  final bool supportsThinking;
  final bool supportsVision;
  final bool supportsToolCalling;
  final List<String> thinkingLevels;
  final String? defaultThinkingLevel;
  final String speedTier;
  final String costTier;
  final List<String> capabilityTags;

  factory ModelEntry.fromJson(Map<String, dynamic> json) {
    return ModelEntry(
      id: json['id'] as String? ?? '',
      providerId: json['provider_id'] as String? ?? '',
      modelId: json['model_id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      type: json['type'] as String? ?? 'chat',
      enabled: json['enabled'] as bool? ?? false,
      maxContext: (json['max_context'] as num?)?.toInt() ?? -1,
      supportsThinking: json['supports_thinking'] as bool? ?? false,
      supportsVision: json['supports_vision'] as bool? ?? false,
      supportsToolCalling: json['supports_tool_calling'] as bool? ?? false,
      thinkingLevels: (json['thinking_levels'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
      defaultThinkingLevel: json['default_thinking_level'] as String?,
      speedTier: json['speed_tier'] as String? ?? 'balanced',
      costTier: json['cost_tier'] as String? ?? 'unknown',
      capabilityTags: (json['capability_tags'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class ProfileEntry {
  const ProfileEntry({
    required this.profileId,
    required this.providerId,
    required this.modelId,
    required this.displayName,
    required this.qualifiedModelId,
    required this.type,
    required this.maxContext,
    required this.supportsThinking,
    required this.supportsVision,
    required this.supportsToolCalling,
  });

  final String profileId;
  final String providerId;
  final String modelId;
  final String displayName;
  final String qualifiedModelId;
  final String type;
  final int maxContext;
  final bool supportsThinking;
  final bool supportsVision;
  final bool supportsToolCalling;

  factory ProfileEntry.fromJson(Map<String, dynamic> json) {
    return ProfileEntry(
      profileId: json['profile_id'] as String? ?? json['id'] as String? ?? '',
      providerId: json['provider_id'] as String? ?? '',
      modelId: json['model_id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      qualifiedModelId: json['qualified_model_id'] as String? ?? '',
      type: json['type'] as String? ?? 'chat',
      maxContext: (json['max_context'] as num?)?.toInt() ?? -1,
      supportsThinking: json['supports_thinking'] as bool? ?? false,
      supportsVision: json['supports_vision'] as bool? ?? false,
      supportsToolCalling: json['supports_tool_calling'] as bool? ?? false,
    );
  }
}

class TemplateEntry {
  const TemplateEntry({
    required this.entryId,
    required this.name,
    required this.description,
    required this.sourceType,
    required this.tags,
    required this.updatedAt,
  });

  final String entryId;
  final String name;
  final String description;
  final String sourceType;
  final List<String> tags;
  final String updatedAt;

  factory TemplateEntry.fromJson(Map<String, dynamic> json) {
    return TemplateEntry(
      entryId: json['entry_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
      tags: (json['tags'] as List? ?? []).map((e) => e.toString()).toList(),
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}

class PcCatalog {
  const PcCatalog({
    required this.providers,
    required this.models,
    required this.profiles,
    required this.templates,
    required this.fetchedAt,
  });

  final List<ProviderEntry> providers;
  final List<ModelEntry> models;
  final List<ProfileEntry> profiles;
  final List<TemplateEntry> templates;
  final DateTime fetchedAt;

  List<ModelEntry> modelsForProvider(String providerId) =>
      models.where((m) => m.providerId == providerId).toList();

  List<ProviderEntry> get configuredProviders =>
      providers.where((p) => p.configured).toList();

  factory PcCatalog.fromJson(Map<String, dynamic> json) {
    return PcCatalog(
      providers: (json['providers'] as List? ?? [])
          .map((e) => ProviderEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      models: (json['models'] as List? ?? [])
          .map((e) => ModelEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      profiles: (json['profiles'] as List? ?? [])
          .map((e) => ProfileEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      templates: (json['templates'] as List? ?? [])
          .map((e) => TemplateEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      fetchedAt: DateTime.now(),
    );
  }
}

class PcBootstrap {
  const PcBootstrap({
    required this.deviceId,
    required this.label,
    required this.version,
    required this.capabilities,
    required this.cursor,
  });

  final String deviceId;
  final String label;
  final String version;
  final PcBootstrapCapabilities capabilities;
  final String cursor;

  factory PcBootstrap.fromJson(Map<String, dynamic> json) {
    final server = json['server'] as Map<String, dynamic>? ?? const {};
    final caps = json['capabilities'] as Map<String, dynamic>? ?? const {};
    return PcBootstrap(
      deviceId: server['device_id'] as String? ?? '',
      label: server['label'] as String? ?? '',
      version: server['version'] as String? ?? '',
      capabilities: PcBootstrapCapabilities.fromJson(caps),
      cursor: json['cursor'] as String? ?? '',
    );
  }
}

class PcBootstrapCapabilities {
  const PcBootstrapCapabilities({
    required this.chat,
    required this.tools,
    required this.approvals,
    required this.credentialTransfer,
  });

  final bool chat;
  final bool tools;
  final bool approvals;
  final bool credentialTransfer;

  factory PcBootstrapCapabilities.fromJson(Map<String, dynamic> json) {
    return PcBootstrapCapabilities(
      chat: json['chat'] as bool? ?? false,
      tools: json['tools'] as bool? ?? false,
      approvals: json['approvals'] as bool? ?? false,
      credentialTransfer: json['credential_transfer'] as bool? ?? false,
    );
  }
}
