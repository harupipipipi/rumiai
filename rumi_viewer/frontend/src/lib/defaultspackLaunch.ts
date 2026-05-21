export interface DefaultspackLaunchCandidate {
  id: string;
  name: string;
  version?: string;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[\s_-]+/g, '');
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
