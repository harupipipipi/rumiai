export const COMPOSER_EXPERIENCE_STYLES = String.raw`
.rumi-composer-experience {
  display: contents;
  --rumi-composer-bg: rgba(27, 27, 29, 0.97);
  --rumi-composer-bg-strong: rgba(31, 31, 34, 0.99);
  --rumi-composer-border: rgba(255, 255, 255, 0.105);
  --rumi-composer-border-focus: rgba(255, 255, 255, 0.24);
  --rumi-composer-divider: rgba(255, 255, 255, 0.075);
  --rumi-composer-muted: rgba(161, 161, 170, 0.78);
  --rumi-composer-ease: cubic-bezier(0.2, 0.78, 0.2, 1);
}

.rumi-new-chat-stage .rumi-greeting {
  display: none !important;
}

.rumi-new-chat-stage {
  padding-bottom: clamp(5rem, 13vh, 9rem) !important;
  animation: rumi-composer-stage-in 360ms var(--rumi-composer-ease) both !important;
}

.rumi-new-chat-stage > div {
  width: 100%;
}

.rumi-composer-experience[data-composer-variant="home"] .rumi-composer-shell,
.rumi-composer-experience[data-composer-variant="home"] .rumi-composer-shell-new {
  width: min(760px, calc(100% - 24px)) !important;
  max-width: 760px !important;
}

.rumi-composer-experience[data-composer-variant="conversation"] .rumi-composer-shell {
  width: min(760px, calc(100% - 20px)) !important;
  max-width: 760px !important;
}

.rumi-composer-experience[data-composer-variant="conversation"] > div {
  padding-inline: 12px !important;
  padding-bottom: 14px !important;
  padding-top: 8px !important;
  background: linear-gradient(180deg, rgba(9, 9, 11, 0), #09090b 38%) !important;
}

.rumi-composer-surface {
  position: relative;
  isolation: isolate;
  overflow: visible !important;
  color-scheme: dark;
  border: 1px solid var(--rumi-composer-border) !important;
  border-radius: 24px !important;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0) 34%),
    var(--rumi-composer-bg) !important;
  box-shadow:
    0 22px 64px rgba(0, 0, 0, 0.36),
    0 3px 12px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.045) !important;
  transform: translateZ(0) !important;
  transition:
    border-color 170ms ease,
    background-color 170ms ease,
    box-shadow 210ms ease,
    transform 210ms var(--rumi-composer-ease) !important;
}

.rumi-composer-experience[data-composer-variant="home"] .rumi-composer-surface {
  padding: 8px 10px 10px;
  animation: rumi-composer-surface-in 420ms 35ms var(--rumi-composer-ease) both !important;
}

.rumi-composer-experience[data-composer-variant="conversation"] .rumi-composer-surface {
  animation: rumi-composer-dock-in 260ms var(--rumi-composer-ease) both;
}

.rumi-composer-surface:focus-within {
  border-color: var(--rumi-composer-border-focus) !important;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0) 36%),
    var(--rumi-composer-bg-strong) !important;
  box-shadow:
    0 28px 78px rgba(0, 0, 0, 0.44),
    0 4px 16px rgba(0, 0, 0, 0.22),
    0 0 0 1px rgba(255, 255, 255, 0.025),
    inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
  transform: translateY(-1px) !important;
}

.rumi-new-chat-stage.is-launching .rumi-composer-surface {
  pointer-events: none;
  animation: rumi-composer-submit-away 240ms var(--rumi-composer-ease) both !important;
}

.rumi-composer-editor-row {
  min-height: 62px !important;
  grid-template-columns: 2rem minmax(0, 1fr) auto !important;
  align-items: end !important;
  column-gap: 10px !important;
  border: 0 !important;
  border-radius: 18px !important;
  background: transparent !important;
  padding: 7px 5px 8px !important;
  box-shadow: none !important;
}

.rumi-composer-new:focus-within .rumi-composer-editor-row,
.rumi-composer-new:focus-within .rumi-composer-main-panel {
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
}

.rumi-composer-editor {
  min-width: 0;
}

textarea.rumi-composer-textarea {
  box-sizing: border-box;
  width: 100%;
  resize: none !important;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgba(113, 113, 122, 0.48) transparent;
  transition: height 120ms var(--rumi-composer-ease), color 120ms ease;
}

textarea.rumi-composer-textarea::-webkit-scrollbar {
  width: 7px;
}

textarea.rumi-composer-textarea::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(113, 113, 122, 0.48);
  background-clip: padding-box;
}

.rumi-composer-experience[data-composer-variant="home"] textarea.rumi-composer-textarea,
.rumi-composer-experience[data-composer-variant="home"] .rumi-composer-mention-overlay {
  padding: 13px 1px 9px !important;
  font-size: 16px !important;
  font-weight: 400 !important;
  line-height: 24px !important;
  letter-spacing: -0.006em;
}

.rumi-composer-experience[data-composer-variant="home"] textarea.rumi-composer-textarea::placeholder {
  color: rgba(161, 161, 170, 0.66) !important;
  font-weight: 400;
}

.rumi-composer-experience[data-composer-variant="conversation"] textarea.rumi-composer-textarea {
  display: block;
  padding: 15px 18px 8px !important;
  font-size: 15px !important;
  font-weight: 400;
  line-height: 22px;
  color: rgb(244, 244, 245);
}

.rumi-composer-experience[data-composer-variant="conversation"] textarea.rumi-composer-textarea::placeholder {
  color: rgba(161, 161, 170, 0.62) !important;
}

.rumi-composer-mention-overlay {
  overflow-y: hidden !important;
}

.rumi-composer-fake-caret {
  width: 1px !important;
  background: rgba(250, 250, 250, 0.88) !important;
  animation: rumi-composer-caret 1.05s step-end infinite !important;
}

.rumi-composer-new .rumi-composer-model-dock {
  margin-top: 2px;
  padding: 9px 2px 0 !important;
  border-top: 1px solid var(--rumi-composer-divider);
  filter: none !important;
}

.rumi-composer-new .rumi-composer-dock-rail {
  width: 100%;
  justify-content: flex-end !important;
  gap: 6px !important;
}

.rumi-composer-control-surface {
  white-space: nowrap;
  height: 32px !important;
  border-color: rgba(255, 255, 255, 0.075) !important;
  border-radius: 11px !important;
  background: rgba(255, 255, 255, 0.035) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.022) !important;
}

.rumi-composer-control-surface:hover {
  border-color: rgba(255, 255, 255, 0.13) !important;
  background: rgba(255, 255, 255, 0.055) !important;
}

.rumi-composer-widget {
  min-width: 0;
}

.rumi-composer-widget[data-composer-widget="model-picker"] {
  max-width: min(15rem, 36vw) !important;
}

.rumi-model-control {
  min-width: 0;
}

.rumi-composer-widget button,
.rumi-composer-widget select,
.rumi-composer-surface button,
.rumi-composer-surface select {
  -webkit-tap-highlight-color: transparent;
}

.rumi-composer-widget button {
  min-width: 0;
  white-space: nowrap;
}

.rumi-composer-widget button > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rumi-composer-widget button:focus-visible,
.rumi-composer-surface button:focus-visible,
.rumi-composer-surface select:focus-visible,
.rumi-workspace-picker select:focus-visible {
  outline: none !important;
  box-shadow: 0 0 0 2px rgba(161, 161, 170, 0.24) !important;
}

.rumi-send-button {
  border-radius: 10px !important;
  transform: none !important;
  transition: opacity 140ms ease, transform 140ms var(--rumi-composer-ease), filter 140ms ease !important;
}

.rumi-send-button:not(:disabled):hover {
  transform: translateY(-1px) !important;
  filter: brightness(1.05);
  box-shadow: none !important;
}

.rumi-send-button:not(:disabled):active {
  transform: scale(0.96) !important;
}

.rumi-composer-toolbar {
  display: grid !important;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px !important;
  margin-top: 3px;
  padding: 9px 12px 10px !important;
  border-top: 1px solid var(--rumi-composer-divider);
}

.rumi-composer-toolbar > :first-child {
  min-width: 0;
  overflow-x: auto !important;
  overflow-y: hidden;
  scrollbar-width: none;
}

.rumi-composer-toolbar > :first-child::-webkit-scrollbar {
  display: none;
}

.rumi-composer-submit-area {
  min-width: 0;
  max-width: min(70%, 31rem);
  gap: 6px !important;
}

.rumi-composer-context-rail {
  display: grid !important;
  grid-template-columns: minmax(220px, 1.35fr) minmax(120px, 0.72fr) minmax(120px, 0.72fr);
  align-items: center;
  gap: 7px !important;
  margin: 0 !important;
  padding: 9px 12px 11px !important;
  border-top: 1px solid var(--rumi-composer-divider);
  color: var(--rumi-composer-muted) !important;
}

.rumi-composer-context-rail > .rumi-coding-workspace-badge {
  display: none !important;
}

.rumi-composer-context-field {
  display: grid !important;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 6px !important;
  min-width: 0;
  height: 32px;
  margin: 0 !important;
  padding: 0 9px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.026);
}

.rumi-composer-context-field svg {
  flex: 0 0 auto;
  color: rgba(161, 161, 170, 0.72);
}

.rumi-composer-context-field select {
  width: 100%;
  max-width: none !important;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 0 !important;
  background: transparent !important;
  color: rgba(212, 212, 216, 0.9) !important;
  outline: none;
}

.rumi-workspace-picker {
  display: grid !important;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 5px !important;
  width: 100%;
  min-width: 0;
}

.rumi-workspace-picker-main {
  position: relative;
  min-width: 0;
}

.rumi-workspace-picker-main > svg:first-child {
  position: absolute;
  left: 10px;
  top: 50%;
  z-index: 1;
  transform: translateY(-50%);
  pointer-events: none;
}

.rumi-workspace-picker-chevron {
  position: absolute;
  right: 9px;
  top: 50%;
  z-index: 1;
  transform: translateY(-50%);
  pointer-events: none;
  color: rgba(161, 161, 170, 0.62);
}

.rumi-workspace-picker-select {
  width: 100% !important;
  max-width: none !important;
  height: 32px !important;
  appearance: none;
  border: 1px solid rgba(255, 255, 255, 0.075) !important;
  border-radius: 10px !important;
  background: rgba(255, 255, 255, 0.03) !important;
  padding: 0 28px 0 31px !important;
  font-family: inherit !important;
  font-size: 12px !important;
  font-weight: 500;
  color: rgba(228, 228, 231, 0.94) !important;
  text-overflow: ellipsis;
  transition: border-color 150ms ease, background-color 150ms ease;
}

.rumi-workspace-picker-select:hover {
  border-color: rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.052) !important;
}

.rumi-workspace-picker-actions {
  display: flex;
  align-items: center;
  gap: 3px;
}

.rumi-workspace-picker-action {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: rgba(161, 161, 170, 0.74);
  transition: color 140ms ease, background-color 140ms ease;
}

.rumi-workspace-picker-action:hover {
  background: rgba(255, 255, 255, 0.055) !important;
  color: rgba(244, 244, 245, 0.94) !important;
}

.rumi-workspace-picker-action.is-trust {
  color: rgba(252, 211, 77, 0.88);
}

.rumi-coding-workspace-badge {
  min-width: 0;
}

.rumi-composer-surface > div:has(> .rumi-composer-widget),
.rumi-composer-surface > div:has(> [class*="rounded-md"][class*="border-zinc-7"]) {
  min-width: 0;
}

.rumi-composer-surface [class*="truncate"] {
  min-width: 0;
}

.rumi-composer-popover {
  overflow: hidden;
  border-color: rgba(255, 255, 255, 0.105) !important;
  border-radius: 16px !important;
  background: rgba(20, 20, 22, 0.97) !important;
  box-shadow:
    0 24px 70px rgba(0, 0, 0, 0.52),
    inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  animation: rumi-composer-popover-in 150ms var(--rumi-composer-ease) both;
  transform-origin: 50% 100%;
}

.rumi-composer-command-popover {
  left: 14px !important;
  width: min(560px, calc(100vw - 40px)) !important;
  max-width: calc(100vw - 40px) !important;
  max-height: min(390px, 52vh);
}

.rumi-composer-command-popover > div:last-child {
  max-height: min(330px, 45vh) !important;
  overscroll-behavior: contain;
}

.rumi-composer-command-popover button {
  min-height: 44px;
  padding-block: 8px !important;
}

.rumi-composer-command-popover button > span.min-w-0 > span:first-child {
  overflow: hidden;
  white-space: normal !important;
  overflow-wrap: anywhere;
  text-overflow: clip;
  line-height: 1.3;
}

.rumi-composer-command-popover button > span.min-w-0 > span:nth-child(2) {
  display: -webkit-box !important;
  overflow: hidden;
  white-space: normal !important;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.rumi-composer-popover [role="option"],
.rumi-composer-popover button {
  transition: background-color 110ms ease, color 110ms ease;
}

.rumi-composer-popover [role="option"][aria-selected="true"] {
  background: rgba(255, 255, 255, 0.075) !important;
}

.rumi-composer-popover input {
  border-color: rgba(255, 255, 255, 0.075) !important;
  border-radius: 10px !important;
  background: rgba(255, 255, 255, 0.035) !important;
}

.rumi-composer-surface > div[class*="px-5"][class*="pt-1"] {
  color: rgba(113, 113, 122, 0.88) !important;
}

.rumi-composer-surface > div[class*="px-5"][class*="pt-1"] > span:first-child {
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
}

.rumi-activity-loading {
  border: 0 !important;
  background: transparent !important;
  padding: 6px 2px !important;
  box-shadow: none !important;
}

.rumi-loading-bars {
  position: relative;
  display: block !important;
  width: 28px !important;
  height: 2px !important;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(113, 113, 122, 0.28);
}

.rumi-loading-bars span {
  display: none !important;
}

.rumi-loading-bars span:first-child {
  position: absolute;
  inset-block: 0;
  left: 0;
  display: block !important;
  width: 11px !important;
  height: 2px !important;
  border-radius: 999px;
  background: rgba(212, 212, 216, 0.82) !important;
  animation: rumi-activity-track 1.25s ease-in-out infinite !important;
}

.rumi-activity-loading > div:last-child > div:first-child > span:first-child {
  font-size: 12px !important;
  font-weight: 500 !important;
  letter-spacing: 0 !important;
}

.rumi-activity-loading > div:last-child > div:last-child {
  color: rgba(113, 113, 122, 0.88) !important;
}

@keyframes rumi-composer-stage-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes rumi-composer-surface-in {
  from { opacity: 0; transform: translateY(9px) scale(0.992); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes rumi-composer-dock-in {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes rumi-composer-submit-away {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to { opacity: 0; transform: translateY(5px) scale(0.994); }
}

@keyframes rumi-composer-popover-in {
  from { opacity: 0; transform: translateY(5px) scale(0.988); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes rumi-composer-caret {
  0%, 48% { opacity: 1; }
  49%, 100% { opacity: 0; }
}

@keyframes rumi-activity-track {
  0% { transform: translateX(-12px); opacity: 0.25; }
  35% { opacity: 1; }
  70% { opacity: 1; }
  100% { transform: translateX(29px); opacity: 0.2; }
}

@media (max-width: 760px) {
  .rumi-composer-experience[data-composer-variant="home"] .rumi-composer-shell,
  .rumi-composer-experience[data-composer-variant="home"] .rumi-composer-shell-new,
  .rumi-composer-experience[data-composer-variant="conversation"] .rumi-composer-shell {
    width: min(100%, calc(100% - 8px)) !important;
  }

  .rumi-composer-context-rail {
    grid-template-columns: minmax(0, 1fr) minmax(110px, 0.58fr) !important;
  }

  .rumi-composer-context-rail > :last-child {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .rumi-new-chat-stage {
    align-items: flex-end !important;
    padding: 16px 8px clamp(3rem, 9vh, 5.5rem) !important;
  }

  .rumi-composer-experience[data-composer-variant="conversation"] > div {
    padding-inline: 5px !important;
    padding-bottom: max(7px, env(safe-area-inset-bottom)) !important;
  }

  .rumi-composer-surface {
    border-radius: 20px !important;
  }

  .rumi-composer-experience[data-composer-variant="home"] .rumi-composer-surface {
    padding-inline: 7px;
  }

  .rumi-composer-editor-row {
    min-height: 56px !important;
    grid-template-columns: 1.75rem minmax(0, 1fr) auto !important;
    column-gap: 7px !important;
    padding-inline: 3px !important;
  }

  .rumi-composer-experience[data-composer-variant="home"] textarea.rumi-composer-textarea,
  .rumi-composer-experience[data-composer-variant="home"] .rumi-composer-mention-overlay {
    padding-top: 12px !important;
    font-size: 15px !important;
    line-height: 22px !important;
  }

  .rumi-composer-experience[data-composer-variant="conversation"] textarea.rumi-composer-textarea {
    padding: 13px 14px 7px !important;
    font-size: 14px !important;
    line-height: 21px;
  }

  .rumi-composer-toolbar {
    gap: 6px !important;
    padding: 8px 8px 9px !important;
  }

  .rumi-composer-submit-area {
    max-width: none;
  }

  .rumi-composer-context-rail {
    grid-template-columns: minmax(0, 1fr) !important;
    padding: 8px !important;
  }

  .rumi-composer-context-rail > :last-child {
    grid-column: auto;
  }

  .rumi-composer-command-popover {
    left: 8px !important;
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px) !important;
  }

  .rumi-composer-popover {
    border-radius: 14px !important;
  }
}

@media (max-width: 430px) {
  .rumi-composer-widget[data-composer-widget="voice-input"],
  .rumi-composer-widget[data-composer-widget="computer-use-status"],
  .rumi-composer-widget[data-composer-widget="vision-bridge-status"] {
    display: none !important;
  }

  .rumi-workspace-picker {
    grid-template-columns: minmax(0, 1fr);
  }

  .rumi-workspace-picker-actions {
    justify-content: flex-end;
  }
}

@media (prefers-reduced-motion: reduce) {
  .rumi-new-chat-stage,
  .rumi-composer-surface,
  .rumi-composer-popover,
  .rumi-loading-bars span:first-child,
  textarea.rumi-composer-textarea,
  .rumi-send-button,
  .rumi-composer-fake-caret {
    animation: none !important;
    transition: none !important;
  }
}
`;
