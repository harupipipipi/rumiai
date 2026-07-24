export type SetupCompletionSource = 'oauth' | 'setup-pack' | 'existing-account';

export type SetupCompletion = {
  kind:
    | 'account-and-pack'
    | 'pack-only'
    | 'account-verification-error'
    | 'pack-selection-error'
    | 'oauth-error';
  canRedirect: boolean;
  title: string;
  description: string;
  toast: string | null;
};

export function resolveSetupCompletion({
  source,
  accountConnected,
  packSelected,
  oauthError,
}: {
  source: SetupCompletionSource;
  accountConnected: boolean;
  packSelected: boolean;
  oauthError?: string | null;
}): SetupCompletion {
  if (oauthError) {
    return {
      kind: 'oauth-error',
      canRedirect: false,
      title: 'Account connection failed',
      description: `OAuth error: ${oauthError}`,
      toast: null,
    };
  }

  if (!packSelected) {
    return {
      kind: 'pack-selection-error',
      canRedirect: false,
      title: 'Setup pack not ready',
      description: 'Choose and install a setup pack before opening the panel.',
      toast: null,
    };
  }

  if (source === 'oauth' && !accountConnected) {
    return {
      kind: 'account-verification-error',
      canRedirect: false,
      title: 'Account connection not verified',
      description: 'Tobkiri could not verify the account connection. Try connecting again.',
      toast: null,
    };
  }

  if (!accountConnected) {
    return {
      kind: 'pack-only',
      canRedirect: true,
      title: 'Setup pack ready',
      description: 'Your setup pack is installed. Connecting a Tobkiri Account remains optional.',
      toast: 'Setup pack installed successfully!',
    };
  }

  return {
    kind: 'account-and-pack',
    canRedirect: true,
    title: 'Setup complete',
    description: 'Your Tobkiri Account is connected and your setup pack is ready.',
    toast: 'Account connected and setup pack installed!',
  };
}
