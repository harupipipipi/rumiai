(function () {
  const ELEMENT_ATTR = "data-rumi-element-id";
  let sequence = 0;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || !message.type) {
      return false;
    }

    (async () => {
      if (message.type === "rumi:dom-snapshot") {
        sendResponse({
          ok: true,
          url: location.href,
          title: document.title,
          viewport: {
            width: window.innerWidth,
            height: window.innerHeight,
            scrollX: window.scrollX,
            scrollY: window.scrollY
          },
          nodes: collectSnapshot(Number(message.maxNodes) || 300)
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

  function collectSnapshot(maxNodes) {
    const nodes = [];
    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_ELEMENT);

    while (walker.nextNode() && nodes.length < maxNodes) {
      const element = walker.currentNode;
      if (!(element instanceof HTMLElement)) {
        continue;
      }
      const rect = element.getBoundingClientRect();
      const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(element).visibility !== "hidden";
      if (!isVisible) {
        continue;
      }

      const elementId = ensureElementId(element);
      const role = element.getAttribute("role") || inferRole(element);
      const text = extractAccessibleText(element);
      const interactive = isInteractiveElement(element, role);

      nodes.push({
        element_id: elementId,
        tag: element.tagName.toLowerCase(),
        id: element.id || "",
        role: role || "",
        name: text,
        text,
        rect: {
          x: round2(rect.x),
          y: round2(rect.y),
          width: round2(rect.width),
          height: round2(rect.height)
        },
        interactive,
        flags: {
          clickable: interactive.clickable,
          editable: interactive.editable,
          focusable: interactive.focusable,
          scrollable: interactive.scrollable
        },
        selector_hint: buildSelectorHint(element)
      });
    }

    return nodes;
  }

  async function executeElementCommand(command) {
    const target = resolveTarget(command);
    const action = String(command.action || command.type || "");
    switch (action) {
      case "page.click":
      ensureTarget(target, "click");
      focusElement(target);
      target.click();
      return { action: "click", element_id: target.getAttribute(ELEMENT_ATTR) };
      case "page.type":
      ensureTarget(target, "type");
      return typeIntoElement(target, String(command.text ?? ""));
      case "page.press":
      return pressKeys(target, command);
      case "page.scroll":
      return scrollTarget(target, command);
      case "page.extract":
      ensureTarget(target, "extract");
      return extractFromElement(target, command);
      default:
        throw new Error(`Unsupported content command: ${action || command.type}`);
    }
  }

  function resolveTarget(command) {
    if (command.element_id) {
      const found = document.querySelector(`[${ELEMENT_ATTR}="${cssEscape(command.element_id)}"]`);
      if (found) {
        return found;
      }
    }
    if (command.selector) {
      return document.querySelector(command.selector);
    }
    const action = String(command.action || command.type || "");
    if (action === "page.press") {
      return document.activeElement || document.body || document.documentElement;
    }
    if (action === "page.scroll") {
      return document.scrollingElement || document.documentElement || document.body;
    }
    return null;
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
    return { action: "type", element_id: target.getAttribute(ELEMENT_ATTR), text_length: text.length };
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
      const value = "value" in target ? target.value : "";
      return { action: "extract", mode, value };
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
    return { action: "extract", mode: "text", value: extractAccessibleText(target) };
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

  function extractAccessibleText(element) {
    const ariaLabel = element.getAttribute("aria-label");
    const alt = element.getAttribute("alt");
    const placeholder = element.getAttribute("placeholder");
    const value = "value" in element ? element.value : "";
    const text = (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
    return (ariaLabel || alt || placeholder || value || text || "").slice(0, 500);
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
    if (element.id) {
      return `#${element.id}`;
    }
    const parts = [];
    let current = element;
    while (current instanceof Element && parts.length < 4) {
      let part = current.tagName.toLowerCase();
      if (current.classList.length > 0) {
        part += `.${Array.from(current.classList).slice(0, 2).join(".")}`;
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
    return parts.join(" > ");
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

  function round2(value) {
    return Math.round(value * 100) / 100;
  }
})();
