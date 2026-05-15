import { frontendMessages, type FrontendMessageKey } from "./frontend";
import { toolMessages, type ToolMessageKey } from "./tools";

export type Locale = "ja" | "en";
export type LocaleSetting = Locale | "auto";
export type I18nKey = FrontendMessageKey | ToolMessageKey;

const messages: Record<Locale, Record<I18nKey, string>> = {
  ja: { ...frontendMessages.ja, ...toolMessages.ja },
  en: { ...frontendMessages.en, ...toolMessages.en },
};

export function normalizeLocale(value: unknown, browserLanguage = globalThis.navigator?.language): Locale {
  const raw = String(value || "ja").trim().toLowerCase();
  const locale = raw === "auto" ? String(browserLanguage || "ja").toLowerCase() : raw;
  return locale.startsWith("en") ? "en" : "ja";
}

export function t(localeValue: unknown, key: I18nKey, values: Record<string, string | number> = {}): string {
  const locale = normalizeLocale(localeValue);
  const template = messages[locale][key] ?? messages.ja[key] ?? key;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.split(`{${name}}`).join(String(value)),
    template,
  );
}

export { frontendMessages, toolMessages };
