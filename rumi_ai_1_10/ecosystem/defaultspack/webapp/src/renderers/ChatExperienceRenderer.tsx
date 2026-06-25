import { useEffect, useRef } from "react";

import { ChatMessagesRenderer } from "./ChatMessagesRenderer";
import { COMPOSER_EXPERIENCE_STYLES } from "./composerExperienceStyles";
import type { ChatMessagesRendererProps } from "./types";

export function decorateChatExperience(root: HTMLElement) {
  root.querySelectorAll<HTMLElement>(".rumi-activity-loading").forEach((loading) => {
    loading.setAttribute("role", "status");
    loading.setAttribute("aria-live", "polite");
  });

  root.querySelectorAll<HTMLElement>("span.animate-bounce").forEach((dot) => {
    const indicator = dot.parentElement;
    if (!indicator || indicator.querySelectorAll(":scope > span.animate-bounce").length < 3) return;
    const loading = indicator.parentElement;
    if (!loading) return;
    indicator.classList.add("rumi-loading-bars");
    loading.classList.add("rumi-activity-loading");
    loading.setAttribute("role", "status");
    loading.setAttribute("aria-live", "polite");
  });
}

export function ChatExperienceRenderer(props: ChatMessagesRendererProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    const decorate = () => decorateChatExperience(root);
    decorate();
    const observer = new MutationObserver(decorate);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={rootRef} className="rumi-chat-experience" style={{ display: "contents" }}>
      <style data-rumi-chat-experience-styles>{COMPOSER_EXPERIENCE_STYLES}</style>
      <ChatMessagesRenderer {...props} />
    </div>
  );
}
