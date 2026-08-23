import { useEffect, useState } from "react";

function browserLocalStorage(): Storage | null {
  try {
    return typeof globalThis.localStorage === "undefined"
      ? null
      : globalThis.localStorage;
  } catch {
    return null;
  }
}

export function safeLocalStorageGetItem(key: string): string | null {
  const storage = browserLocalStorage();
  if (!storage) return null;
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

export function safeLocalStorageSetItem(key: string, value: string): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function safeLocalStorageRemoveItem(key: string): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function readJsonLocalStorage<T>(key: string, defaultValue: T): T {
  const saved = safeLocalStorageGetItem(key);
  if (saved === null) return defaultValue;
  try {
    return JSON.parse(saved) as T;
  } catch {
    return defaultValue;
  }
}

export function writeJsonLocalStorage<T>(key: string, value: T): boolean {
  try {
    return safeLocalStorageSetItem(key, JSON.stringify(value));
  } catch {
    return false;
  }
}

export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
): [T, (value: T | ((previous: T) => T)) => void] {
  const [value, setValue] = useState<T>(() =>
    readJsonLocalStorage(key, defaultValue),
  );

  useEffect(() => {
    writeJsonLocalStorage(key, value);
  }, [key, value]);

  return [value, setValue];
}
