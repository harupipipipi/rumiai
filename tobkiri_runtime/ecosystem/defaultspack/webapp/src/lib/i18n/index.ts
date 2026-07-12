import { frontendMessages, type FrontendMessageKey } from "./frontend";
import { toolMessages, type ToolMessageKey } from "./tools";
import { frontendLocaleOverrides, toolLocaleOverrides } from "./extraLocales";

export const supportedLocales = ["ja", "en", "zh", "ko", "es", "fr", "de"] as const;
export type Locale = typeof supportedLocales[number];
export type LocaleSetting = Locale | "auto";
export type I18nKey = FrontendMessageKey | ToolMessageKey;

const messages: Record<Locale, Partial<Record<I18nKey, string>>> = {
  ja: { ...frontendMessages.ja, ...toolMessages.ja },
  en: { ...frontendMessages.en, ...toolMessages.en },
  zh: { ...frontendMessages.en, ...toolMessages.en, ...frontendLocaleOverrides.zh, ...toolLocaleOverrides.zh },
  ko: { ...frontendMessages.en, ...toolMessages.en, ...frontendLocaleOverrides.ko, ...toolLocaleOverrides.ko },
  es: { ...frontendMessages.en, ...toolMessages.en, ...frontendLocaleOverrides.es, ...toolLocaleOverrides.es },
  fr: { ...frontendMessages.en, ...toolMessages.en, ...frontendLocaleOverrides.fr, ...toolLocaleOverrides.fr },
  de: { ...frontendMessages.en, ...toolMessages.en, ...frontendLocaleOverrides.de, ...toolLocaleOverrides.de },
};

export function isLocale(value: unknown): value is Locale {
  return supportedLocales.includes(String(value || "").trim().toLowerCase() as Locale);
}

export function isLocaleSetting(value: unknown): value is LocaleSetting {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "auto" || isLocale(normalized);
}

export function normalizeLocale(value: unknown, browserLanguage = globalThis.navigator?.language): Locale {
  const raw = String(value || "ja").trim().toLowerCase();
  const locale = raw === "auto" ? String(browserLanguage || "ja").toLowerCase() : raw;
  if (locale.startsWith("ja")) return "ja";
  if (locale.startsWith("zh") || locale.startsWith("cn")) return "zh";
  if (locale.startsWith("ko") || locale.startsWith("kr")) return "ko";
  if (locale.startsWith("es")) return "es";
  if (locale.startsWith("fr")) return "fr";
  if (locale.startsWith("de")) return "de";
  if (locale.startsWith("en")) return "en";
  return raw === "auto" ? "ja" : "en";
}

export function t(localeValue: unknown, key: I18nKey, values: Record<string, string | number> = {}): string {
  const locale = normalizeLocale(localeValue);
  const template = messages[locale][key] ?? messages.en[key] ?? messages.ja[key] ?? key;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.split(`{${name}}`).join(String(value)),
    template,
  );
}

export { frontendMessages, toolMessages };
