import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import { ComposerRenderer } from "./ComposerRenderer";
import { composerExperiencePlaceholder, composerTextareaMetrics, type ComposerExperienceVariant } from "./composerExperience";
import { COMPOSER_EXPERIENCE_STYLES } from "./composerExperienceStyles";
import type { ComposerRendererProps } from "./types";

const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

function addClass(element: Element | null | undefined, className: string) {
  element?.classList.add(className);
}

export function decorateComposerRoot(root: HTMLElement) {
  const frame = root.querySelector<HTMLElement>(".rumi-composer-frame");
  const textarea = root.querySelector<HTMLTextAreaElement>("textarea.rumi-composer-textarea");
  const toolbar = root.querySelector<HTMLElement>(".rumi-composer-submit-area")?.parentElement;
  const workspacePicker = root.querySelector<HTMLElement>(".rumi-workspace-picker");
  const contextRail = workspacePicker?.parentElement;

  addClass(frame, "rumi-composer-surface");
  const editorHost = textarea?.parentElement === frame ? textarea : textarea?.parentElement;
  addClass(editorHost, "rumi-composer-editor");
  addClass(root.querySelector(".rumi-composer-main-panel"), "rumi-composer-editor-row");
  addClass(toolbar, "rumi-composer-toolbar");
  addClass(contextRail, "rumi-composer-context-rail");

  contextRail?.querySelectorAll<HTMLElement>(":scope > span").forEach((item) => {
    item.classList.add("rumi-composer-context-field");
  });

  root.querySelectorAll<HTMLElement>(
    "[data-testid='composer-at-mention-candidates'], [role='listbox'], .rumi-layer-command-palette, .rumi-layer-modal",
  ).forEach((popover) => popover.classList.add("rumi-composer-popover"));

  frame?.querySelectorAll<HTMLElement>(":scope > .absolute.bottom-full").forEach((popover) => {
    popover.classList.add("rumi-composer-popover", "rumi-composer-command-popover");
  });
}

function fitTextarea(
  textarea: HTMLTextAreaElement,
  variant: ComposerExperienceVariant,
  placeholder: string,
) {
  const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
  const { minHeight, maxHeight } = composerTextareaMetrics(variant, viewportHeight);
  const previousScrollTop = textarea.scrollTop;
  const wasAtBottom = textarea.scrollHeight - textarea.clientHeight - previousScrollTop < 8;

  textarea.rows = 1;
  textarea.placeholder = placeholder;
  textarea.setAttribute("aria-label", textarea.getAttribute("aria-label") || "メッセージ入力");
  textarea.dataset.composerExperienceEditor = variant;
  textarea.style.minHeight = `${minHeight}px`;
  textarea.style.maxHeight = `${maxHeight}px`;
  textarea.style.height = "0px";

  const contentHeight = Math.max(minHeight, textarea.scrollHeight);
  const nextHeight = Math.min(contentHeight, maxHeight);
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = contentHeight > maxHeight ? "auto" : "hidden";
  textarea.style.scrollbarGutter = contentHeight > maxHeight ? "stable" : "auto";

  if (contentHeight > maxHeight) {
    textarea.scrollTop = wasAtBottom ? textarea.scrollHeight : previousScrollTop;
  } else {
    textarea.scrollTop = 0;
  }
}

export function ComposerExperienceRenderer(props: ComposerRendererProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const variant: ComposerExperienceVariant = props.isNewConversation ? "home" : "conversation";
  const placeholder = composerExperiencePlaceholder(props);

  const synchronizeComposer = useCallback(() => {
    const root = rootRef.current;
    if (!root || typeof window === "undefined") return;
    decorateComposerRoot(root);
    const textarea = root.querySelector<HTMLTextAreaElement>("textarea.rumi-composer-textarea");
    if (textarea) fitTextarea(textarea, variant, placeholder);
  }, [placeholder, variant]);

  useIsomorphicLayoutEffect(() => {
    synchronizeComposer();
  }, [props.input, props.mode, props.isGenerating, props.isNewConversation, synchronizeComposer]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof window === "undefined") return undefined;

    let animationFrame = 0;
    const scheduleSynchronize = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(synchronizeComposer);
    };

    const textarea = root.querySelector<HTMLTextAreaElement>("textarea.rumi-composer-textarea");
    textarea?.addEventListener("input", scheduleSynchronize);
    window.addEventListener("resize", scheduleSynchronize);
    window.visualViewport?.addEventListener("resize", scheduleSynchronize);

    const observer = new MutationObserver(scheduleSynchronize);
    observer.observe(root, { childList: true, subtree: true });

    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(scheduleSynchronize);
    const shell = root.querySelector<HTMLElement>(".rumi-composer-shell");
    if (shell) resizeObserver?.observe(shell);

    scheduleSynchronize();
    return () => {
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
      resizeObserver?.disconnect();
      textarea?.removeEventListener("input", scheduleSynchronize);
      window.removeEventListener("resize", scheduleSynchronize);
      window.visualViewport?.removeEventListener("resize", scheduleSynchronize);
    };
  }, [synchronizeComposer]);

  return (
    <div
      ref={rootRef}
      className="rumi-composer-experience"
      data-composer-variant={variant}
      data-composer-mode={props.mode ?? "chat"}
    >
      <style data-rumi-composer-experience-styles>{COMPOSER_EXPERIENCE_STYLES}</style>
      <ComposerRenderer {...props} placeholder={placeholder} />
    </div>
  );
}
