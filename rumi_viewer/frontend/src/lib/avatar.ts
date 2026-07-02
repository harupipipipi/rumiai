const avatarSvg = (seed: string, start: string, end: string) =>
  `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='128' height='128' viewBox='0 0 128 128'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23${start}'/%3E%3Cstop offset='100%25' stop-color='%23${end}'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='128' height='128' rx='32' fill='url(%23g)'/%3E%3Ctext x='64' y='76' text-anchor='middle' font-family='Inter,Arial,sans-serif' font-size='34' font-weight='700' fill='white'%3E${seed}%3C/text%3E%3C/svg%3E`;

export const AVATAR_OPTIONS = [
  avatarSvg('RU', '7c3aed', '0f766e'),
  avatarSvg('AI', 'db2777', '2563eb'),
  avatarSvg('RM', 'ea580c', '0891b2'),
  avatarSvg('01', '16a34a', '4f46e5'),
  avatarSvg('ME', '9333ea', 'ca8a04'),
];

export const DEFAULT_AVATAR = '';

export function profileInitial(username?: string | null): string {
  const normalized = (username || '').trim();
  return (normalized.charAt(0) || 'U').toUpperCase();
}

export function isBundledAvatar(value?: string | null): boolean {
  const avatar = value || '';
  return avatar === '' || avatar.startsWith('data:image/svg+xml,');
}
