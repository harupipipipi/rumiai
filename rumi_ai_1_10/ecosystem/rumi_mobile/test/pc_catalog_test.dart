import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;

import 'package:rumi_remote_app/src/data/pc/pc_catalog.dart';
import 'package:rumi_remote_app/src/data/pc/pc_catalog_client.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

const _pc = PcConnection(baseUrl: 'http://192.168.1.10:8765', token: 'tok');

http.Response _ok(Map<String, dynamic> data) {
  return http.Response(jsonEncode({'status': 'ok', 'data': data}), 200,
      headers: {'content-type': 'application/json'});
}

void main() {
  group('PcCatalog model parsing', () {
    test('PcBootstrap.fromJson parses server + capabilities', () {
      final b = PcBootstrap.fromJson({
        'server': {'device_id': 'mac', 'label': 'MacBook', 'version': '1.2'},
        'capabilities': {
          'chat': true,
          'tools': true,
          'approvals': false,
          'credential_transfer': true,
        },
        'cursor': 'event-9',
      });
      expect(b.deviceId, 'mac');
      expect(b.label, 'MacBook');
      expect(b.capabilities.chat, isTrue);
      expect(b.capabilities.approvals, isFalse);
      expect(b.cursor, 'event-9');
    });

    test('PcCatalog.fromJson parses providers/models/profiles/templates', () {
      final catalog = PcCatalog.fromJson({
        'providers': [
          {
            'provider_id': 'openai',
            'display_name': 'OpenAI',
            'kind': 'cloud',
            'configured': true,
            'openai_compatible': true,
            'local': false,
            'catalog_only': false,
            'default_model': 'gpt-5.4',
            'capabilities': ['chat', 'tool_calls'],
            'env_vars': ['OPENAI_API_KEY'],
            'base_url_envs': ['OPENAI_BASE_URL'],
            'configured_api_count': 1,
          }
        ],
        'models': [
          {
            'id': 'openai/gpt-5.4',
            'provider_id': 'openai',
            'model_id': 'gpt-5.4',
            'display_name': 'GPT 5.4',
            'type': 'chat',
            'enabled': true,
            'max_context': 128000,
            'supports_thinking': true,
            'supports_vision': true,
            'supports_tool_calling': true,
            'thinking_levels': ['low', 'medium', 'high'],
            'default_thinking_level': 'medium',
            'speed_tier': 'fast',
            'cost_tier': 'medium',
            'capability_tags': ['thinking', 'vision'],
          }
        ],
        'profiles': [],
        'templates': [
          {
            'entry_id': 't1',
            'name': '要約',
            'description': 'テキスト要約',
            'source_type': 'prompt',
            'tags': ['writing'],
            'updated_at': '2026-01-01T00:00:00Z',
          }
        ],
      });
      expect(catalog.providers.length, 1);
      expect(catalog.providers.first.providerId, 'openai');
      expect(catalog.providers.first.configured, isTrue);
      expect(catalog.models.first.modelId, 'gpt-5.4');
      expect(catalog.models.first.maxContext, 128000);
      expect(catalog.templates.first.name, '要約');
      expect(catalog.modelsForProvider('openai').length, 1);
      expect(catalog.modelsForProvider('groq'), isEmpty);
      expect(catalog.configuredProviders.length, 1);
    });
  });

  group('PcCatalogClient', () {
    test('fetchBootstrap calls /api/mobile/v1/bootstrap with bearer', () async {
      String? authHeader;
      String? requestedPath;
      final client = MockClient((request) async {
        authHeader = request.headers['Authorization'];
        requestedPath = request.url.path;
        return _ok({
          'server': {'device_id': 'mac', 'label': 'MacBook', 'version': '1'},
          'capabilities': {
            'chat': true,
            'tools': true,
            'approvals': true,
            'credential_transfer': false,
          },
          'cursor': 'event-0',
        });
      });

      final pcClient = PcCatalogClient(client: client);
      final b = await pcClient.fetchBootstrap(_pc);
      pcClient.close();

      expect(authHeader, 'Bearer tok');
      expect(requestedPath, '/api/mobile/v1/bootstrap');
      expect(b.label, 'MacBook');
      expect(b.capabilities.chat, isTrue);
    });

    test('fetchCapabilities passes provider filter as query param', () async {
      Map<String, String>? query;
      final client = MockClient((request) async {
        query = request.url.queryParameters;
        return _ok(
            {'providers': [], 'models': [], 'profiles': [], 'templates': []});
      });

      final pcClient = PcCatalogClient(client: client);
      await pcClient.fetchCapabilities(_pc,
          providerFilter: 'openai', includeTemplates: false);
      pcClient.close();

      expect(query?['provider'], 'openai');
      expect(query?['include_templates'], 'false');
    });

    test('fetchCapabilities returns catalog from response data', () async {
      final client = MockClient((request) async {
        return _ok({
          'providers': [
            {'provider_id': 'groq', 'display_name': 'Groq', 'configured': false}
          ],
          'models': [
            {
              'id': 'groq/m1',
              'provider_id': 'groq',
              'model_id': 'm1',
              'display_name': 'M1'
            }
          ],
          'profiles': [],
          'templates': [],
        });
      });

      final pcClient = PcCatalogClient(client: client);
      final catalog = await pcClient.fetchCapabilities(_pc);
      pcClient.close();

      expect(catalog.providers.first.providerId, 'groq');
      expect(catalog.models.first.modelId, 'm1');
    });

    test('throws on non-ok status', () async {
      final client = MockClient((request) async {
        return http.Response(
            jsonEncode({
              'status': 'error',
              'error': {'message': 'bad'}
            }),
            500);
      });
      final pcClient = PcCatalogClient(client: client);
      expect(() => pcClient.fetchBootstrap(_pc),
          throwsA(isA<PcCatalogFetchException>()));
    });

    test('throws when pc not configured', () async {
      final client = MockClient((request) async => _ok({}));
      final pcClient = PcCatalogClient(client: client);
      expect(
          () => pcClient
              .fetchBootstrap(const PcConnection(baseUrl: '', token: '')),
          throwsA(isA<PcCatalogFetchException>()));
    });
  });
}
