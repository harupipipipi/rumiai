import { CheckCircle2, Download, Layers3, Sparkles, Upload, Users2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  type AgentFusionDefinition,
  type AgentSelectionRule,
  type AgentStudioManifest,
  type AgentTeamDefinition,
  type Conversation,
  type RegisteredAgentProfile,
} from "../../lib/api";
import { companyResources } from "../../features/company/resources/companyResources";

type AgentStudioSection = "profiles" | "teams" | "fusion" | "selection";

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function listValue(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, items) => items.indexOf(item) === index);
}

function conversationFromActionResult(value: unknown): Conversation | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const conversation = (value as Record<string, unknown>).conversation;
  return conversation && typeof conversation === "object" && !Array.isArray(conversation)
    ? conversation as Conversation
    : null;
}

function matchesSelectionRule(rule: AgentSelectionRule, prompt: string): boolean {
  const text = prompt.trim().toLowerCase();
  if (!text) return false;
  const terms = [...(rule.prompt_contains ?? []), ...(rule.match_terms ?? [])]
    .map((item) => item.toLowerCase());
  return terms.some((item) => item && text.includes(item));
}

export function AgentStudioPanel({
  section,
  conversationId = null,
  onConversationUpdate,
}: {
  section: AgentStudioSection;
  conversationId?: string | null;
  onConversationUpdate?: (conversation: Conversation) => void;
}) {
  const [manifest, setManifest] = useState<AgentStudioManifest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [exportText, setExportText] = useState("");
  const [playgroundInput, setPlaygroundInput] = useState("");
  const [profileDraft, setProfileDraft] = useState({ id: "", display_name: "", base_profile_id: "", aliases: "", description: "" });
  const [teamDraft, setTeamDraft] = useState({ id: "", display_name: "", coordinator_profile_id: "", member_profile_ids: "", description: "" });
  const [fusionDraft, setFusionDraft] = useState({ id: "", display_name: "", synthesis_profile_id: "", participant_profile_ids: "", description: "" });
  const [ruleDraft, setRuleDraft] = useState({ display_name: "", target_type: "profile", target_id: "", match_terms: "" });

  const loadManifest = async () => {
    setBusy(true);
    setError(null);
    try {
      setManifest(await companyResources.getAgentStudio());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Agent Studio load failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadManifest();
  }, []);

  const activeConversationState = useMemo(() => {
    const metadata = conversationId && manifest ? null : null;
    return metadata;
  }, [conversationId, manifest]);
  void activeConversationState;

  const profiles = manifest?.profiles ?? [];
  const teams = manifest?.teams ?? [];
  const fusions = manifest?.fusions ?? [];
  const rules = manifest?.selection_rules ?? [];

  const performAction = async (payload: Record<string, unknown>, successMessage?: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await companyResources.updateAgentStudio(payload);
      const conversation = conversationFromActionResult(result);
      if (conversation && onConversationUpdate) onConversationUpdate(conversation);
      if (payload.action === "export_bundle") {
        setExportText(JSON.stringify(result, null, 2));
      } else {
        await loadManifest();
      }
      if (successMessage) setError(successMessage);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Agent Studio action failed.");
    } finally {
      setBusy(false);
    }
  };

  const activateProfile = (profileId: string) => {
    if (!conversationId) {
      setError("Start a chat first so the Mode Agent can attach to a conversation.");
      return;
    }
    void performAction({ action: "activate_profile", conversation_id: conversationId, profile_id: profileId, surface: "mode_agent" }, `Mode Agent switched to ${profileId}.`);
  };

  const activateTeam = (teamId: string) => {
    if (!conversationId) {
      setError("Start a chat first so the Team Agent can attach to a conversation.");
      return;
    }
    void performAction({ action: "activate_team", conversation_id: conversationId, team_id: teamId }, `Team Agent switched to ${teamId}.`);
  };

  const activateFusion = (fusionId: string) => {
    if (!conversationId) {
      setError("Start a chat first so the Fusion Agent can attach to a conversation.");
      return;
    }
    void performAction({ action: "activate_fusion", conversation_id: conversationId, fusion_id: fusionId }, `Fusion Agent switched to ${fusionId}.`);
  };

  const matchedRule = useMemo(() => rules.find((rule) => matchesSelectionRule(rule, playgroundInput)) ?? null, [playgroundInput, rules]);

  const profileSection = (
    <div className="space-y-3 p-2">
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-zinc-200">
          <Layers3 size={14} />
          Registered Profiles
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {profiles.map((profile: RegisteredAgentProfile) => (
            <div key={profile.id} className="rounded-lg border border-zinc-800 bg-black/20 p-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium text-zinc-100">{profile.display_name || profile.id}</div>
                  <div className="truncate font-mono text-[10px] text-zinc-500">{profile.id}</div>
                </div>
                <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[9px] text-zinc-500">{profile.source_type}</span>
              </div>
              <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-zinc-400">{profile.description || "No description."}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(profile.command_shortcuts ?? []).map((shortcut) => (
                  <span key={shortcut} className="rounded border border-zinc-800 bg-zinc-900/60 px-1 py-0.5 text-[9px] text-zinc-500">/{shortcut}</span>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="truncate text-[10px] text-zinc-500">{profile.runtime_profile_id || profile.base_profile_id || "runtime pending"}</span>
                <button
                  type="button"
                  disabled={busy || !conversationId}
                  onClick={() => activateProfile(profile.id)}
                  className="rounded-md bg-zinc-100 px-2.5 py-1 text-[10px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
                >
                  Mode Agent
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 text-[12px] font-semibold text-zinc-200">Create Custom Profile</div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={profileDraft.id} onChange={(event) => setProfileDraft((current) => ({ ...current, id: event.target.value }))} placeholder="id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={profileDraft.display_name} onChange={(event) => setProfileDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="display name" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={profileDraft.base_profile_id} onChange={(event) => setProfileDraft((current) => ({ ...current, base_profile_id: event.target.value }))} placeholder="base runtime profile id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={profileDraft.aliases} onChange={(event) => setProfileDraft((current) => ({ ...current, aliases: event.target.value }))} placeholder="aliases, comma separated" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <textarea value={profileDraft.description} onChange={(event) => setProfileDraft((current) => ({ ...current, description: event.target.value }))} placeholder="description" className="md:col-span-2 min-h-20 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={busy || !textValue(profileDraft.id)}
            onClick={() => void performAction({
              action: "upsert_profile",
              profile: {
                ...profileDraft,
                aliases: listValue(profileDraft.aliases),
              },
            }, `Saved profile ${profileDraft.id}.`)}
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
          >
            Save Profile
          </button>
        </div>
      </div>
    </div>
  );

  const teamSection = (
    <div className="space-y-3 p-2">
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-zinc-200">
          <Users2 size={14} />
          Team Agents
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {teams.map((team: AgentTeamDefinition) => (
            <div key={team.id} className="rounded-lg border border-zinc-800 bg-black/20 p-2">
              <div className="truncate text-[12px] font-medium text-zinc-100">{team.display_name || team.id}</div>
              <div className="truncate font-mono text-[10px] text-zinc-500">{team.id}</div>
              <p className="mt-2 text-[11px] leading-relaxed text-zinc-400">{team.description || "No description."}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(team.member_profile_ids ?? []).map((memberId) => (
                  <span key={memberId} className="rounded border border-zinc-800 bg-zinc-900/60 px-1 py-0.5 text-[9px] text-zinc-500">{memberId}</span>
                ))}
              </div>
              <div className="mt-3 flex justify-end">
                <button type="button" disabled={busy || !conversationId} onClick={() => activateTeam(team.id)} className="rounded-md bg-zinc-100 px-2.5 py-1 text-[10px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40">
                  Team Agent
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 text-[12px] font-semibold text-zinc-200">Create Team</div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={teamDraft.id} onChange={(event) => setTeamDraft((current) => ({ ...current, id: event.target.value }))} placeholder="id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={teamDraft.display_name} onChange={(event) => setTeamDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="display name" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={teamDraft.coordinator_profile_id} onChange={(event) => setTeamDraft((current) => ({ ...current, coordinator_profile_id: event.target.value }))} placeholder="coordinator profile id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={teamDraft.member_profile_ids} onChange={(event) => setTeamDraft((current) => ({ ...current, member_profile_ids: event.target.value }))} placeholder="member profile ids" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <textarea value={teamDraft.description} onChange={(event) => setTeamDraft((current) => ({ ...current, description: event.target.value }))} placeholder="description" className="md:col-span-2 min-h-20 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={busy || !textValue(teamDraft.id)}
            onClick={() => void performAction({
              action: "upsert_team",
              team: {
                ...teamDraft,
                member_profile_ids: listValue(teamDraft.member_profile_ids),
              },
            }, `Saved team ${teamDraft.id}.`)}
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
          >
            Save Team
          </button>
        </div>
      </div>
    </div>
  );

  const fusionSection = (
    <div className="space-y-3 p-2">
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-zinc-200">
          <Sparkles size={14} />
          Fusion Agents
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {fusions.map((fusion: AgentFusionDefinition) => (
            <div key={fusion.id} className="rounded-lg border border-zinc-800 bg-black/20 p-2">
              <div className="truncate text-[12px] font-medium text-zinc-100">{fusion.display_name || fusion.id}</div>
              <div className="truncate font-mono text-[10px] text-zinc-500">{fusion.id}</div>
              <p className="mt-2 text-[11px] leading-relaxed text-zinc-400">{fusion.description || "No description."}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(fusion.participant_profile_ids ?? []).map((memberId) => (
                  <span key={memberId} className="rounded border border-zinc-800 bg-zinc-900/60 px-1 py-0.5 text-[9px] text-zinc-500">{memberId}</span>
                ))}
              </div>
              <div className="mt-3 flex justify-end">
                <button type="button" disabled={busy || !conversationId} onClick={() => activateFusion(fusion.id)} className="rounded-md bg-zinc-100 px-2.5 py-1 text-[10px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40">
                  Fusion Agent
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 text-[12px] font-semibold text-zinc-200">Create Fusion</div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={fusionDraft.id} onChange={(event) => setFusionDraft((current) => ({ ...current, id: event.target.value }))} placeholder="id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={fusionDraft.display_name} onChange={(event) => setFusionDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="display name" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={fusionDraft.synthesis_profile_id} onChange={(event) => setFusionDraft((current) => ({ ...current, synthesis_profile_id: event.target.value }))} placeholder="synthesis profile id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={fusionDraft.participant_profile_ids} onChange={(event) => setFusionDraft((current) => ({ ...current, participant_profile_ids: event.target.value }))} placeholder="participant profile ids" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <textarea value={fusionDraft.description} onChange={(event) => setFusionDraft((current) => ({ ...current, description: event.target.value }))} placeholder="description" className="md:col-span-2 min-h-20 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={busy || !textValue(fusionDraft.id)}
            onClick={() => void performAction({
              action: "upsert_fusion",
              fusion: {
                ...fusionDraft,
                participant_profile_ids: listValue(fusionDraft.participant_profile_ids),
              },
            }, `Saved fusion ${fusionDraft.id}.`)}
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
          >
            Save Fusion
          </button>
        </div>
      </div>
    </div>
  );

  const selectionSection = (
    <div className="space-y-3 p-2">
      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 text-[12px] font-semibold text-zinc-200">Selection Playground</div>
        <textarea value={playgroundInput} onChange={(event) => setPlaygroundInput(event.target.value)} placeholder="Type a prompt to see which selection rule matches." className="min-h-24 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        <div className="mt-2 rounded-lg border border-zinc-800 bg-black/20 p-2 text-[11px] text-zinc-400">
          {matchedRule ? (
            <>
              <div className="font-medium text-zinc-100">{matchedRule.display_name || matchedRule.id}</div>
              <div className="mt-1">target: {matchedRule.target_type} / {matchedRule.target_id}</div>
              <div className="mt-1">reason: {matchedRule.reason || "No reason."}</div>
            </>
          ) : (
            "No matching selection rule."
          )}
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 text-[12px] font-semibold text-zinc-200">Selection Rules</div>
        <div className="space-y-2">
          {rules.map((rule) => (
            <div key={rule.id} className="rounded-lg border border-zinc-800 bg-black/20 p-2 text-[11px]">
              <div className="font-medium text-zinc-100">{rule.display_name || rule.id}</div>
              <div className="mt-1 text-zinc-500">{rule.target_type} / {rule.target_id}</div>
              <div className="mt-1 text-zinc-400">{(rule.prompt_contains ?? rule.match_terms ?? []).join(", ") || "No terms."}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <input value={ruleDraft.display_name} onChange={(event) => setRuleDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="rule name" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <select value={ruleDraft.target_type} onChange={(event) => setRuleDraft((current) => ({ ...current, target_type: event.target.value }))} className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600">
            <option value="profile">profile</option>
            <option value="team">team</option>
            <option value="fusion">fusion</option>
          </select>
          <input value={ruleDraft.target_id} onChange={(event) => setRuleDraft((current) => ({ ...current, target_id: event.target.value }))} placeholder="target id" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
          <input value={ruleDraft.match_terms} onChange={(event) => setRuleDraft((current) => ({ ...current, match_terms: event.target.value }))} placeholder="match terms" className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={busy || !textValue(ruleDraft.target_id)}
            onClick={() => void performAction({
              action: "set_selection_rules",
              selection_rules: [
                ...rules,
                {
                  display_name: ruleDraft.display_name,
                  target_type: ruleDraft.target_type,
                  target_id: ruleDraft.target_id,
                  match_terms: listValue(ruleDraft.match_terms),
                  prompt_contains: listValue(ruleDraft.match_terms),
                },
              ],
            }, "Saved selection rule.")}
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
          >
            Save Rule
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/50 p-3">
        <div className="mb-2 flex items-center justify-between gap-2 text-[12px] font-semibold text-zinc-200">
          <span>Import / Export</span>
          <div className="flex items-center gap-1">
            <button type="button" disabled={busy} onClick={() => void performAction({ action: "export_bundle" })} className="inline-flex items-center gap-1 rounded-md border border-zinc-800 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-900 disabled:opacity-40"><Download size={11} />Export</button>
            {conversationId && (
              <button type="button" disabled={busy} onClick={() => void performAction({ action: "mark_review_gate", conversation_id: conversationId, approved: true, approved_by: "workroom" }, "Review gate passed for this conversation.")} className="inline-flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-200 hover:bg-emerald-500/15 disabled:opacity-40"><CheckCircle2 size={11} />Pass Gate</button>
            )}
          </div>
        </div>
        <textarea value={importText} onChange={(event) => setImportText(event.target.value)} placeholder="Paste Agent Studio JSON bundle here." className="min-h-28 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-zinc-600" />
        <div className="mt-2 flex items-center justify-between gap-2">
          <button
            type="button"
            disabled={busy || !textValue(importText)}
            onClick={() => {
              try {
                const bundle = JSON.parse(importText);
                void performAction({ action: "import_bundle", bundle, merge: true }, "Imported Agent Studio bundle.");
              } catch {
                setError("Import JSON is invalid.");
              }
            }}
            className="inline-flex items-center gap-1 rounded-md bg-zinc-100 px-3 py-1.5 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
          >
            <Upload size={12} />
            Import Merge
          </button>
          <span className="text-[10px] text-zinc-600">Export JSON appears below after running Export.</span>
        </div>
        {exportText && (
          <textarea value={exportText} readOnly className="mt-2 min-h-28 w-full rounded-md border border-zinc-800 bg-black/25 px-2 py-1.5 text-[10px] text-zinc-400 outline-none" />
        )}
      </div>
    </div>
  );

  return (
    <section className="min-h-0">
      {error && (
        <div className="mx-2 mt-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
          {error}
        </div>
      )}
      {section === "profiles" ? profileSection : section === "teams" ? teamSection : section === "fusion" ? fusionSection : selectionSection}
    </section>
  );
}
