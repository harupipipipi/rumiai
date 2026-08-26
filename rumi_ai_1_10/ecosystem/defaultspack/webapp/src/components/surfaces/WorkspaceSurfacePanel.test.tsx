import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { WorkspaceSurfacePanel } from "./WorkspaceSurfacePanel";
import type { SurfaceDescriptor } from "../../lib/api";

function renderSurface(kind: "write" | "image" | "slide" | "movie", draft: string, payload: Record<string, unknown> = {}): string {
  const surface: SurfaceDescriptor = {
    id: `${kind}:test`,
    kind,
    title: kind,
    payload: { initial_text: draft, ...payload },
  };
  return renderToStaticMarkup(
    createElement(WorkspaceSurfacePanel, {
      surface,
      draft,
      onDraftChange: () => {},
      onAppendDraftToComposer: () => {},
      onClose: () => {},
    }),
  );
}

const unsafeSvg = '<svg xmlns="http://www.w3.org/2000/svg" onclick="alert(1)"><script>alert(1)</script><foreignObject><div>bad</div></foreignObject><iframe src="https://evil.example/frame"></iframe><object data="https://evil.example/object"></object><embed src="https://evil.example/embed"/><image href="https://evil.example/image.svg" xlink:href="https://evil.example/xlink.svg"/><circle onload="alert(1)" cx="5" cy="5" r="4"/></svg>';

function assertSanitizedSvgOutput(html: string, sourceAlias: string): void {
  const imageSource = html.match(/<img[^>]+src="([^"]+)"/i)?.[1] ?? "";
  assert.match(imageSource, /^data:image\/svg\+xml;charset=utf-8,/);
  assert.doesNotMatch(html, new RegExp(`src="${sourceAlias}"`));
  const sanitizedSvg = decodeURIComponent(imageSource.replace(/^data:image\/svg\+xml;charset=utf-8,/, ""));
  assert.doesNotMatch(sanitizedSvg, /script|foreignObject|iframe|object|embed|onclick|onload|evil\.example/i);
}

function withSvgDom<T>(render: () => T): T {
  type Attribute = { name: string; value: string };
  type Edit = { start: number; end: number; value: string };
  type Node = {
    tagName: string;
    attributes: Attribute[];
    removed: boolean;
    openStart: number;
    openEnd: number;
    closeEnd: number;
    remove: () => void;
    removeAttribute: (name: string) => void;
  };

  class SvgNode implements Node {
    public removed = false;
    public attributes: Attribute[];

    public constructor(
      public readonly tagName: string,
      public readonly openStart: number,
      public readonly openEnd: number,
      public readonly closeEnd: number,
      attributes: Attribute[],
    ) {
      this.attributes = attributes;
    }

    public remove = () => {
      this.removed = true;
    };

    public removeAttribute = (name: string) => {
      this.attributes = this.attributes.filter((attribute) => attribute.name !== name);
    };
  }

  class SvgDocument {
    public readonly documentElement: SvgNode;
    private readonly nodes: SvgNode[];

    public constructor(private readonly source: string) {
      const nodes: SvgNode[] = [];
      const tagPattern = /<([A-Za-z][\w:.-]*)(\s[^<>]*?)?\s*(\/?)>/g;
      let match: RegExpExecArray | null;
      while ((match = tagPattern.exec(source))) {
        const tagName = match[1];
        const opening = match[0];
        const attributeText = match[2] ?? "";
        const attributes: Attribute[] = [];
        const attributePattern = /([:\w.-]+)\s*=\s*(["'])(.*?)\2/g;
        let attributeMatch: RegExpExecArray | null;
        while ((attributeMatch = attributePattern.exec(attributeText))) {
          attributes.push({ name: attributeMatch[1], value: attributeMatch[3] });
        }
        const openStart = match.index;
        const openEnd = openStart + opening.length;
        const closingPattern = new RegExp(`</${tagName}\\s*>`, "ig");
        closingPattern.lastIndex = openEnd;
        const closingMatch = closingPattern.exec(source);
        nodes.push(new SvgNode(tagName, openStart, openEnd, closingMatch?.index !== undefined ? closingMatch.index + closingMatch[0].length : openEnd, attributes));
      }
      this.nodes = nodes;
      this.documentElement = nodes.find((node) => node.tagName.toLowerCase() === "svg") ?? nodes[0];
    }

    public querySelector = (selector: string): SvgNode | null => (
      selector === "parsererror" ? null : this.nodes.find((node) => node.tagName.toLowerCase() === selector.toLowerCase()) ?? null
    );

    public querySelectorAll = (selector: string): SvgNode[] => {
      if (selector === "*") return this.nodes;
      const tags = selector.split(",").map((tag) => tag.trim().toLowerCase());
      return this.nodes.filter((node) => tags.includes(node.tagName.toLowerCase()));
    };
  }

  class SvgParser {
    public parseFromString(source: string): SvgDocument {
      return new SvgDocument(source);
    }
  }

  class SvgSerializer {
    public serializeToString(root: SvgNode): string {
      const document = (root as SvgNode & { document?: SvgDocument }).document;
      void document;
      return "";
    }
  }

  // The production sanitizer uses the browser DOM. This small deterministic
  // adapter keeps the SSR test focused on source selection and sanitization.
  const parserKey = "DOMParser";
  const serializerKey = "XMLSerializer";
  const globals = globalThis as unknown as Record<string, unknown>;
  const previousParser = globals[parserKey];
  const previousSerializer = globals[serializerKey];
  const documents: SvgDocument[] = [];
  class TestParser extends SvgParser {
    public override parseFromString(source: string): SvgDocument {
      const document = new SvgDocument(source);
      documents.push(document);
      return document;
    }
  }
  class TestSerializer {
    public serializeToString(root: SvgNode): string {
      const document = documents.find((candidate) => candidate.documentElement === root);
      if (!document) return "";
      const edits: Edit[] = [];
      for (const node of document.querySelectorAll("*")) {
        if (node.removed) {
          edits.push({ start: node.openStart, end: node.closeEnd, value: "" });
          continue;
        }
        const attributes = node.attributes.map((attribute) => `${attribute.name}="${attribute.value}"`).join(" ");
        const closing = document["source"].slice(node.openEnd - 2, node.openEnd) === "/>" ? "/>" : ">";
        edits.push({ start: node.openStart, end: node.openEnd, value: `<${node.tagName}${attributes ? ` ${attributes}` : ""}${closing}` });
      }
      let sanitized = document["source"];
      for (const edit of edits.sort((left, right) => right.start - left.start)) {
        sanitized = `${sanitized.slice(0, edit.start)}${edit.value}${sanitized.slice(edit.end)}`;
      }
      return sanitized;
    }
  }
  globals[parserKey] = TestParser;
  globals[serializerKey] = TestSerializer;
  try {
    return render();
  } finally {
    globals[parserKey] = previousParser;
    globals[serializerKey] = previousSerializer;
  }
}

test("write surface renders a Notion-like document canvas", () => {
  const html = renderSurface("write", "# Business mail templates\n\nReusable copy blocks");

  assert.match(html, /data-surface-kind="write"/);
  assert.match(html, /Document title/);
  assert.match(html, /Document body/);
  assert.match(html, /Heading 1/);
  assert.match(html, /Rumi Canvas/);
});

test("slide surface renders project-driven deck slides and assets", () => {
  const html = renderSurface("slide", "# Quarterly review\n\nRoadmap and milestones", {
    slide_project: {
      project_id: "slide:test",
      title: "Quarterly review",
      theme: { name: "Executive clean" },
      assets: [{ id: "chart-1", name: "growth-chart.png", kind: "image", source: "generated:growth-chart" }],
      slides: [
        {
          id: "opening",
          title: "Growth story",
          subtitle: "Quarterly review",
          bullets: ["Revenue grew", "Roadmap is on track"],
          asset_ids: ["chart-1"],
          notes: "Open with the chart.",
        },
        {
          id: "roadmap",
          title: "Roadmap focus",
          bullets: ["Ship mobile polish", "Expand onboarding"],
        },
      ],
      status_cards: [{ label: "Slides", value: "2", status: "editable" }],
      export: { format: "pptx", filename: "quarterly-review.pptx", status: "ready" },
    },
  });

  assert.match(html, /data-surface-kind="slide"/);
  assert.match(html, /Speaker notes/);
  assert.match(html, /Growth story/);
  assert.match(html, /Roadmap focus/);
  assert.match(html, /Revenue grew/);
  assert.match(html, /growth-chart.png/);
  assert.match(html, /Executive clean/);
  assert.match(html, /quarterly-review.pptx/);
  assert.doesNotMatch(html, /Agenda/);
});

test("slide surface fallback links attached files as deck assets", () => {
  const html = renderSurface("slide", "# Field notes\n\nUse the captured visual", {
    attached_files: [
      { id: "capture-1", name: "whiteboard-capture.png", kind: "image", source: "file:whiteboard-capture.png" },
    ],
  });

  assert.match(html, /data-surface-kind="slide"/);
  assert.match(html, /whiteboard-capture.png/);
  assert.match(html, /Assets/);
  assert.match(html, /linked/);
  assert.doesNotMatch(html, /No linked assets/);
});

test("image surface renders a dedicated image editor instead of generic draft", () => {
  const html = renderSurface("image", "Product photo on a clean desk");

  assert.match(html, /data-surface-kind="image"/);
  assert.match(html, /Image prompt/);
  assert.match(html, /Variants/);
  assert.match(html, /Generate/);
  assert.doesNotMatch(html, /Start writing/);
});

test("image assets with only an id and SVG markup use sanitized SVG output", () => {
  const html = withSvgDom(() => renderSurface("image", "SVG logo", {
    image_project: {
      prompt: "SVG logo",
      assets: [
        {
          id: "diagram",
          kind: "image",
          // This mirrors the backend-normalized alias source=id.
          source: "diagram",
          svg: unsafeSvg,
        },
      ],
    },
  }));

  assertSanitizedSvgOutput(html, "diagram");
});

test("image surface renders structured variants and real asset sources", () => {
  const html = renderSurface("image", "Product image brief", {
    image_project: {
      project_id: "image:product",
      prompt: "Product image on a clean desk",
      mode: "edit",
      assets: [
        {
          id: "source-photo",
          name: "source-photo.png",
          kind: "image",
          source: "/assets/source-photo.png",
        },
      ],
      variants: [
        {
          id: "variant-clean",
          label: "Clean crop",
          status: "ready",
          asset_id: "source-photo",
          source: "/assets/variant-clean.webp",
          mime_type: "image/webp",
        },
      ],
    },
  });

  assert.match(html, /Product image on a clean desk/);
  assert.match(html, /Image variant variant-clean/);
  assert.match(html, /Clean crop/);
  assert.match(html, /ready/);
  assert.match(html, /<img[^>]+src="\/assets\/variant-clean\.webp"/);
  assert.doesNotMatch(html, /No structured outputs yet/);
});

test("SVG-only slide and movie assets render sanitized data URI output", () => {
  const htmlBySurface = withSvgDom(() => ({
    slide: renderSurface("slide", "SVG deck", {
      slide_project: {
        assets: [{ id: "slide-diagram", kind: "image", svg: unsafeSvg }],
        slides: [{ title: "SVG slide", asset_ids: ["slide-diagram"] }],
      },
    }),
    movie: renderSurface("movie", "SVG movie", {
      movie_project: {
        assets: [{ id: "movie-frame", kind: "image", duration: 2, svg: unsafeSvg }],
        clips: [{ id: "movie-clip", asset_id: "movie-frame", duration: 2 }],
        captions: [{ id: "caption-1", text: "SVG caption", start: 0, duration: 2 }],
      },
    }),
  }));

  assertSanitizedSvgOutput(htmlBySurface.slide, "slide-diagram");
  assertSanitizedSvgOutput(htmlBySurface.movie, "movie-frame");
  assert.match(htmlBySurface.movie, /SVG caption/);
});

test("slide surface renders element DSL text, media, and styles", () => {
  const html = renderSurface("slide", "Customer update", {
    slide_project: {
      title: "Customer update",
      assets: [
        {
          id: "chart",
          name: "growth-chart.png",
          kind: "image",
          source: "/assets/growth-chart.png",
        },
      ],
      slides: [
        {
          id: "growth",
          title: "Growth story",
          elements: [
            {
              id: "headline",
              type: "text",
              text: "Revenue is growing",
              x: 12,
              y: 8,
              width: 48,
              height: 12,
              style: { color: "#123456", fontSize: 24 },
            },
            {
              id: "chart-element",
              type: "image",
              asset_id: "chart",
              x: 50,
              y: 20,
              width: 42,
              height: 60,
              style: { objectFit: "contain" },
            },
          ],
        },
      ],
    },
  });

  assert.match(html, /Revenue is growing/);
  assert.match(html, /growth-chart\.png/);
  assert.match(html, /left:12%;top:8%;width:48%;height:12%/);
  assert.match(html, /color:#123456/);
  assert.match(html, /font-size:24px/);
  assert.match(html, /left:50%;top:20%;width:42%;height:60%/);
  assert.match(html, /object-fit:contain/);
  assert.doesNotMatch(html, /title-and-bullets/);
});

test("movie surface keeps structured clip, asset, caption, and timeline data dynamic", () => {
  const html = renderSurface("movie", "Launch movie brief", {
    movie_project: {
      project_id: "movie:launch",
      title: "Mimo launch film",
      brief: "Launch movie brief",
      fps: 24,
      timeline: {
        duration: 42.5,
        tracks: ["video", "audio", "captions"],
      },
      assets: [
        {
          id: "hero-frame",
          name: "Hero frame",
          kind: "image",
          source: "/assets/hero-frame.png",
          start: 5,
          duration: 10,
        },
      ],
      clips: [
        {
          id: "hero-clip",
          name: "Open on the product",
          asset_id: "hero-frame",
          track: "video",
          start: 5,
          duration: 7.5,
        },
        {
          id: "voiceover",
          name: "Voiceover",
          asset_id: "voice-track",
          track: "audio",
          start: 12.5,
          duration: 30,
        },
      ],
      captions: [
        {
          id: "caption-open",
          text: "Build faster with Rumi.",
          start: 5.5,
          duration: 2.25,
        },
        {
          id: "caption-close",
          text: "Everything stays editable.",
          start: 38,
          duration: 2,
        },
      ],
    },
  });

  assert.match(html, /Mimo launch film/);
  assert.match(html, /42\.50s · 24 fps/);
  assert.match(html, /Open on the product/);
  assert.match(html, /Voiceover/);
  assert.match(html, /Hero frame/);
  assert.match(html, /Build faster with Rumi\./);
  assert.match(html, /Everything stays editable\./);
  assert.match(html, /2 clips \/ 2 captions/);
  assert.match(html, /Hero frame · image · 5\.00–15\.00s/);
});

test("movie surface renders an editable video project timeline", () => {
  const html = renderSurface("movie", "# Launch movie\n\nTrim intro and add captions");

  assert.match(html, /data-surface-kind="movie"/);
  assert.match(html, /Inspector/);
  assert.match(html, /Timeline/);
  assert.match(html, /Captions/);
  assert.match(html, /Import/);
  assert.match(html, /Save/);
  assert.match(html, /Export/);
  assert.match(html, /Render/);
  assert.match(html, /Selected clip duration/);
});

test("surface save and export actions expose accessible controls", () => {
  const imageHtml = withSvgDom(() => renderSurface("image", "Export an SVG", {
    image_project: {
      assets: [{ id: "logo", kind: "image", svg: unsafeSvg }],
    },
  }));
  const slideHtml = renderSurface("slide", "Export this deck");
  const movieHtml = renderSurface("movie", "Export this movie");

  assert.match(imageHtml, /aria-label="Export selected image"/);
  assert.doesNotMatch(imageHtml, /aria-label="Export selected image"[^>]* disabled=""/);
  assert.match(slideHtml, /aria-label="Save editable deck"/);
  assert.match(slideHtml, /aria-label="Export HTML deck"/);
  assert.match(movieHtml, /aria-label="Save project"/);
  assert.match(movieHtml, /aria-label="Export project"/);
  assert.match(movieHtml, /aria-label="Render movie"[^>]* disabled=""/);
});
