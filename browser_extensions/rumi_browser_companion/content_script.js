(function () {
  const ELEMENT_ATTR = "data-rumi-element-id";
  const HIGHLIGHT_LAYER_ID = "rumi-browser-companion-highlight-layer";
  const REDACTED_VALUE = "[redacted]";
  const MIN_ACTION_CONFIDENCE = 0.75;
  let sequence = 0;
  let highlightTimer = null;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || !message.type) {
      return false;
    }

    (async () => {
      if (message.type === "rumi:dom-snapshot") {
        sendResponse({
          ok: true,
          schema_version: "semantic_dom_v2",
          url: location.href,
          title: document.title,
          viewport: {
            width: window.innerWidth,
            height: window.innerHeight,
            scrollX: window.scrollX,
            scrollY: window.scrollY
          },
          nodes: collectSnapshot(Number(message.maxNodes) || 300, message.options || message)
        });
        return;
      }

      if (message.type === "rumi:element-command") {
        const result = await executeElementCommand(message.command || {});
        sendResponse({ ok: true, ...result });
        return;
      }

      sendResponse({ ok: false, error: `Unknown message type: ${message.type}` });
    })().catch((error) => {
      sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
    });

    return true;
  });

  function collectSnapshot(maxNodes, options) {
    const nodes = [];
    const roots = [document.body || document.documentElement];
    const includeHidden = Boolean(options && options.includeHidden);
    const includeValues = includeValuesAllowed(options);

    while (roots.length > 0 && nodes.length < maxNodes) {
      const root = roots.shift();
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);

      while (walker.nextNode() && nodes.length < maxNodes) {
        const element = walker.currentNode;
        if (!(element instanceof HTMLElement)) {
          continue;
        }
        if (element.shadowRoot) {
          roots.push(element.shadowRoot);
        }
        const rect = element.getBoundingClientRect();
        const computedStyle = window.getComputedStyle(element);
        const isVisible =
          rect.width > 0 &&
          rect.height > 0 &&
          computedStyle.visibility !== "hidden" &&
          computedStyle.display !== "none" &&
          Number(computedStyle.opacity || 1) > 0;
        if (!includeHidden && !isVisible) {
          continue;
        }

        const elementId = ensureElementId(element);
        const role = element.getAttribute("role") || inferRole(element);
        const labels = extractLabels(element);
        const text = extractAccessibleText(element, labels, { includeValues });
        const interactive = isInteractiveElement(element, role);
        const actionHints = buildActionHints(element, role, interactive);
        const selectorMeta = buildSelectorHint(element);
        const liveValue = formValue(element);

        nodes.push({
          index: nodes.length,
          element_id: elementId,
          semantic_id: buildSemanticId(element, role, text),
          tag: element.tagName.toLowerCase(),
          id: element.id || "",
          role: role || "",
          name: text,
          accessible_name: text,
          text,
          labels,
          nearby_text: extractNearbyText(element),
          rect: {
            x: round2(rect.x),
            y: round2(rect.y),
            width: round2(rect.width),
            height: round2(rect.height)
          },
          is_visible: isVisible,
          is_in_viewport: isInViewport(rect),
          interactive,
          flags: {
            clickable: interactive.clickable,
            editable: interactive.editable,
            focusable: interactive.focusable,
            scrollable: interactive.scrollable
          },
          action_hints: actionHints,
          attributes: collectSafeAttributes(element),
          recognition_confidence: recognitionConfidence(element, role, text, labels, interactive),
          value_redacted: Boolean(liveValue && !includeValues),
          selector_hint: selectorMeta.selector,
          selector_hint_unique: selectorMeta.unique,
          selector_hint_confidence: selectorMeta.confidence,
          selector_hint_error: selectorMeta.error,
          xpath_hint: buildXPathHint(element)
        });
      }
    }

    return nodes;
  }

  async function executeElementCommand(command) {
    const action = String(command.action || command.type || "");
    const resolved = resolveTarget(command, action);
    const target = resolved.target;
    switch (action) {
      case "page.click":
      ensureTarget(target, "click");
      validateActionTarget(target, action, command, resolved);
      focusElement(target);
      target.click();
      return { action: "click", element_id: ensureElementId(target), target: resolved.metadata };
      case "page.type":
      ensureTarget(target, "type");
      validateActionTarget(target, action, command, resolved);
      return typeIntoElement(target, String(command.text ?? ""));
      case "page.press":
      if (target) {
        validateActionTarget(target, action, command, resolved);
      } else if (isEnterKey(command) && !hasActionApprovalEvidence(command)) {
        throw new Error("press Enter requires approval evidence because it can submit forms");
      }
      return pressKeys(target, command);
      case "page.scroll":
      if (target && (command.element_id || command.selector)) {
        validateActionTarget(target, action, command, resolved);
      }
      return scrollTarget(target, command);
      case "page.extract":
      ensureTarget(target, "extract");
      return extractFromElement(target, command);
      case "page.highlight":
      ensureTarget(target, "highlight");
      validateActionTarget(target, action, command, resolved);
      return highlightElement(target, command);
      case "page.clear_highlight":
      return clearHighlights();
      default:
        throw new Error(`Unsupported content command: ${action || command.type}`);
    }
  }

  function resolveTarget(command, action) {
    if (command.element_id) {
      const found = document.querySelector(`[${ELEMENT_ATTR}="${cssEscape(command.element_id)}"]`);
      if (found) {
        return { target: found, metadata: { matched_by: "element_id", element_id: command.element_id } };
      }
    }
    if (command.selector) {
      let matches;
      try {
        matches = Array.from(document.querySelectorAll(command.selector));
      } catch (error) {
        throw new Error(`selector target is invalid: ${String(error && error.message ? error.message : error)}`);
      }
      if (matches.length !== 1) {
        throw new Error(`selector target must match exactly one element; matched ${matches.length}`);
      }
      return { target: matches[0], metadata: { matched_by: "selector", selector_count: matches.length } };
    }
    if (action === "page.press") {
      return { target: document.activeElement || document.body || document.documentElement, metadata: { matched_by: "active_element" } };
    }
    if (action === "page.scroll") {
      return { target: document.scrollingElement || document.documentElement || document.body, metadata: { matched_by: "scrolling_element" } };
    }
    if (action === "page.clear_highlight") {
      return { target: document.body || document.documentElement, metadata: { matched_by: "document" } };
    }
    return { target: null, metadata: { matched_by: "none" } };
  }

  function ensureTarget(target, action) {
    if (!target) {
      throw new Error(`${action} target not found`);
    }
    if (!(target instanceof Element)) {
      throw new Error(`${action} target is not an element`);
    }
  }

  function focusElement(target) {
    if (target instanceof HTMLElement) {
      target.focus({ preventScroll: false });
    }
  }

  function typeIntoElement(target, text) {
    focusElement(target);
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
      target.value = text;
    } else if (target instanceof HTMLSelectElement) {
      target.value = text;
    } else if (target instanceof HTMLElement && target.isContentEditable) {
      target.textContent = text;
    } else {
      throw new Error("type target is not editable");
    }
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
    return { action: "type", element_id: ensureElementId(target), text_length: text.length };
  }

  function pressKeys(target, command) {
    const key = String(command.key || "Enter");
    const code = String(command.code || key);
    const repeat = Boolean(command.repeat);
    const modifiers = normalizeModifiers(command.modifiers);
    const dispatchTarget = target instanceof EventTarget ? target : document;
    const eventInit = {
      key,
      code,
      repeat,
      bubbles: true,
      cancelable: true,
      altKey: modifiers.altKey,
      ctrlKey: modifiers.ctrlKey,
      metaKey: modifiers.metaKey,
      shiftKey: modifiers.shiftKey
    };
    dispatchTarget.dispatchEvent(new KeyboardEvent("keydown", eventInit));
    dispatchTarget.dispatchEvent(new KeyboardEvent("keypress", eventInit));
    dispatchTarget.dispatchEvent(new KeyboardEvent("keyup", eventInit));
    return { action: "press", key, code, modifiers };
  }

  function scrollTarget(target, command) {
    const behavior = command.behavior === "smooth" ? "smooth" : "auto";
    const top = Number(command.top);
    const left = Number(command.left);
    const deltaX = Number(command.delta_x);
    const deltaY = Number(command.delta_y);
    const direction = String(command.direction || "").toLowerCase();
    const amount = Number(command.amount);
    const options = {
      behavior
    };

    if (Number.isFinite(top) || Number.isFinite(left)) {
      if (Number.isFinite(top)) {
        options.top = top;
      }
      if (Number.isFinite(left)) {
        options.left = left;
      }
    } else if (Number.isFinite(deltaX) || Number.isFinite(deltaY)) {
      options.top = Number.isFinite(deltaY) ? deltaY : 0;
      options.left = Number.isFinite(deltaX) ? deltaX : 0;
    } else {
      const step = Number.isFinite(amount) && amount !== 0 ? amount : 600;
      if (direction === "left") {
        options.left = -step;
      } else if (direction === "right") {
        options.left = step;
      } else if (direction === "up") {
        options.top = -step;
      } else {
        options.top = step;
      }
    }

    if (target instanceof Element && typeof target.scrollBy === "function" && command.element_id) {
      if (Number.isFinite(top) || Number.isFinite(left)) {
        target.scrollTo(options);
      } else {
        target.scrollBy(options);
      }
    } else {
      if (Number.isFinite(top) || Number.isFinite(left)) {
        window.scrollTo(options);
      } else {
        window.scrollBy(options);
      }
    }

    return {
      action: "scroll",
      target: command.element_id || "window",
      scrollX: window.scrollX,
      scrollY: window.scrollY
    };
  }

  function extractFromElement(target, command) {
    const mode = String(command.mode || "text");
    if (mode === "html") {
      return { action: "extract", mode, value: target.outerHTML };
    }
    if (mode === "value") {
      const value = formValue(target);
      const revealValue = includeValuesAllowed(command) && !isPasswordValueElement(target);
      return {
        action: "extract",
        mode,
        value: revealValue ? value : value ? REDACTED_VALUE : "",
        value_redacted: Boolean(value && !revealValue)
      };
    }
    if (mode === "attributes") {
      const attributes = {};
      const allowedNames = Array.isArray(command.attribute_names)
        ? new Set(command.attribute_names.map((name) => String(name)))
        : null;
      for (const attribute of target.attributes) {
        if (allowedNames && !allowedNames.has(attribute.name)) {
          continue;
        }
        attributes[attribute.name] = attribute.value;
      }
      return { action: "extract", mode, value: attributes };
    }
    return { action: "extract", mode: "text", value: extractAccessibleText(target, undefined, command) };
  }

  function ensureElementId(element) {
    let existing = element.getAttribute(ELEMENT_ATTR);
    if (existing) {
      return existing;
    }
    sequence += 1;
    existing = `rumi-el-${Date.now().toString(36)}-${sequence.toString(36)}`;
    element.setAttribute(ELEMENT_ATTR, existing);
    return existing;
  }

  function inferRole(element) {
    const tag = element.tagName.toLowerCase();
    if (tag === "a" && element.getAttribute("href")) {
      return "link";
    }
    if (tag === "button") {
      return "button";
    }
    if (tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      return type === "checkbox" ? "checkbox" : type === "radio" ? "radio" : "textbox";
    }
    if (tag === "textarea") {
      return "textbox";
    }
    if (tag === "select") {
      return "combobox";
    }
    return "";
  }

  function extractAccessibleText(element, labels, options) {
    const ariaLabel = element.getAttribute("aria-label");
    const alt = element.getAttribute("alt");
    const placeholder = element.getAttribute("placeholder");
    const value = includeValuesAllowed(options) && !isPasswordValueElement(element) ? formValue(element) : "";
    const labelText = Array.isArray(labels) ? labels.join(" ") : "";
    const text = (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
    return (ariaLabel || labelText || alt || placeholder || value || text || "").slice(0, 500);
  }

  function extractLabels(element) {
    const labels = [];
    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) {
      labels.push(ariaLabel);
    }
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      for (const id of labelledBy.split(/\s+/)) {
        const ref = document.getElementById(id);
        if (ref) {
          labels.push(ref.innerText || ref.textContent || "");
        }
      }
    }
    if ("labels" in element && element.labels) {
      for (const label of element.labels) {
        labels.push(label.innerText || label.textContent || "");
      }
    }
    if (element.id) {
      const explicit = document.querySelector(`label[for="${cssEscape(element.id)}"]`);
      if (explicit) {
        labels.push(explicit.innerText || explicit.textContent || "");
      }
    }
    const wrappingLabel = element.closest("label");
    if (wrappingLabel) {
      labels.push(wrappingLabel.innerText || wrappingLabel.textContent || "");
    }
    return uniqueCleanText(labels, 120).slice(0, 6);
  }

  function extractNearbyText(element) {
    const candidates = [];
    const previous = element.previousElementSibling;
    const parent = element.parentElement;
    if (previous) {
      candidates.push(previous.innerText || previous.textContent || "");
    }
    if (parent) {
      candidates.push(parent.innerText || parent.textContent || "");
    }
    return uniqueCleanText(candidates, 240).join(" | ").slice(0, 500);
  }

  function isInteractiveElement(element, role) {
    const tag = element.tagName.toLowerCase();
    const tabindex = element.getAttribute("tabindex");
    const editable = Boolean(
      element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement ||
        element.isContentEditable
    );
    const clickableRoles = new Set(["button", "link", "checkbox", "menuitem", "option", "radio", "switch", "tab"]);
    const clickableTags = new Set(["a", "button", "input", "label", "option", "select", "summary", "textarea"]);
    const clickable = clickableRoles.has(role) || clickableTags.has(tag) || typeof element.onclick === "function";
    const focusable =
      editable ||
      clickable ||
      tabindex !== null ||
      element.matches("audio[controls], video[controls], iframe");
    const scrollable = element.scrollHeight > element.clientHeight || element.scrollWidth > element.clientWidth;
    return {
      clickable,
      editable,
      focusable,
      scrollable
    };
  }

  function buildSelectorHint(element) {
    const candidates = [];
    if (element.id) {
      candidates.push({ selector: `#${cssEscape(element.id)}`, confidence: 0.98 });
    }
    const testId = element.getAttribute("data-testid") || element.getAttribute("data-test");
    if (testId) {
      candidates.push({ selector: `[data-testid="${cssStringEscape(testId)}"]`, confidence: 0.94 });
      candidates.push({ selector: `[data-test="${cssStringEscape(testId)}"]`, confidence: 0.94 });
    }
    const parts = [];
    let current = element;
    while (current instanceof Element && parts.length < 4) {
      let part = current.tagName.toLowerCase();
      if (current.classList.length > 0) {
        part += `.${Array.from(current.classList).slice(0, 2).map((name) => cssEscape(name)).join(".")}`;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((child) => child.tagName === current.tagName);
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }
      parts.unshift(part);
      current = current.parentElement;
    }
    if (parts.length > 0) {
      candidates.push({ selector: parts.join(" > "), confidence: 0.82 });
    }
    for (const candidate of candidates) {
      const meta = selectorHintMetadata(element, candidate.selector, candidate.confidence);
      if (meta.unique) {
        return meta;
      }
    }
    if (candidates.length > 0) {
      return selectorHintMetadata(element, candidates[0].selector, candidates[0].confidence);
    }
    return { selector: "", unique: false, confidence: 0, error: "no selector hint available" };
  }

  function buildXPathHint(element) {
    const parts = [];
    let current = element;
    while (current instanceof Element && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === current.tagName) {
          index += 1;
        }
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${current.tagName.toLowerCase()}[${index}]`);
      current = current.parentElement;
    }
    return parts.length ? `/${parts.join("/")}` : "";
  }

  function buildSemanticId(element, role, text) {
    const tag = element.tagName.toLowerCase();
    const stable =
      element.id ||
      element.getAttribute("data-testid") ||
      element.getAttribute("data-test") ||
      element.getAttribute("name") ||
      text ||
      "";
    return [tag, role || "node", slugify(stable).slice(0, 48)].filter(Boolean).join(":");
  }

  function collectSafeAttributes(element) {
    const allowed = [
      "aria-label",
      "aria-labelledby",
      "data-testid",
      "data-test",
      "href",
      "name",
      "placeholder",
      "role",
      "title",
      "type"
    ];
    const attributes = {};
    for (const name of allowed) {
      const value = element.getAttribute(name);
      if (!value) {
        continue;
      }
      attributes[name] = String(value).slice(0, 240);
    }
    return attributes;
  }

  function buildActionHints(element, role, interactive) {
    const hints = ["extract", "highlight"];
    if (interactive.clickable) {
      hints.push("click");
    }
    if (interactive.editable) {
      hints.push(element instanceof HTMLSelectElement ? "select" : "type");
    }
    if (interactive.focusable) {
      hints.push("press");
    }
    if (interactive.scrollable) {
      hints.push("scroll");
    }
    if (role === "link") {
      hints.push("open");
    }
    return Array.from(new Set(hints));
  }

  function recognitionConfidence(element, role, text, labels, interactive) {
    let score = 0.25;
    if (interactive.clickable || interactive.editable || interactive.focusable) {
      score += 0.25;
    }
    if (role) {
      score += 0.15;
    }
    if (text) {
      score += 0.15;
    }
    if (labels.length > 0) {
      score += 0.15;
    }
    if (element.id || element.getAttribute("data-testid") || element.getAttribute("name")) {
      score += 0.05;
    }
    return round2(Math.min(score, 0.99));
  }

  function isInViewport(rect) {
    return rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
  }

  function highlightElement(target, command) {
    const rect = target.getBoundingClientRect();
    const layer = ensureHighlightLayer(Boolean(command.clear_existing ?? true));
    const color = String(command.color || "#2563eb");
    const label = String(command.label || target.getAttribute(ELEMENT_ATTR) || "Rumi").slice(0, 80);
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.left = `${rect.left}px`;
    overlay.style.top = `${rect.top}px`;
    overlay.style.width = `${rect.width}px`;
    overlay.style.height = `${rect.height}px`;
    overlay.style.border = `2px solid ${color}`;
    overlay.style.boxShadow = `0 0 0 3px ${hexToRgba(color, 0.18)}`;
    overlay.style.borderRadius = "6px";
    overlay.style.pointerEvents = "none";
    overlay.style.zIndex = "2147483647";

    const badge = document.createElement("div");
    badge.textContent = label;
    badge.style.position = "absolute";
    badge.style.left = "0";
    badge.style.top = "-22px";
    badge.style.maxWidth = "320px";
    badge.style.overflow = "hidden";
    badge.style.textOverflow = "ellipsis";
    badge.style.whiteSpace = "nowrap";
    badge.style.background = color;
    badge.style.color = "white";
    badge.style.font = "12px/18px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    badge.style.padding = "1px 6px";
    badge.style.borderRadius = "4px";
    overlay.appendChild(badge);
    layer.appendChild(overlay);

    const durationMs = Number(command.duration_ms);
    if (Number.isFinite(durationMs) && durationMs > 0) {
      if (highlightTimer) {
        clearTimeout(highlightTimer);
      }
      highlightTimer = setTimeout(() => clearHighlights(), Math.min(durationMs, 30000));
    }

    return {
      action: "highlight",
      element_id: ensureElementId(target),
      rect: {
        x: round2(rect.x),
        y: round2(rect.y),
        width: round2(rect.width),
        height: round2(rect.height)
      }
    };
  }

  function ensureHighlightLayer(clearExisting) {
    let layer = document.getElementById(HIGHLIGHT_LAYER_ID);
    if (!layer) {
      layer = document.createElement("div");
      layer.id = HIGHLIGHT_LAYER_ID;
      layer.style.position = "fixed";
      layer.style.inset = "0";
      layer.style.pointerEvents = "none";
      layer.style.zIndex = "2147483647";
      document.documentElement.appendChild(layer);
    }
    if (clearExisting) {
      layer.textContent = "";
    }
    return layer;
  }

  function clearHighlights() {
    if (highlightTimer) {
      clearTimeout(highlightTimer);
      highlightTimer = null;
    }
    const layer = document.getElementById(HIGHLIGHT_LAYER_ID);
    if (layer) {
      layer.remove();
    }
    return { action: "clear_highlight" };
  }

  function uniqueCleanText(values, maxLength) {
    const seen = new Set();
    const result = [];
    for (const value of values) {
      const text = String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
      if (!text || seen.has(text)) {
        continue;
      }
      seen.add(text);
      result.push(text);
    }
    return result;
  }

  function includeValuesAllowed(options) {
    return Boolean(options && options.include_values === true && options.include_values_approved === true);
  }

  function formValue(element) {
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {
      return String(element.value || "");
    }
    return "";
  }

  function isPasswordValueElement(element) {
    return element instanceof HTMLInputElement && String(element.type || "").toLowerCase() === "password";
  }

  function validateActionTarget(target, action, command, resolved) {
    ensureTarget(target, action.replace(/^page\./, ""));
    if (!(target instanceof HTMLElement)) {
      throw new Error(`${action} target must be an HTMLElement`);
    }
    const state = inspectActionTarget(target);
    if (!state.visible) {
      throw new Error(`${action} target is hidden`);
    }
    if (!state.inViewport) {
      throw new Error(`${action} target is outside the viewport`);
    }
    if (state.disabled) {
      throw new Error(`${action} target is disabled`);
    }
    if (action === "page.type" && state.readOnly) {
      throw new Error("type target is readOnly");
    }
    const actionName = action.replace(/^page\./, "");
    if (actionName === "click" || actionName === "type" || actionName === "press") {
      if (!state.topmost) {
        throw new Error(`${action} target is not topmost at its center point`);
      }
    }
    if (!state.actionHints.includes(actionName)) {
      throw new Error(`${action} target does not advertise ${actionName} in action_hints`);
    }
    if (state.confidence < MIN_ACTION_CONFIDENCE) {
      throw new Error(`${action} target confidence ${state.confidence} is below ${MIN_ACTION_CONFIDENCE}`);
    }
    if (action === "page.click" && isSubmitLikeClickTarget(target) && !hasActionApprovalEvidence(command)) {
      throw new Error("submit-like click requires approval evidence");
    }
    if (action === "page.press" && isEnterKey(command) && isSubmitLikePressTarget(target) && !hasActionApprovalEvidence(command)) {
      throw new Error("press Enter requires approval evidence because it can submit forms");
    }
    if (resolved && resolved.metadata) {
      resolved.metadata.validation = {
        visible: state.visible,
        in_viewport: state.inViewport,
        enabled: !state.disabled,
        read_only: state.readOnly,
        topmost: state.topmost,
        recognition_confidence: state.confidence,
        action_hints: state.actionHints
      };
    }
  }

  function inspectActionTarget(element) {
    const rect = element.getBoundingClientRect();
    const computedStyle = window.getComputedStyle(element);
    const role = element.getAttribute("role") || inferRole(element);
    const labels = extractLabels(element);
    const text = extractAccessibleText(element, labels);
    const interactive = isInteractiveElement(element, role);
    const actionHints = buildActionHints(element, role, interactive);
    return {
      visible:
        rect.width > 0 &&
        rect.height > 0 &&
        computedStyle.visibility !== "hidden" &&
        computedStyle.display !== "none" &&
        Number(computedStyle.opacity || 1) > 0,
      inViewport: isInViewport(rect),
      disabled: isDisabledElement(element),
      readOnly: isReadOnlyElement(element),
      topmost: isTopmostAtCenter(element, rect),
      actionHints,
      confidence: recognitionConfidence(element, role, text, labels, interactive)
    };
  }

  function isDisabledElement(element) {
    return Boolean(
      element.getAttribute("aria-disabled") === "true" ||
        (element instanceof HTMLButtonElement && element.disabled) ||
        (element instanceof HTMLInputElement && element.disabled) ||
        (element instanceof HTMLSelectElement && element.disabled) ||
        (element instanceof HTMLTextAreaElement && element.disabled) ||
        (element instanceof HTMLOptionElement && element.disabled)
    );
  }

  function isReadOnlyElement(element) {
    return Boolean(
      (element instanceof HTMLInputElement && element.readOnly) ||
        (element instanceof HTMLTextAreaElement && element.readOnly) ||
        element.getAttribute("aria-readonly") === "true"
    );
  }

  function isTopmostAtCenter(element, rect) {
    const x = Math.min(Math.max(rect.left + rect.width / 2, 0), Math.max(window.innerWidth - 1, 0));
    const y = Math.min(Math.max(rect.top + rect.height / 2, 0), Math.max(window.innerHeight - 1, 0));
    const top = document.elementFromPoint(x, y);
    return Boolean(top && (top === element || element.contains(top) || top.contains(element)));
  }

  function isSubmitLikeClickTarget(element) {
    if (element instanceof HTMLInputElement) {
      return ["submit", "image"].includes(String(element.type || "").toLowerCase());
    }
    if (element instanceof HTMLButtonElement) {
      const type = String(element.type || "submit").toLowerCase();
      return type === "submit" || (!element.getAttribute("type") && Boolean(element.closest("form")));
    }
    return Boolean(element.closest("button,input")?.closest("form") && /submit|send|pay|buy|order|checkout|confirm|save/i.test(element.textContent || ""));
  }

  function isSubmitLikePressTarget(element) {
    if (!element.closest("form")) {
      return false;
    }
    return Boolean(
      element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement ||
        element instanceof HTMLButtonElement ||
        element.isContentEditable
    );
  }

  function isEnterKey(command) {
    return String(command.key || command.code || "Enter").toLowerCase() === "enter";
  }

  function hasActionApprovalEvidence(command) {
    return command && command.approval_evidence === "tool_server_approval";
  }

  function selectorHintMetadata(element, selector, confidence) {
    try {
      const matches = Array.from(document.querySelectorAll(selector));
      const unique = matches.length === 1 && matches[0] === element;
      return {
        selector,
        unique,
        confidence: unique ? confidence : Math.min(confidence, 0.5),
        error: unique ? "" : `selector matched ${matches.length} elements`
      };
    } catch (error) {
      return {
        selector,
        unique: false,
        confidence: 0,
        error: String(error && error.message ? error.message : error)
      };
    }
  }

  function slugify(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function hexToRgba(value, alpha) {
    const match = /^#?([a-f0-9]{6})$/i.exec(value);
    if (!match) {
      return `rgba(37, 99, 235, ${alpha})`;
    }
    const intValue = parseInt(match[1], 16);
    const r = (intValue >> 16) & 255;
    const g = (intValue >> 8) & 255;
    const b = intValue & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function normalizeModifiers(modifiers) {
    const list = Array.isArray(modifiers) ? modifiers.map((item) => String(item).toLowerCase()) : [];
    return {
      altKey: list.includes("alt"),
      ctrlKey: list.includes("ctrl") || list.includes("control"),
      metaKey: list.includes("meta") || list.includes("cmd") || list.includes("command"),
      shiftKey: list.includes("shift")
    };
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function cssStringEscape(value) {
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function round2(value) {
    return Math.round(value * 100) / 100;
  }
})();
