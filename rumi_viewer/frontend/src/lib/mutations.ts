export type MutationResult =
  | {ok: true}
  | {ok: false; error: string};

/**
 * Run UI success work only after a confirmed store mutation.
 *
 * Failed mutations already surface their error through the store. Keeping the
 * success callback behind this result check prevents contradictory feedback
 * and destructive local state resets.
 */
export async function runConfirmedMutation(
  mutation: () => Promise<MutationResult>,
  onSuccess: () => void,
): Promise<boolean> {
  const result = await mutation();
  if (!result.ok) {
    return false;
  }
  onSuccess();
  return true;
}
