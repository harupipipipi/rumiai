import { createRumiDataAttributes, defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

export const TYPE_SPECIMEN_CASES = Object.freeze([
  { id: "long-ja-heading", role: "pageTitle", text: "未対応会話を短時間で処理するための優先度付きインボックス" },
  { id: "mixed-ja-en", role: "body", text: "株式会社Rumi Operations 2026 Q2 SLAレビュー" },
  { id: "long-company", role: "body", text: "日本リレーオペレーションズ株式会社カスタマーサクセス統括本部" },
  { id: "date-money", role: "numeric", text: "2026-06-26 / JPY 1,284,500 / USD 8,420.33" },
  { id: "table", role: "table", text: "Owner / Status / Due date / Amount" },
  { id: "form-label", role: "label", text: "返信テンプレートの適用範囲" },
  { id: "message-body", role: "body", text: "先週の障害について、原因と再発防止策を確認したいです。" },
  { id: "button", role: "label", text: "返信を送信" },
  { id: "caption", role: "caption", text: "最終更新 2026-06-26 09:30 JST" },
  { id: "error", role: "status", text: "送信に失敗しました。接続を確認して再試行してください。" }
]);

export function createRenderMatrix(config = defineRumiFrontend(), overrides = {}) {
  const viewports = overrides.viewports ?? config.viewports;
  const textScales = overrides.textScales ?? config.textScales;
  const scenarios = overrides.scenarios ?? config.scenarios;
  return viewports.flatMap((viewport) =>
    textScales.flatMap((textScale) =>
      scenarios.map((scenario) => ({
        viewport,
        textScale,
        scenario,
      })),
    ),
  );
}

export function createRenderJobs(candidate, contract, config = defineRumiFrontend()) {
  const nodeId = contract.id ?? candidate.nodeId;
  return createRenderMatrix(config).map((entry) => {
    const id = [
      nodeId,
      candidate.candidateId ?? candidate.id,
      `w${entry.viewport}`,
      `t${String(entry.textScale).replace(".", "-")}`,
      entry.scenario,
    ].join("__");
    return {
      id,
      nodeId,
      candidateId: candidate.candidateId ?? candidate.id,
      viewport: entry.viewport,
      textScale: entry.textScale,
      scenario: entry.scenario,
      url: buildCandidateUrl(candidate, entry),
      outputPath: `.rumi/ui/renders/${nodeId}/${candidate.candidateId ?? candidate.id}/${id}.png`,
      requiredAttributes: createRumiDataAttributes({
        nodeId,
        density: contract.density,
        role: "interaction-region",
      }),
    };
  });
}

export function createTypeSpecimenManifest(foundationId, config = defineRumiFrontend()) {
  const viewports = config.viewports.filter((viewport) => [390, 768, 1440].includes(viewport));
  return {
    foundationId,
    viewports,
    textScales: config.textScales,
    cases: TYPE_SPECIMEN_CASES,
    outputDirectory: `.rumi/ui/renders/foundation/${foundationId}/type-specimen`,
  };
}

export function createSourceAttribute(filePath, line) {
  if (!filePath || !Number.isInteger(line) || line < 1) {
    throw new TypeError("source attribute requires a file path and one-based line number");
  }
  return `${filePath}:${line}`;
}

function buildCandidateUrl(candidate, entry) {
  const baseUrl = candidate.previewUrl ?? "about:blank";
  if (baseUrl === "about:blank") {
    return baseUrl;
  }
  const url = new URL(baseUrl, "http://rumi.local");
  url.searchParams.set("rumiViewport", String(entry.viewport));
  url.searchParams.set("rumiTextScale", String(entry.textScale));
  url.searchParams.set("rumiScenario", entry.scenario);
  return candidate.previewUrl?.startsWith("http") ? url.toString() : `${url.pathname}${url.search}`;
}
