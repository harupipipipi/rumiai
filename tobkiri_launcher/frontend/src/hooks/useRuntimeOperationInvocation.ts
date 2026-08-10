import {useCallback, useEffect, useRef, useState} from 'react';

import {
  classifyRuntimeSurfaceError,
  invokeRuntimeOperation,
  runtimeSurfaceErrorMessage,
  type RuntimeOperationDescriptor,
  type RuntimeSurfaceEnvelope,
  type RuntimeSurfaceErrorCode,
} from '@/src/lib/runtimeSurface';

export type RuntimeInvocationState = 'idle' | 'running' | 'succeeded' | 'failed';

export interface RuntimeInvocationError {
  code: RuntimeSurfaceErrorCode;
  message: string;
}

export function runtimeOperationIdentity(
  envelope: RuntimeSurfaceEnvelope<unknown>,
  operation: RuntimeOperationDescriptor,
): string {
  return [
    envelope.surface,
    envelope.profile_id,
    envelope.profile_revision,
    envelope.plan_digest,
    envelope.catalog_revision,
    envelope.records.activation_record.digest,
    operation.operation_id,
    operation.contract_id,
    operation.owner_pack_id,
    operation.contribution_id,
    operation.artifact_digest,
    operation.invocation_contribution_id ?? '',
    operation.invocation_catalog_hash ?? '',
  ].join('\u0000');
}

interface ActiveInvocation {
  token: number;
  identity: string;
  envelope: RuntimeSurfaceEnvelope<unknown>;
}

export type RuntimeOperationInvoker = (request: {
  envelope: RuntimeSurfaceEnvelope<unknown>;
  operation: RuntimeOperationDescriptor;
  payload: Record<string, unknown>;
}) => Promise<unknown>;

export function useRuntimeOperationInvocation(
  envelope: RuntimeSurfaceEnvelope<unknown> | null,
  operation: RuntimeOperationDescriptor | null,
  invokeOperation: RuntimeOperationInvoker = invokeRuntimeOperation,
) {
  const [state, setState] = useState<RuntimeInvocationState>('idle');
  const [error, setError] = useState<RuntimeInvocationError | null>(null);
  const nextToken = useRef(0);
  const active = useRef<ActiveInvocation | null>(null);
  const binding = useRef<{envelope: RuntimeSurfaceEnvelope<unknown> | null; identity: string | null} | null>(null);
  const envelopeRef = useRef(envelope);
  const operationRef = useRef(operation);
  envelopeRef.current = envelope;
  operationRef.current = operation;

  const identity = envelope && operation
    ? runtimeOperationIdentity(envelope, operation)
    : null;

  useEffect(() => {
    const changed = binding.current !== null
      && (binding.current.envelope !== envelope || binding.current.identity !== identity);
    binding.current = {envelope, identity};
    const current = active.current;
    if (changed || (current && (current.envelope !== envelope || current.identity !== identity))) {
      active.current = null;
      setState('idle');
      setError(null);
    }
  }, [envelope, identity]);

  useEffect(() => () => {
    active.current = null;
  }, []);

  const invoke = useCallback(async (payload: Record<string, unknown>): Promise<void> => {
    if (!envelope || !operation || active.current) return;
    const invocationToken = nextToken.current + 1;
    nextToken.current = invocationToken;
    const invocationIdentity = runtimeOperationIdentity(envelope, operation);
    active.current = {
      token: invocationToken,
      identity: invocationIdentity,
      envelope,
    };
    setState('running');
    setError(null);

    const isCurrent = (): boolean => {
      const current = active.current;
      return Boolean(
        current
        && current.token === invocationToken
        && current.identity === invocationIdentity
        && current.envelope === envelope
        && envelopeRef.current === envelope
        && operationRef.current !== null
        && runtimeOperationIdentity(envelopeRef.current, operationRef.current) === invocationIdentity,
      );
    };

    try {
      await invokeOperation({envelope, operation, payload});
      if (isCurrent()) {
        setState('succeeded');
      }
    } catch (cause) {
      if (isCurrent()) {
        const code = classifyRuntimeSurfaceError(cause);
        setState('failed');
        setError({code, message: runtimeSurfaceErrorMessage(code)});
      }
    } finally {
      const current = active.current;
      if (current?.token === invocationToken) {
        const completedCurrent = isCurrent();
        active.current = null;
        if (!completedCurrent) {
          setState('idle');
          setError(null);
        }
      }
    }
  }, [envelope, operation, invokeOperation]);

  return {
    state,
    error,
    busy: state === 'running',
    invoke,
  };
}
