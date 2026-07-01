import {expect, test} from '@playwright/test';
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {PNG} from 'pngjs';

let server;
let profile;
let apiLog;

const graphPort = {
  port_key: 'frontend.surface',
  node_id: 'defaultspack.base_runtime',
  port_id: 'frontend',
  target_node_ref: 'defaultspack.base_runtime',
  target_port: {
    id: 'frontend',
    port_id: 'frontend',
    label: 'Frontend Surface',
    direction: 'input',
    standards: ['rumi.surface'],
    multi: false,
  },
  source_node_id: 'defaultspack.web_surface',
  source_node_ref: 'defaultspack.web_surface',
  source_port_id: 'surface',
  source_port: {
    id: 'surface',
    port_id: 'surface',
    label: 'Default Surface',
    direction: 'output',
    standards: ['rumi.surface'],
  },
  source_ref: 'defaultspack.web_surface',
};

function surfaceNode(packId, ref, title) {
  return {
    node_id: `${packId}.${ref}`,
    ref,
    title,
    kind: 'surface',
    component_type: 'frontend',
    metadata: {component_type: 'frontend'},
    display_name: {en: title},
    ports: [{id: 'surface', port_id: 'surface', label: 'Surface', direction: 'output', standards: ['rumi.surface']}],
  };
}

function toolNode(packId, ref, title) {
  return {
    node_id: `${packId}.${ref}`,
    ref,
    title,
    kind: 'tool_bundle',
    component_type: 'tool',
    metadata: {component_type: 'tool'},
    display_name: {en: title},
    ports: [{id: 'tools', port_id: 'tools', label: 'Tools', direction: 'output', standards: ['rumi.tool.bundle']}],
  };
}

const catalog = {
  version: 1,
  packs: [
    {
      pack_id: 'defaultspack',
      name: 'Defaults Pack',
      description: 'Base runtime and default launch surface.',
      pack_identity: 'defaultspack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [{graph_id: 'defaultspack.startup', display_name: {en: 'Default Startup'}, node_count: 2, edge_count: 1}],
      nodes: [surfaceNode('defaultspack', 'web_surface', 'Default Web Surface')],
    },
    {
      pack_id: 'frontendpack',
      name: 'Browser Frontend Pack',
      description: 'Replacement frontend surface from a dedicated pack.',
      pack_identity: 'frontendpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [surfaceNode('frontendpack', 'web_surface', 'Browser Frontend Surface')],
    },
    {
      pack_id: 'altfrontpack',
      name: 'Chooser Frontend Pack',
      description: 'Alternative selector-driven frontend surface.',
      pack_identity: 'altfrontpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [surfaceNode('altfrontpack', 'surface_choice', 'Chooser Frontend Surface')],
    },
    {
      pack_id: 'searchpack',
      name: 'Search Tool Pack',
      description: 'Adds search tools to the runtime.',
      pack_identity: 'searchpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [toolNode('searchpack', 'tool_bundle', 'Search Tool Bundle')],
    },
    {
      pack_id: 'localpack',
      name: 'Local Tool Pack',
      description: 'Adds local file tools to the runtime.',
      pack_identity: 'localpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [toolNode('localpack', 'tool_bundle', 'Local Tool Bundle')],
    },
  ],
};

function resetProfile() {
  apiLog = [];
  profile = {
    version: 1,
    profile_id: 'mock-profile',
    name: 'Visual QA Profile',
    base_pack: 'defaultspack',
    graph_id: 'defaultspack.startup',
    graph_ports: [graphPort],
    packs: ['defaultspack'],
    node_overrides: {},
    created_at: 1767225600,
    updated_at: 1767225600,
    launch_capability_graph: true,
    policy: {
      require_capability_graph_compile: true,
      enforce_api_route_allowlist: true,
      tool_allowlist: [],
    },
    permissions: {host_actions: 'approval_required'},
    metadata: {visual_test: true},
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function envelope(data) {
  return {success: true, data, error: null};
}

function sendJson(response, status, payload) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers': 'content-type,x-rumi-panel-csrf',
  });
  response.end(JSON.stringify(payload));
}

function readBody(request) {
  return new Promise((resolve) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      if (!body) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(body));
      } catch {
        resolve({});
      }
    });
  });
}

function compilePreview() {
  const frontendNode = profile.node_overrides['frontend.surface'] || 'defaultspack.web_surface';
  const packId = frontendNode.split('.')[0] || 'defaultspack';
  const toolAllowlist = profile.packs.filter((packId) => ['searchpack', 'localpack'].includes(packId));
  const previewProfile = {...profile, policy: {...profile.policy, tool_allowlist: toolAllowlist}};
  const surface_launch_target = {
    kind: 'frontend',
    pack_id: packId,
    surface: frontendNode,
    node_id: frontendNode,
    source: 'visual-mock',
  };
  return {
    ok: true,
    profile_id: profile.profile_id,
    profile: clone(previewProfile),
    capability_graph: {
      ok: true,
      graph_id: profile.graph_id,
      capability_profile_id: 'visual-qa-capability-profile',
      runtime_profile_key: 'visual-qa-runtime',
      runtime_profile: {frontend: frontendNode, tools: toolAllowlist},
      surface_launch_target,
      diagnostics: [],
    },
    surface_launch_target,
    diagnostics: [],
  };
}

function startMockApi() {
  resetProfile();
  server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1:8765');
    if (request.method === 'OPTIONS') {
      sendJson(response, 200, envelope({}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/health') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({status: 'ok', needs_setup: false, panel_ready: true, runtime_ready: true, runtime_status: 'runtime_ready'}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/setup/status') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({needs_setup: false, panel_ready: true, runtime_ready: true, runtime_status: 'runtime_ready'}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/startup/profiles') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({profiles: [clone(profile)], active_profile_id: 'mock-profile', last_launched_profile_id: null, catalog: clone(catalog)}));
      return;
    }
    if (request.method === 'PUT' && url.pathname === '/api/panel/startup/profiles/mock-profile') {
      const body = await readBody(request);
      apiLog.push({method: request.method, path: url.pathname, body: clone(body)});
      profile = {...profile, ...body, updated_at: Date.now() / 1000};
      sendJson(response, 200, envelope({profile: clone(profile), updated: true}));
      return;
    }
    if (request.method === 'POST' && url.pathname === '/api/panel/startup/profiles/mock-profile/compile-preview') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope(compilePreview()));
      return;
    }
    if (request.method === 'POST' && url.pathname === '/api/panel/startup/profiles/mock-profile/launch') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({profile: clone(profile), launched: true}));
      return;
    }
    if (request.method === 'POST' && url.pathname === '/api/panel/startup/profiles/mock-profile/activate') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({profile: clone(profile), activated: true, active_profile_id: 'mock-profile'}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/packs') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({
        packs: catalog.packs.map((pack) => ({
          pack_id: pack.pack_id,
          name: pack.name,
          version: 'visual',
          description: pack.description,
          is_core: pack.pack_id === 'defaultspack',
          enabled: pack.enabled,
        })),
        count: catalog.packs.length,
      }));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/settings/profile') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({profile: {username: 'Visual QA', language: 'en', icon: null, occupation: 'test operator'}}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/version') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({app_version: 'visual', display_version: 'visual', kernel_version: 'visual', python_version: '3.x', platform: 'win32', platform_release: 'visual'}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/updates') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({updates: []}));
      return;
    }
    if (request.method === 'GET' && url.pathname === '/api/panel/updates/settings') {
      apiLog.push({method: request.method, path: url.pathname});
      sendJson(response, 200, envelope({auto_update: {rumiai: false, defaultspack: false}, check_interval_hours: 24, last_checked_at: null, last_results: [], updated_at: null}));
      return;
    }

    sendJson(response, 404, {success: false, data: null, error: `Unhandled route ${request.method} ${url.pathname}`});
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(8765, '127.0.0.1', resolve);
  });
}

async function stopMockApi() {
  if (!server) return;
  server.closeIdleConnections?.();
  server.closeAllConnections?.();
  await new Promise((resolve) => server.close(resolve));
  server = undefined;
}

function screenshotStats(buffer) {
  const png = PNG.sync.read(buffer);
  const buckets = new Set();
  let opaque = 0;
  let content = 0;
  let total = 0;
  const pixelCount = png.width * png.height;
  const step = Math.max(1, Math.floor(pixelCount / 60_000));

  for (let pixel = 0; pixel < pixelCount; pixel += step) {
    const offset = pixel * 4;
    const alpha = png.data[offset + 3];
    if (alpha < 8) continue;
    total += 1;
    opaque += alpha > 240 ? 1 : 0;
    const red = png.data[offset];
    const green = png.data[offset + 1];
    const blue = png.data[offset + 2];
    buckets.add(`${red >> 4}:${green >> 4}:${blue >> 4}`);
    const lightBackground = red > 242 && green > 242 && blue > 242;
    const darkBackground = red < 12 && green < 12 && blue < 12;
    if (!lightBackground && !darkBackground) {
      content += 1;
    }
  }

  return {
    width: png.width,
    height: png.height,
    colorBuckets: buckets.size,
    contentRatio: total ? content / total : 0,
    opaqueRatio: total ? opaque / total : 0,
  };
}

function assertUsefulScreenshot(buffer, {minWidth, minHeight, minColorBuckets, minContentRatio}) {
  const stats = screenshotStats(buffer);
  assert.ok(stats.width >= minWidth, `screenshot width ${stats.width} should be >= ${minWidth}`);
  assert.ok(stats.height >= minHeight, `screenshot height ${stats.height} should be >= ${minHeight}`);
  assert.ok(stats.colorBuckets >= minColorBuckets, `screenshot should have at least ${minColorBuckets} color buckets, got ${stats.colorBuckets}`);
  assert.ok(stats.contentRatio >= minContentRatio, `screenshot content ratio ${stats.contentRatio} should be >= ${minContentRatio}`);
  return stats;
}

async function pageHealth(page) {
  return page.evaluate(() => {
    const html = document.documentElement;
    const keyText = [
      'Startup Profiles',
      'Pack Selection',
      'Profile Security',
      'Runtime Preview',
      'Browser Frontend Pack',
      'Search Tool Pack',
      'Local Tool Pack',
    ];
    const missing = keyText.filter((text) => !document.body.innerText.includes(text));
    const visibleByAria = ['Base pack', 'Launch frontend', 'Pack to add'].filter((label) => {
      const element = document.querySelector(`[aria-label="${label}"]`);
      if (!element) return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    return {
      missing,
      visibleByAria,
      horizontalOverflow: Math.max(0, html.scrollWidth - html.clientWidth),
    };
  });
}

async function exerciseProfileRuntime(page) {
  await page.goto('/panel/startup');
  await expect(page.getByRole('heading', {name: 'Startup Profiles', exact: true})).toBeVisible();
  await page.getByLabel('Launch frontend', {exact: true}).selectOption('frontendpack.web_surface');
  await expect.poll(() => profile.node_overrides['frontend.surface']).toBe('frontendpack.web_surface');

  const searchSwitch = page.getByRole('switch', {name: 'Toggle Search Tool Pack tool pack', exact: true});
  await searchSwitch.click();
  await expect.poll(() => profile.packs.includes('searchpack')).toBe(true);
  await expect(searchSwitch).toHaveAttribute('aria-checked', 'true');

  const localSwitch = page.getByRole('switch', {name: 'Toggle Local Tool Pack tool pack', exact: true});
  await localSwitch.click();
  await expect.poll(() => profile.packs.includes('localpack')).toBe(true);
  await expect(localSwitch).toHaveAttribute('aria-checked', 'true');

  await page.getByLabel('Pack to add', {exact: true}).selectOption('altfrontpack');
  await page.getByRole('button', {name: 'Add Pack', exact: true}).click();
  await expect.poll(() => profile.packs.includes('altfrontpack')).toBe(true);
  await page.getByLabel('Launch frontend', {exact: true}).selectOption('altfrontpack.surface_choice');
  await expect.poll(() => profile.node_overrides['frontend.surface']).toBe('altfrontpack.surface_choice');
  await page.getByRole('button', {name: 'Preview', exact: true}).click();
  await expect(page.getByText('altfrontpack', {exact: true})).toBeVisible();
  await expect(page.getByText('searchpack, localpack', {exact: true})).toBeVisible();
}

function latestProfilePut() {
  return [...apiLog]
    .reverse()
    .find((entry) => entry.method === 'PUT' && entry.path === '/api/panel/startup/profiles/mock-profile');
}

test.beforeAll(startMockApi);
test.afterAll(stopMockApi);
test.beforeEach(async ({page}) => {
  resetProfile();
  await page.addInitScript(() => {
    window.localStorage.setItem('rumi-setup', 'true');
  });
});

test('startup profiles visual flow keeps defaultspack while replacing frontend and adding tool packs', async ({page}, testInfo) => {
  await page.setViewportSize({width: 1280, height: 900});
  await exerciseProfileRuntime(page);

  assert.deepEqual(profile.packs, ['defaultspack', 'frontendpack', 'searchpack', 'localpack', 'altfrontpack']);
  assert.equal(profile.base_pack, 'defaultspack');
  assert.equal(profile.node_overrides['frontend.surface'], 'altfrontpack.surface_choice');
  assert.ok(apiLog.some((entry) => entry.method === 'POST' && entry.path.endsWith('/compile-preview')));

  const health = await pageHealth(page);
  assert.deepEqual(health.missing, []);
  assert.deepEqual(health.visibleByAria.sort(), ['Base pack', 'Launch frontend', 'Pack to add'].sort());
  assert.equal(health.horizontalOverflow, 0);

  const screenshot = await page.screenshot({fullPage: true, animations: 'disabled'});
  const stats = assertUsefulScreenshot(screenshot, {
    minWidth: 1200,
    minHeight: 900,
    minColorBuckets: 24,
    minContentRatio: 0.08,
  });
  await testInfo.attach('startup-profiles-desktop.png', {body: screenshot, contentType: 'image/png'});
  testInfo.annotations.push({type: 'visual-stats', description: JSON.stringify(stats)});
});

test('profile security switches persist profile-scoped launch and policy settings', async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await page.goto('/panel/startup');
  await expect(page.getByRole('heading', {name: 'Startup Profiles', exact: true})).toBeVisible();

  const compileSwitch = page.getByRole('switch', {name: 'Compile capability graph before launch', exact: true});
  await expect(compileSwitch).toHaveAttribute('aria-checked', 'true');
  await compileSwitch.click();
  await expect.poll(() => profile.launch_capability_graph).toBe(false);
  assert.equal(latestProfilePut()?.body.launch_capability_graph, false);
  await expect(compileSwitch).toHaveAttribute('aria-checked', 'false');

  const strictCompileSwitch = page.getByRole('switch', {name: 'Require clean graph compile', exact: true});
  await expect(strictCompileSwitch).toHaveAttribute('aria-checked', 'true');
  await strictCompileSwitch.click();
  await expect.poll(() => profile.policy.require_capability_graph_compile).toBe(false);
  assert.equal(latestProfilePut()?.body.policy.require_capability_graph_compile, false);
  await expect(strictCompileSwitch).toHaveAttribute('aria-checked', 'false');

  const routeAllowlistSwitch = page.getByRole('switch', {name: 'Enforce API route allowlist', exact: true});
  await expect(routeAllowlistSwitch).toHaveAttribute('aria-checked', 'true');
  await routeAllowlistSwitch.click();
  await expect.poll(() => profile.policy.enforce_api_route_allowlist).toBe(false);
  assert.equal(latestProfilePut()?.body.policy.enforce_api_route_allowlist, false);
  await expect(routeAllowlistSwitch).toHaveAttribute('aria-checked', 'false');
  assert.equal(profile.base_pack, 'defaultspack');
  assert.deepEqual(profile.packs, ['defaultspack']);
});

test('profiles and packs navigation stay separate surfaces', async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await page.goto('/panel/startup');
  await expect(page.getByRole('heading', {name: 'Startup Profiles', exact: true})).toBeVisible();
  await expect(page.getByText('Pack Selection', {exact: true})).toBeVisible();

  await page.getByRole('link', {name: 'Packs', exact: true}).click();
  await expect(page).toHaveURL(/\/panel\/packs$/);
  await expect(page.getByRole('main').getByRole('heading', {name: 'Packs', exact: true})).toBeVisible();
  await expect(page.getByText('Manage installed packs and their capabilities.', {exact: true})).toBeVisible();
  await expect(page.getByText('Pack Selection', {exact: true})).toHaveCount(0);
  await expect(page.getByLabel('Launch frontend', {exact: true})).toHaveCount(0);
  await expect(page.getByLabel('Pack to add', {exact: true})).toHaveCount(0);

  await page.getByRole('link', {name: 'Profiles', exact: true}).click();
  await expect(page).toHaveURL(/\/panel\/startup$/);
  await expect(page.getByRole('heading', {name: 'Startup Profiles', exact: true})).toBeVisible();
  await expect(page.getByText('Pack Selection', {exact: true})).toBeVisible();
  await expect(page.getByLabel('Launch frontend', {exact: true})).toBeVisible();
});

test('startup profiles stay readable in a narrow viewer when the sidebar is collapsed', async ({page}, testInfo) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/panel/startup');
  await page.getByRole('button', {name: 'Collapse sidebar', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Startup Profiles', exact: true})).toBeVisible();
  await expect(page.getByText('Pack Selection')).toBeVisible();
  await expect(page.getByText('Profile Security')).toBeVisible();

  const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth));
  assert.equal(overflow, 0);
  const screenshot = await page.screenshot({fullPage: true, animations: 'disabled'});
  const stats = assertUsefulScreenshot(screenshot, {
    minWidth: 390,
    minHeight: 844,
    minColorBuckets: 18,
    minContentRatio: 0.06,
  });
  await testInfo.attach('startup-profiles-narrow.png', {body: screenshot, contentType: 'image/png'});
  testInfo.annotations.push({type: 'visual-stats', description: JSON.stringify(stats)});
});

test('settings security tab has visible guardrails and no horizontal overflow', async ({page}, testInfo) => {
  await page.setViewportSize({width: 1280, height: 900});
  await page.goto('/panel/settings');
  await page.getByRole('tab', {name: 'Security', exact: true}).click();
  await expect(page.getByText('Runtime Security')).toBeVisible();
  await expect(page.getByText('Client approval flags')).toBeVisible();
  await expect(page.getByText('Write-like actions')).toBeVisible();
  await expect(page.getByText('Pack execution')).toBeVisible();

  const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth));
  assert.equal(overflow, 0);
  const screenshot = await page.screenshot({fullPage: true, animations: 'disabled'});
  const stats = assertUsefulScreenshot(screenshot, {
    minWidth: 1200,
    minHeight: 900,
    minColorBuckets: 20,
    minContentRatio: 0.06,
  });
  await testInfo.attach('settings-security-desktop.png', {body: screenshot, contentType: 'image/png'});
  testInfo.annotations.push({type: 'visual-stats', description: JSON.stringify(stats)});
});

test('splash loader renders the bundled SVG after startup progress', async ({page}, testInfo) => {
  await page.setViewportSize({width: 900, height: 520});
  await page.addInitScript(() => {
    window.__TAURI__ = {
      event: {
        listen: async (_event, callback) => {
          window.setTimeout(() => callback({payload: 'Loading runtime...'}), 20);
          return () => {};
        },
      },
      core: {
        invoke: async () => 'Loading runtime...',
      },
    };
  });
  const splashUrl = pathToFileURL(path.resolve(process.cwd(), '../src-tauri/splash/index.html')).href;
  await page.goto(splashUrl);
  await expect(page.locator('#loader.visible img[alt="Rumi AI"]')).toBeVisible();
  await expect(page.locator('#progress')).toHaveText('Loading runtime...');
  const imageLoaded = await page.locator('#loader img').evaluate((image) => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0);
  assert.equal(imageLoaded, true);

  const loaderBox = await page.locator('#loader').boundingBox();
  assert.ok(loaderBox);
  assert.ok(loaderBox.width <= 760);
  assert.ok(loaderBox.height > 100);

  const screenshot = await page.screenshot({fullPage: true, animations: 'disabled'});
  const stats = assertUsefulScreenshot(screenshot, {
    minWidth: 900,
    minHeight: 520,
    minColorBuckets: 10,
    minContentRatio: 0.005,
  });
  await testInfo.attach('splash-loader.png', {body: screenshot, contentType: 'image/png'});
  testInfo.annotations.push({type: 'visual-stats', description: JSON.stringify(stats)});
});
