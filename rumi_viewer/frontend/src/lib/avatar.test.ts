import assert from 'node:assert/strict';
import test from 'node:test';

import { AVATAR_OPTIONS, DEFAULT_AVATAR, isBundledAvatar, profileInitial } from './avatar';
import { transformProfile } from './transforms';

test('default viewer avatars are local deterministic values', () => {
  assert.equal(DEFAULT_AVATAR, '');
  assert.ok(AVATAR_OPTIONS.length >= 3);
  for (const avatar of AVATAR_OPTIONS) {
    assert.equal(isBundledAvatar(avatar), true);
    assert.doesNotMatch(avatar, /^https?:\/\//);
  }
});

test('fresh profile transform falls back to initials instead of remote placeholders', () => {
  const profile = transformProfile({
    username: 'Haru',
    language: 'en',
    icon: '',
    occupation: '',
  });

  assert.equal(profile.avatar, DEFAULT_AVATAR);
  assert.equal(profileInitial(profile.username), 'H');
  assert.equal(profileInitial(''), 'U');
});
