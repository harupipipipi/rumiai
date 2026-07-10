import type { PlacementManifest } from "../lib/placement";
import { resolvePlacementHtmlRendering } from "../lib/placement";

export function PlacementHtmlRenderer({ manifest }: { manifest: PlacementManifest }) {
  const rendering = resolvePlacementHtmlRendering(manifest);
  if (rendering.kind !== "html_iframe") return null;
  return (
    <iframe
      title={manifest.label}
      sandbox={rendering.sandbox}
      referrerPolicy={rendering.referrerPolicy}
      loading="lazy"
      srcDoc={rendering.html}
      className="h-full w-full rounded-lg border border-zinc-800 bg-transparent"
    />
  );
}
