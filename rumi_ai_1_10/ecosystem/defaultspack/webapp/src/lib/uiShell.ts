import type { ShellRegion, ShellRenderer, UICatalog } from "./api";

export function shellRegions(catalog: UICatalog | null | undefined): ShellRegion[] {
  return [...(catalog?.shell?.layout?.regions ?? [])]
    .filter((region) => region.enabled !== false)
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));
}

export function hasShellRegion(catalog: UICatalog | null | undefined, regionId: string): boolean {
  return shellRegions(catalog).some((region) => region.id === regionId);
}

export function shellRendererForRegion(
  catalog: UICatalog | null | undefined,
  regionId: string,
): ShellRenderer | null {
  const region = shellRegions(catalog).find((candidate) => candidate.id === regionId);
  if (!region?.renderer) return null;
  return (catalog?.shell?.renderers ?? []).find((renderer) => renderer.id === region.renderer) ?? null;
}
