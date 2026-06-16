export interface DefaultspackLaunchCandidate {
  id: string;
  name: string;
  version?: string;
}

export interface DefaultspackStartupProfileCandidate {
  base_pack?: string;
  packs?: string[];
  name?: string;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[\s_-]+/g, '');
}

function isDefaultspackId(value: string): boolean {
  const normalized = normalize(value);
  return normalized === 'defaultspack' || normalized === 'defaultspackv2';
}

export function isDefaultspackLaunchPack(pack: DefaultspackLaunchCandidate): boolean {
  const id = normalize(pack.id);
  const name = normalize(pack.name);
  const version = pack.version?.trim() ?? '';

  return (
    id === 'defaultspack' ||
    id === 'defaultspackv2' ||
    name.includes('defaultspackv2') ||
    (name.includes('defaultspack') && version.startsWith('2.'))
  );
}

export function isDefaultspackStartupProfile(profile: DefaultspackStartupProfileCandidate): boolean {
  if (profile.base_pack && isDefaultspackId(profile.base_pack)) return true;
  if (profile.packs?.some((packId) => isDefaultspackId(packId))) return true;
  return normalize(profile.name ?? '').includes('defaultspack');
}
