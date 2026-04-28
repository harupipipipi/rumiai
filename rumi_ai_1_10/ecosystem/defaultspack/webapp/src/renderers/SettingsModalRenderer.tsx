import { useState, type ReactElement } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

import { cn } from "../lib/cn";
import type { SettingsSection } from "../lib/api";
import type { SettingsModalRendererProps } from "./types";

function SettingsField({
  sectionId,
  field,
  value,
  onChange,
}: {
  sectionId: string;
  field: SettingsSection["fields"][number];
  value: unknown;
  onChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const [secretDraft, setSecretDraft] = useState("");
  const [secretState, setSecretState] = useState<"idle" | "saved">("idle");
  const commonLabel = <span className="text-sm text-zinc-300">{field.label}</span>;
  const isSecretConfigured = Boolean(value);

  let control: ReactElement;
  switch (field.type) {
    case "secret":
      control = (
        <div className="flex items-center gap-2 min-w-[320px]">
          <input
            type="password"
            autoComplete="off"
            value={secretDraft}
            placeholder={isSecretConfigured ? "Saved" : "Not set"}
            onChange={(event) => {
              setSecretDraft(event.target.value);
              setSecretState("idle");
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || !secretDraft.trim()) return;
              event.preventDefault();
              onChange(sectionId, field.id, secretDraft);
              setSecretDraft("");
              setSecretState("saved");
            }}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
          />
          <button
            type="button"
            disabled={!secretDraft.trim()}
            onClick={() => {
              if (!secretDraft.trim()) return;
              onChange(sectionId, field.id, secretDraft);
              setSecretDraft("");
              setSecretState("saved");
            }}
            className={cn(
              "px-3 py-2 rounded-lg text-xs border transition-colors",
              secretDraft.trim()
                ? "bg-zinc-100 text-zinc-950 border-zinc-100"
                : "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed",
            )}
          >
            Save
          </button>
          <span className="w-14 text-[11px] text-zinc-500">
            {secretState === "saved" || isSecretConfigured ? "Saved" : ""}
          </span>
        </div>
      );
      break;
    case "toggle":
      control = (
        <button
          type="button"
          onClick={() => onChange(sectionId, field.id, !Boolean(value))}
          className={cn("w-10 h-6 rounded-full relative transition-colors", Boolean(value) ? "bg-emerald-500" : "bg-zinc-700")}
        >
          <span className={cn("absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform", Boolean(value) && "translate-x-4")} />
        </button>
      );
      break;
    case "select":
      control = (
        <select
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
        >
          {(field.options ?? []).map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
      );
      break;
    case "number":
      control = (
        <input
          type="number"
          value={Number(value ?? field.default ?? 0)}
          min={field.min}
          max={field.max}
          onChange={(event) => onChange(sectionId, field.id, Number(event.target.value))}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none w-28"
        />
      );
      break;
    case "readonly":
      control = <div className="text-sm text-zinc-200 font-mono">{String(value ?? field.default ?? "")}</div>;
      break;
    case "textarea":
      control = (
        <textarea
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="w-full h-24 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none resize-none"
        />
      );
      break;
    default:
      control = (
        <input
          type="text"
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none min-w-[240px]"
        />
      );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-4">
        {commonLabel}
        {control}
      </div>
      {field.help && <p className="text-[11px] text-zinc-500">{field.help}</p>}
    </div>
  );
}

export function SettingsModalRenderer({
  isOpen,
  catalog,
  health,
  previewsCount,
  settingsSections,
  settingsValues,
  onClose,
  onSettingChange,
}: SettingsModalRendererProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative w-full max-w-4xl bg-[#09090b] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]"
          >
            <div className="px-6 py-4 border-b border-zinc-800 flex justify-between items-center">
              <div>
                <h2 className="text-lg font-medium text-zinc-100">Settings</h2>
                <p className="text-xs text-zinc-500 mt-1">
                  backend registry: {catalog?.extension_points.length ?? 0} extension points, {catalog?.parts?.length ?? 0} parts, {health?.pack ?? "defaultspack"}
                </p>
              </div>
              <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-8">
              {settingsSections.map((section) => (
                <section key={section.id} className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-100">{section.label}</h3>
                    {section.description && <p className="text-xs text-zinc-500 mt-1">{section.description}</p>}
                  </div>
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-4">
                    {section.fields.map((field) => (
                      <SettingsField
                        key={`${section.id}.${field.id}`}
                        sectionId={section.id}
                        field={field}
                        value={
                          field.type === "secret" && field.configured_field
                            ? settingsValues[section.id]?.[field.configured_field]
                            : settingsValues[section.id]?.[field.id] ?? field.default
                        }
                        onChange={onSettingChange}
                      />
                    ))}
                  </div>
                </section>
              ))}

              <section className="space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-zinc-100">Extension Points</h3>
                  <p className="text-xs text-zinc-500 mt-1">frontend は registry と schema だけを知る構成です。</p>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  {(catalog?.extension_points ?? []).map((point) => (
                    <div key={point.id} className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-2">
                      <div className="text-sm text-zinc-200">{point.id}</div>
                      <div className="text-[11px] text-zinc-500 font-mono break-all">{point.path}</div>
                      <p className="text-[11px] text-zinc-400 leading-relaxed">{point.description}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-zinc-100">Parts</h3>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {(catalog?.parts ?? []).map((part) => (
                    <div key={part.id} className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm text-zinc-200">{part.label ?? part.id}</div>
                        <div className="text-[10px] text-zinc-500 font-mono">{part.kind}</div>
                      </div>
                      <div className="text-[11px] text-zinc-500 font-mono break-all">{(part.uses ?? []).join(", ")}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-zinc-100">System Status</h3>
                </div>
                <textarea
                  className="w-full h-32 bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-300 resize-none focus:border-zinc-600 outline-none font-mono"
                  value={JSON.stringify(
                    {
                      health,
                      previewCount: previewsCount,
                      chatRenderers: catalog?.chat_rendering.renderers ?? [],
                      componentBindings: catalog?.component_bindings ?? [],
                      diagnostics: catalog?.diagnostics ?? [],
                    },
                    null,
                    2,
                  )}
                  readOnly
                />
              </section>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
