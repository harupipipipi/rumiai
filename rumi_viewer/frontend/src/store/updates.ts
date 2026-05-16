import type { ApiUpdateInfo } from '@/src/lib/apiTypes';
import type { UpdateInfo } from './types';

export function transformUpdateInfo(update: ApiUpdateInfo): UpdateInfo {
  return {
    target: update.target,
    currentVersion: update.current_version,
    latestVersion: update.latest_version,
    updateAvailable: update.update_available,
    releaseUrl: update.release_url,
    repo: update.repo,
  };
}
