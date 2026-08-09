import {useEffect, useState, type FormEvent} from 'react';

import {Button} from '@/src/components/ui/Button';
import {Input} from '@/src/components/ui/Input';
import {Badge} from '@/src/components/ui/Badge';
import type {RuntimeJsonSchema, RuntimeOperationDescriptor} from '@/src/lib/runtimeSurface';

type InputValue = string | number | boolean | null | Record<string, unknown> | unknown[];

function initialValue(schema: RuntimeJsonSchema): InputValue {
  if (schema.default !== undefined) return schema.default as InputValue;
  if (schema.type === 'boolean') return false;
  return '';
}

function displayValue(value: InputValue, schema: RuntimeJsonSchema): string {
  if (schema.type === 'object' || schema.type === 'array') {
    if (typeof value === 'string') return value;
    return JSON.stringify(value ?? '', null, 2);
  }
  return String(value ?? '');
}

function isEmpty(value: InputValue | undefined): boolean {
  return value === undefined || value === null || (typeof value === 'string' && value.trim() === '');
}

export function OperationInputForm({
  operation,
  busy,
  onInvoke,
}: {
  operation: RuntimeOperationDescriptor;
  busy: boolean;
  onInvoke: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const properties = Object.entries(operation.input_schema?.properties ?? {});
  const required = new Set(operation.input_schema?.required ?? []);
  const [values, setValues] = useState<Record<string, InputValue>>({});
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setValues(Object.fromEntries(properties.map(([name, schema]) => [name, initialValue(schema)])));
    setValidationError(null);
  }, [operation.operation_id]);

  const updateValue = (name: string, value: InputValue) => {
    setValues((current) => ({...current, [name]: value}));
    setValidationError(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    for (const name of required) {
      if (isEmpty(values[name])) {
        setValidationError(`Required input “${name}” is missing.`);
        return;
      }
    }

    const payload: Record<string, unknown> = {};
    for (const [name, schema] of properties) {
      const value = values[name];
      if (schema.type === 'number' || schema.type === 'integer') {
        const parsed = typeof value === 'number' ? value : Number(value);
        if (!Number.isFinite(parsed)) {
          setValidationError(`Input “${name}” must be a number.`);
          return;
        }
        payload[name] = parsed;
      } else if (schema.type === 'object' || schema.type === 'array') {
        if (typeof value !== 'string') {
          payload[name] = value;
          continue;
        }
        try {
          payload[name] = JSON.parse(value) as unknown;
        } catch {
          setValidationError(`Input “${name}” must contain valid JSON.`);
          return;
        }
      } else {
        payload[name] = value;
      }
    }
    setValidationError(null);
    await onInvoke(payload);
  };

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">Schema-driven input</Badge>
        {required.size > 0 ? <span className="text-xs text-text-muted">Required fields are marked.</span> : null}
      </div>
      {properties.length === 0 ? (
        <p className="text-sm text-text-muted">This operation declares no input properties.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {properties.map(([name, schema]) => {
            const value = values[name] ?? '';
            const label = schema.title || name;
            const helper = schema.description || (required.has(name) ? 'Required' : undefined);
            if (schema.enum && schema.enum.length > 0) {
              return (
                <label key={name} className="flex min-w-0 flex-col gap-1.5 text-sm font-medium text-text-main">
                  <span>{label}{required.has(name) ? <span className="ml-1 text-destructive">*</span> : null}</span>
                  <select
                    className="min-h-11 w-full rounded-lg border border-border bg-bg-main px-3 py-2 text-sm text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                    value={String(value)}
                    onChange={(event) => updateValue(name, event.target.value)}
                    aria-label={label}
                  >
                    {schema.enum.map((option) => (
                      <option key={String(option)} value={String(option)}>{String(option)}</option>
                    ))}
                  </select>
                  {helper ? <span className="text-xs font-normal text-text-muted">{helper}</span> : null}
                </label>
              );
            }
            if (schema.type === 'boolean') {
              return (
                <label key={name} className="flex min-h-11 items-center gap-3 rounded-lg border border-border bg-bg-main px-3 py-2 text-sm font-medium text-text-main">
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(event) => updateValue(name, event.target.checked)}
                    aria-label={label}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  <span>{label}{required.has(name) ? <span className="ml-1 text-destructive">*</span> : null}</span>
                  {helper ? <span className="ml-auto text-xs font-normal text-text-muted">{helper}</span> : null}
                </label>
              );
            }
            if (schema.type === 'object' || schema.type === 'array') {
              return (
                <label key={name} className="flex min-w-0 flex-col gap-1.5 text-sm font-medium text-text-main sm:col-span-2">
                  <span>{label}{required.has(name) ? <span className="ml-1 text-destructive">*</span> : null}</span>
                  <textarea
                    className="min-h-28 w-full rounded-lg border border-border bg-bg-main px-3 py-2 font-mono text-xs text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                    value={displayValue(value, schema)}
                    onChange={(event) => updateValue(name, event.target.value)}
                    aria-label={label}
                  />
                  {helper ? <span className="text-xs font-normal text-text-muted">{helper}</span> : null}
                </label>
              );
            }
            return (
              <Input
                key={name}
                id={`operation-${operation.operation_id}-${name}`}
                label={label}
                helperText={helper}
                required={required.has(name)}
                type={schema.type === 'number' || schema.type === 'integer' ? 'number' : 'text'}
                value={displayValue(value, schema)}
                onChange={(event) => updateValue(name, event.target.value)}
              />
            );
          })}
        </div>
      )}
      {validationError ? <p className="text-sm text-destructive" role="alert">{validationError}</p> : null}
      <Button type="submit" className="min-h-11 self-start" loading={busy} disabled={!operation.invokable}>
        Invoke declared operation
      </Button>
    </form>
  );
}
