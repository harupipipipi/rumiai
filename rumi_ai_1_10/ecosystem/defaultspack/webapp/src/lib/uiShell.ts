import type { ShellRegion, ShellRenderer, UICatalog } from "./api";

export function shellRegions(catalog: UICatalog | null | undefined): ShellRegion[] {
  return [...(catalog?.shell?.layout?.regions ?? [])]
    .filter((region) => region.enabled !== false)
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));
}

export function hasShellRegion(catalog: UICatalog | null | undefined, regionId: string): boolean {
  return shellRegions(catalog).some((region) => region.id === regionId);
}

export function shellRegionById(catalog: UICatalog | null | undefined, regionId: string): ShellRegion | null {
  return shellRegions(catalog).find((region) => region.id === regionId) ?? null;
}

export function shellRegionsForSlot(catalog: UICatalog | null | undefined, slot: string): ShellRegion[] {
  return shellRegions(catalog).filter((region) => (region.slot ?? "main") === slot);
}

export function shellRendererById(
  catalog: UICatalog | null | undefined,
  rendererId: string | null | undefined,
): ShellRenderer | null {
  if (!rendererId) return null;
  return (catalog?.shell?.renderers ?? []).find((renderer) => renderer.id === rendererId) ?? null;
}

export function shellRendererForRegion(
  catalog: UICatalog | null | undefined,
  regionId: string,
): ShellRenderer | null {
  const region = shellRegionById(catalog, regionId);
  if (!region?.renderer) return null;
  return shellRendererById(catalog, region.renderer);
}
