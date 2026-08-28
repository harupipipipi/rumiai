import assert from 'node:assert/strict';
import test from 'node:test';

import {
  copyTextToClipboard,
  nextDuplicateProfileId,
} from './Dashboard';

test('copyTextToClipboard copies the complete runtime error message', async () => {
  let copied = '';
  const success = await copyTextToClipboard('Kernel failed to start', {
    writeText: async (text: string) => {
      copied = text;
    },
  });

  assert.equal(success, true);
  assert.equal(copied, 'Kernel failed to start');
});

test('copyTextToClipboard returns false when the clipboard is unavailable', async () => {
  const success = await copyTextToClipboard('message', undefined);
  assert.equal(success, false);
});

test('duplicate Profile IDs are deterministic and never privilege Defaults', () => {
  assert.equal(nextDuplicateProfileId('work-a', ['defaults', 'work-a']), 'work-a-copy');
  assert.equal(
    nextDuplicateProfileId('work-a', ['work-a-copy', 'work-a-copy-2']),
    'work-a-copy-3',
  );
});
