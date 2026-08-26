import { expect, test, type Page, type Route } from "@playwright/test";

type Kind = "write" | "image" | "slide" | "movie";
type CommandExecutePayload = { command?: string; args?: Record<string, unknown>; conversation_id?: string | null; mode?: string };
type ApiTrace = { commandExecutions: Array<{ request: CommandExecutePayload; response: Record<string, unknown> }> };

const now = 1_785_000_000_000;
const longPrompt = "Run a short workspace heartbeat. Check pending tasks, recent failures, QA bugs, blocked work, and the UI layout. This long text catches narrow vertical message bubble regressions when a pack sidecar opens.";
const MOVIE_OPERATIONS = [
  "movie_import_media",
  "movie_edit_timeline",
  "movie_trim_clip",
  "movie_split_clip",
  "movie_update_captions",
  "movie_save_project",
  "movie_export_project",
  "movie_render_project",
];
const MOVIE_TRACKS = ["video", "audio", "captions"];
const surfaces: Record<Kind, { title: string; field: string; text: string; buttons: string[] }> = {
  write: { title: "ビジネスメールテンプレート集", field: "Document body", text: "# ビジネスメールテンプレート集\n\n本文", buttons: ["Sync status", "Undo", "Redo", "Bold", "Italic", "Bulleted list"] },
  image: { title: "画像素材の編集", field: "Image prompt", text: "商品紹介用の明るい画像素材", buttons: ["Sync status", "Undo", "Redo", "Generate", "Crop", "Variants", "Mask"] },
  slide: { title: "四半期レビュー資料", field: "Slide notes", text: "# 四半期レビュー資料\n\nノート", buttons: ["Sync status", "Undo", "Redo", "Select", "Text", "Shapes", "Image"] },
  movie: { title: "商品紹介動画の編集", field: "Movie brief", text: "商品紹介動画の編集", buttons: ["Sync status", "Undo", "Redo", "Play", "Split", "Captions", "Audio"] },
};
const profile = { profile_id: "stub/default", qualified_model_id: "stub/default", provider_id: "stub", provider_display_name: "Stub", model_id: "default", display_name: "Stub Default", max_context: -1, max_context_tokens: -1, supports_thinking: false, supports_tool_calling: true, supports_vision: false, local: true, availability: { local: true, configured: true } };
const settings = { general: { language: "en", composer_placeholder: "Message Rumi...", keyboard_button_navigation: true, show_activity_in_messages: true }, models: { preferred_model: "stub/default", favorite_profiles: ["stub/default"] }, preview: { max_items: 12, auto_open: false, default_mode: "auto" }, calendar: {}, chat_rendering: { unknown_block_strategy: "hidden", show_widgets: true }, sidebar: { pinned_item_ids: [], starred_item_ids: [], custom_tool_tags: {} }, tools: { default_mode: "auto", selection_strategy: "hybrid", standard_permissions: {} }, commands: {} };

function ok(data: unknown) { return { status: "ok", data }; }
async function json(route: Route, data: unknown) { await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(data)) }); }
function conversation() {
  return {
    id: "c-pack-ui",
    title: "Workspace Surface Guard Chat",
    created_at: now - 60_000,
    updated_at: now,
    model: "stub/default",
    tags: ["workspace-surfaces"],
    is_starred: false,
    is_pinned: false,
    is_archived: false,
    messages: [
      { id: "m-user", role: "user", content: [{ type: "text", text: longPrompt }], raw_text: longPrompt, created_at: now - 20_000, conversation_id: "c-pack-ui", parent_id: null, children_ids: [], sequence_number: 1, finish_reason: null, usage: null, widget: null },
      { id: "m-assistant", role: "assistant", content: [{ type: "text", text: "Workspace surface command fixtures are ready." }], raw_text: "Workspace surface command fixtures are ready.", created_at: now - 10_000, conversation_id: "c-pack-ui", parent_id: "m-user", children_ids: [], sequence_number: 2, finish_reason: "stop", usage: { total_tokens: 42 }, widget: null, model: "stub/default", metadata: {}, events: [], tool_logs: [] },
    ],
  };
}
function command(kind: Kind) {
  const ui: Record<string, unknown> = { surface: { kind, layoutMode: "split", chatPlacement: "left" } };
  if (kind === "movie") ui.operations = MOVIE_OPERATIONS;
  return { id: kind, name: kind, label: surfaces[kind].title, description: `Open ${kind} surface`, category: kind, visibility: "default", risk: "low", modes: ["chat", "coding", "agent"], args: [{ name: "text", type: "string", required: false, capture: "rest" }], source_pack_id: "rumi_workspace_surfaces", trust_level: "activated_pack", execution: { type: "rumi_function", pack_id: "rumi_workspace_surfaces", function_id: `open_${kind}_surface` }, ui };
}
function movieProject(text: string, resourceId: string) {
  const clips = [
    { id: "clip-1", name: "Pack storyboard intro", asset_id: "asset-1", track: "video", start: 0, duration: 3.5, in: 0, out: 3.5, color: "sky" },
    { id: "clip-2", name: "Product demo take", asset_id: "asset-2", track: "video", start: 3.5, duration: 5, in: 0, out: 5, color: "violet" },
    { id: "clip-3", name: "Feature closeup", asset_id: "asset-3", track: "video", start: 8.5, duration: 4, in: 0, out: 4, color: "emerald" },
    { id: "clip-4", name: "CTA end slate", asset_id: "asset-4", track: "video", start: 12.5, duration: 2, in: 0, out: 2, color: "amber" },
  ];
  const timeline = { duration: 14.5, fps: 30, tracks: MOVIE_TRACKS };
  return {
    project_id: resourceId,
    title: surfaces.movie.title,
    brief: text,
    format: "16:9 / H.264",
    resolution: "1920x1080",
    fps: 30,
    assets: [
      { id: "asset-1", name: "Opening card", kind: "video", mime_type: "video/mp4", source: "generated:opening-card", duration: 3.5 },
      { id: "asset-2", name: "Product demo", kind: "video", mime_type: "video/mp4", source: "generated:product-demo", duration: 5 },
      { id: "asset-3", name: "Feature closeup", kind: "video", mime_type: "video/mp4", source: "generated:feature-closeup", duration: 4 },
      { id: "asset-4", name: "End slate", kind: "video", mime_type: "video/mp4", source: "generated:end-slate", duration: 2 },
    ],
    clips,
    captions: [
      { id: "caption-1", text: "商品の魅力を15秒で伝える", start: 0.4, duration: 2.4 },
      { id: "caption-2", text: "導入後のベネフィットを明確に示す", start: 6, duration: 3 },
    ],
    audio: { music: "local-placeholder", voice_gain: 0.82, ducking: true },
    render: { engine: "unavailable", enabled: false, status: "disabled" },
    operations: MOVIE_OPERATIONS,
    timeline,
  };
}
function descriptor(kind: Kind, text: string) {
  const resourceId = `${kind}:c-pack-ui`;
  const initialText = text || surfaces[kind].text;
  const payload: Record<string, unknown> = { initial_text: initialText, attached_files: [], selection: null };
  if (kind === "movie") {
    const project = movieProject(initialText, resourceId);
    payload.movie_project = project;
    payload.operations = MOVIE_OPERATIONS;
    payload.tool_timeline = project.timeline;
  }
  return { id: resourceId, kind, title: surfaces[kind].title, sourcePackId: "rumi_workspace_surfaces", renderer: `rumi_workspace_surfaces.${kind}`, conversationId: "c-pack-ui", resourceId, payload, layoutMode: "split", chatPlacement: "left" };
}

async function installMocks(page: Page, trace?: ApiTrace) {
  const commands = (Object.keys(surfaces) as Kind[]).map(command);
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const method = req.method();
    const convo = conversation();
    if (path === "/api/health") return json(route, { status: "ok", pack: "defaultspack", ts: "2026-07-01T00:00:00Z" });
    if (path === "/api/ui/catalog") return json(route, { app: { id: "defaultspack", name: "Rumi", account: { display_name: "Layout Guard", plan_label: "Local" } }, agent_service: { profiles: [], capabilities: [], presets: [] }, sidebar: { filters: [], items: [] }, settings: { sections: [], values: settings }, chat_rendering: { renderers: [] }, skills: [], extension_points: [] });
    if (path === "/api/ui/settings") return json(route, { sections: [], values: settings });
    if (path === "/api/ui/commands") return json(route, { commands });
    if (path === "/api/ui/commands/execute" && method === "POST") {
      const payload = req.postDataJSON() as CommandExecutePayload;
      const kind = String(payload.command ?? "") as Kind;
      if (kind in surfaces) {
        const surface = descriptor(kind, String(payload.args?.text ?? surfaces[kind].text));
        const response = { command: command(kind), executed: true, result: { surface }, effects: [{ type: "surface.open", surface }], message: `${surfaces[kind].title} surface opened.` };
        trace?.commandExecutions.push({ request: payload, response });
        return json(route, response);
      }
    }
    if (path === "/api/ai/profiles") return json(route, { profiles: [profile], count: 1 });
    if (path === "/api/ai/models/search") return json(route, { models: [profile], count: 1 });
    if (path === "/api/tools/catalog") return json(route, { services: [], tools: [], count: 0 });
    if (path === "/api/chat/conversations" && method === "GET") return json(route, { conversations: [{ ...convo, messages: [] }], total: 1 });
    if (path === "/api/chat/conversations" && method === "POST") return json(route, convo);
    if (path === "/api/chat/conversations/c-pack-ui") return json(route, convo);
    if (path === "/api/ui/conversations/c-pack-ui/preview") return json(route, { conversation_id: "c-pack-ui", previews: [], summary: {} });
    if (path === "/api/chat/steer") return json(route, { items: [] });
    if (path === "/api/coding/workspaces") return json(route, { workspaces: [], selected_workspace_id: null });
    if (path === "/api/coding/context") return json(route, { branch: null, root_folder: null, files: [], entries: [], git: null });
    return json(route, {});
  });
}
async function openApp(page: Page, trace?: ApiTrace) {
  await installMocks(page, trace);
  await page.goto("/static/chat");
  await expect(page.getByText("Workspace Surface Guard Chat").first()).toBeVisible();
}
function captureErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}
async function openSurface(page: Page, kind: Kind) {
  await page.locator("textarea.rumi-composer-textarea").fill(`/${kind} ${surfaces[kind].text}`);
  await page.keyboard.press("Enter");
  const surface = page.locator(`[data-surface-kind="${kind}"]`);
  await expect(surface).toBeVisible();
  return surface;
}
async function metrics(page: Page) {
  return page.evaluate(() => {
    const rect = (selector: string) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
    };
    const chat = rect(".rumi-chat-pane");
    const sidecar = rect(".rumi-activity-preview-pane");
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const overlap = Boolean(chat && sidecar && chat.right > sidecar.left - 2 && sidecar.right > chat.left + 2 && chat.bottom > sidecar.top + 2 && sidecar.bottom > chat.top + 2);
    const out = Object.entries({ chat, sidecar }).filter(([, r]) => r && (r.left < -1 || r.right > viewport.width + 1 || r.top < -1 || r.bottom > viewport.height + 1));
    const crushed = Array.from(document.querySelectorAll(".rumi-message-bubble")).map((el) => {
      const r = el.getBoundingClientRect();
      const text = el.textContent?.replace(/\s+/g, " ").trim() ?? "";
      return { text: text.slice(0, 90), len: text.length, width: r.width, height: r.height, ratio: r.height / Math.max(r.width, 1) };
    }).filter((item) => item.len >= 80 && (item.width < 220 || item.ratio > 1.15));
    return { viewport, chat, sidecar, overlap, out, crushed };
  });
}

test("pack sidecar does not crush chat or long bubbles at desktop width", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const errors = captureErrors(page);
  await openApp(page);
  await openSurface(page, "movie");
  const result = await metrics(page);
  const detail = JSON.stringify(result, null, 2);
  expect(result.chat?.width ?? 0, detail).toBeGreaterThanOrEqual(360);
  expect(result.sidecar?.width ?? 0, detail).toBeLessThanOrEqual(540);
  expect(result.overlap, detail).toBe(false);
  expect(result.out, detail).toEqual([]);
  expect(result.crushed, detail).toEqual([]);
  expect(errors).toEqual([]);
});

for (const kind of Object.keys(surfaces) as Kind[]) {
  test(`/${kind} supports open, controls, edit, append, and close`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const errors = captureErrors(page);
    await openApp(page);
    const surface = await openSurface(page, kind);
    for (const label of surfaces[kind].buttons) await surface.getByRole("button", { name: label }).click();
    const edited = `${surfaces[kind].title} edited by UI contract`;
    await surface.getByLabel(surfaces[kind].field).fill(edited);
    await surface.getByRole("button", { name: "Composer" }).click();
    await expect(page.locator("textarea.rumi-composer-textarea")).toHaveValue(edited);
    await surface.getByRole("button", { name: "Close surface" }).click();
    await expect(page.locator(`[data-surface-kind="${kind}"]`)).toBeHidden();
    expect(errors).toEqual([]);
  });
}

test("/movie opens from pack command effect and reports operation statuses", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const errors = captureErrors(page);
  const trace: ApiTrace = { commandExecutions: [] };
  await openApp(page, trace);
  const surface = await openSurface(page, "movie");

  expect(trace.commandExecutions).toHaveLength(1);
  const execution = trace.commandExecutions[0];
  expect(execution.request).toMatchObject({ command: "movie", args: { text: surfaces.movie.text }, conversation_id: "c-pack-ui", mode: "agent" });
  const result = execution.response.result as { surface?: Record<string, unknown> };
  const openedSurface = result.surface;
  expect(openedSurface).toBeTruthy();
  expect(execution.response.effects).toEqual([{ type: "surface.open", surface: openedSurface }]);
  expect(openedSurface).toMatchObject({
    id: "movie:c-pack-ui",
    kind: "movie",
    sourcePackId: "rumi_workspace_surfaces",
    renderer: "rumi_workspace_surfaces.movie",
    conversationId: "c-pack-ui",
    resourceId: "movie:c-pack-ui",
    payload: {
      initial_text: surfaces.movie.text,
      operations: MOVIE_OPERATIONS,
      movie_project: {
        project_id: "movie:c-pack-ui",
        operations: MOVIE_OPERATIONS,
        timeline: { duration: 14.5, fps: 30, tracks: MOVIE_TRACKS },
        render: { enabled: false, status: "disabled" },
      },
      tool_timeline: { duration: 14.5, fps: 30, tracks: MOVIE_TRACKS },
    },
    layoutMode: "split",
    chatPlacement: "left",
  });

  await expect(surface.getByText("4 clips / 2 captions")).toBeVisible();
  await expect(surface.getByLabel("Selected clip name")).toHaveValue("Pack storyboard intro");
  await surface.getByRole("button", { name: "Import media" }).click();
  await expect(surface.getByText("5 clips / 2 captions")).toBeVisible();
  await expect(surface.getByText("Imported media and appended it to the timeline")).toBeVisible();

  await surface.getByRole("button", { name: "Split" }).click();
  await expect(surface.getByText("6 clips / 2 captions")).toBeVisible();
  await expect(surface.getByLabel("Selected clip name")).toHaveValue("Pack storyboard intro B");

  await surface.getByLabel("Selected clip duration").fill("1.25");
  await expect(surface.getByText("Trim metadata updated")).toBeVisible();
  await expect(surface.getByText("1.25s")).toBeVisible();

  await surface.getByRole("button", { name: "Captions" }).click();
  await expect(surface.getByText("6 clips / 3 captions")).toBeVisible();

  await surface.getByRole("button", { name: "Save project" }).click();
  await expect(surface.getByText("Saved local project JSON with 6 clips")).toBeVisible();

  await surface.getByRole("button", { name: "Export project" }).click();
  await expect(surface.getByText("Exported project JSON and timeline EDL")).toBeVisible();

  expect(MOVIE_OPERATIONS).toContain("movie_render_project");
  await surface.getByRole("button", { name: "Render movie" }).click();
  await expect(surface.getByText("ffmpeg render disabled; export is still available")).toBeVisible();

  expect(errors).toEqual([]);
});
