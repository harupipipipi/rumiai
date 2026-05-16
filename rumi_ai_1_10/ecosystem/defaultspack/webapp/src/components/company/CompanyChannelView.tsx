import { MessageSquare, Send } from "lucide-react";
import { useMemo, useState } from "react";

import type { CompanyChannel, CompanyMessage } from "../../lib/api";

export function CompanyChannelView({
  channels,
  messages,
  activeChannelId,
  busy = false,
  onChannelChange,
  onSendMessage,
}: {
  channels: CompanyChannel[];
  messages: CompanyMessage[];
  activeChannelId?: string | null;
  busy?: boolean;
  onChannelChange?: (channelId: string) => void;
  onSendMessage?: (content: string, channelId: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const selectedChannelId = activeChannelId || channels[0]?.id || "ops-company";
  const visibleMessages = useMemo(
    () => messages.filter((message) => !selectedChannelId || message.channel_id === selectedChannelId),
    [messages, selectedChannelId],
  );

  return (
    <section className="space-y-2 p-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Channels</h4>
        <select
          value={selectedChannelId}
          onChange={(event) => onChannelChange?.(event.target.value)}
          className="max-w-[150px] bg-transparent text-[11px] text-zinc-300 outline-none"
        >
          {channels.map((channel) => (
            <option key={channel.id} value={channel.id} className="bg-zinc-900">
              {channel.name || channel.id}
            </option>
          ))}
          {channels.length === 0 && <option value="ops-company">ops-company</option>}
        </select>
      </div>

      <div className="max-h-48 space-y-1 overflow-y-auto">
        {visibleMessages.slice(-20).map((message) => (
          <div key={message.id} className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
            <div className="mb-0.5 flex items-center gap-1.5 text-[10px] text-zinc-500">
              <MessageSquare size={10} />
              <span className="truncate">{message.sender_id}</span>
            </div>
            <p className="line-clamp-3 whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-300">{message.content}</p>
          </div>
        ))}
        {visibleMessages.length === 0 && (
          <div className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-2 text-[11px] text-zinc-500">
            No messages in this channel.
          </div>
        )}
      </div>

      {onSendMessage && (
        <form
          className="flex items-center gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            const content = draft.trim();
            if (!content) return;
            onSendMessage(content, selectedChannelId);
            setDraft("");
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={busy}
            placeholder="@pm handoff note"
            className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="flex h-8 w-8 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-30"
            title="Send company message"
          >
            <Send size={13} />
          </button>
        </form>
      )}
    </section>
  );
}
