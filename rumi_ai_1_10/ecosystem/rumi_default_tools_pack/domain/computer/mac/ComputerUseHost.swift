import AppKit
import ApplicationServices
import CoreGraphics
import Foundation
import Vision

let hostVersion = "rumi.mac.computer_use_host.v1"

func readRequest() throws -> [String: Any] {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    if data.isEmpty {
        return [:]
    }
    let object = try JSONSerialization.jsonObject(with: data, options: [])
    return object as? [String: Any] ?? [:]
}

func emit(_ value: [String: Any]) -> Never {
    let safeValue: [String: Any]
    if JSONSerialization.isValidJSONObject(value) {
        safeValue = value
    } else {
        safeValue = ["ok": false, "error_code": "INVALID_RESULT", "error": "Result was not JSON serializable."]
    }
    let data = (try? JSONSerialization.data(withJSONObject: safeValue, options: [.sortedKeys])) ?? Data()
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

func ok(_ result: [String: Any]) -> Never {
    emit(["ok": true, "result": result])
}

func fail(_ code: String, _ message: String, _ result: [String: Any] = [:]) -> Never {
    var payload: [String: Any] = ["ok": false, "error_code": code, "error": message]
    if !result.isEmpty {
        payload["result"] = result
    }
    emit(payload)
}

func stringValue(_ value: Any?) -> String {
    if let text = value as? String {
        return text
    }
    if let int = value as? Int {
        return String(int)
    }
    if let double = value as? Double {
        return String(double)
    }
    if let bool = value as? Bool {
        return bool ? "true" : "false"
    }
    if let number = value as? NSNumber {
        return number.stringValue
    }
    return ""
}

func intValue(_ value: Any?, default fallback: Int = 0) -> Int {
    if let int = value as? Int {
        return int
    }
    if let double = value as? Double {
        return Int(double)
    }
    if let number = value as? NSNumber {
        return number.intValue
    }
    if let text = value as? String, let parsed = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
        return parsed
    }
    return fallback
}

func doubleValue(_ value: Any?, default fallback: Double = 0) -> Double {
    if let double = value as? Double {
        return double
    }
    if let int = value as? Int {
        return Double(int)
    }
    if let number = value as? NSNumber {
        return number.doubleValue
    }
    if let text = value as? String, let parsed = Double(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
        return parsed
    }
    return fallback
}

func boolValue(_ value: Any?, default fallback: Bool = false) -> Bool {
    if let bool = value as? Bool {
        return bool
    }
    if let int = value as? Int {
        return int != 0
    }
    if let double = value as? Double {
        return double != 0
    }
    if let number = value as? NSNumber {
        return number.boolValue
    }
    let text = stringValue(value).lowercased()
    if ["1", "true", "yes", "y", "on"].contains(text) {
        return true
    }
    if ["0", "false", "no", "n", "off"].contains(text) {
        return false
    }
    return fallback
}

func frontmostPid() -> pid_t {
    NSWorkspace.shared.frontmostApplication?.processIdentifier ?? 0
}

func runningApps() -> [[String: Any]] {
    let activePid = frontmostPid()
    return NSWorkspace.shared.runningApplications.compactMap { app in
        let name = app.localizedName ?? app.bundleIdentifier ?? ""
        if name.isEmpty {
            return nil
        }
        return [
            "name": name,
            "app": name,
            "bundle_id": app.bundleIdentifier ?? "",
            "pid": Int(app.processIdentifier),
            "active": app.processIdentifier == activePid,
            "path": app.bundleURL?.path ?? "",
            "running": true
        ]
    }
}

func appMatches(_ app: NSRunningApplication, args: [String: Any]) -> Bool {
    let pid = intValue(args["pid"])
    if pid > 0 && Int(app.processIdentifier) == pid {
        return true
    }
    let nameNeedle = stringValue(args["app"] ?? args["application"] ?? args["name"]).lowercased()
    let bundleNeedle = stringValue(args["bundle_id"] ?? args["bundleIdentifier"]).lowercased()
    let appName = (app.localizedName ?? "").lowercased()
    let bundleId = (app.bundleIdentifier ?? "").lowercased()
    if !bundleNeedle.isEmpty && bundleId.contains(bundleNeedle) {
        return true
    }
    if !nameNeedle.isEmpty && (appName.contains(nameNeedle) || bundleId.contains(nameNeedle)) {
        return true
    }
    return false
}

func activateApp(args: [String: Any]) -> Never {
    let matches = NSWorkspace.shared.runningApplications.filter { appMatches($0, args: args) }
    guard let app = matches.first else {
        fail("APP_NOT_FOUND", "No running macOS app matched the activation request.", [
            "action": "computer.activate_app",
            "platform": "Darwin",
            "driver": "mac_swift_host"
        ])
    }
    let activated = app.activate(options: [.activateAllWindows])
    usleep(250_000)
    ok([
        "action": "computer.activate_app",
        "platform": "Darwin",
        "executed": activated,
        "active": Int(frontmostPid()) == Int(app.processIdentifier),
        "app": app.localizedName ?? app.bundleIdentifier ?? "",
        "bundle_id": app.bundleIdentifier ?? "",
        "pid": Int(app.processIdentifier),
        "driver": "mac_swift_host"
    ])
}

func windowRecords() -> [[String: Any]] {
    let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    let info = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []
    let activePid = Int(frontmostPid())
    return info.compactMap { item in
        let windowId = intValue(item[kCGWindowNumber as String])
        let pid = intValue(item[kCGWindowOwnerPID as String])
        let app = stringValue(item[kCGWindowOwnerName as String])
        let title = stringValue(item[kCGWindowName as String])
        let layer = intValue(item[kCGWindowLayer as String])
        guard windowId > 0, pid > 0, layer == 0 else {
            return nil
        }
        guard let bounds = item[kCGWindowBounds as String] as? [String: Any] else {
            return nil
        }
        let x = intValue(bounds["X"])
        let y = intValue(bounds["Y"])
        let width = intValue(bounds["Width"])
        let height = intValue(bounds["Height"])
        guard width > 0, height > 0 else {
            return nil
        }
        return [
            "window_id": windowId,
            "id": windowId,
            "pid": pid,
            "app": app,
            "title": title,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "active": pid == activePid,
            "platform": "Darwin"
        ]
    }
}

func matchingWindow(args: [String: Any]) -> [String: Any]? {
    let explicitId = intValue(args["window_id"] ?? args["id"] ?? args["window"])
    let pid = intValue(args["pid"])
    let appNeedle = stringValue(args["app"] ?? args["application"] ?? args["name"]).lowercased()
    let titleNeedle = stringValue(args["title"] ?? args["title_contains"]).lowercased()
    for window in windowRecords() {
        if explicitId > 0 && intValue(window["window_id"]) == explicitId {
            return window
        }
    }
    for window in windowRecords() {
        if pid > 0 && intValue(window["pid"]) != pid {
            continue
        }
        if !appNeedle.isEmpty && !stringValue(window["app"]).lowercased().contains(appNeedle) {
            continue
        }
        if !titleNeedle.isEmpty && !stringValue(window["title"]).lowercased().contains(titleNeedle) {
            continue
        }
        if pid > 0 || !appNeedle.isEmpty || !titleNeedle.isEmpty {
            return window
        }
    }
    return nil
}

func temporaryPngPath() -> String {
    let name = "rumi-mac-computer-\(UUID().uuidString).png"
    return URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(name).path
}

func screenshotPayload(args: [String: Any]) -> (payload: [String: Any]?, code: String, message: String) {
    let path = stringValue(args["output_path"] ?? args["path"]).isEmpty ? temporaryPngPath() : stringValue(args["output_path"] ?? args["path"])
    var command = ["-x"]
    var target: [String: Any] = [:]
    if let window = matchingWindow(args: args) {
        command.append(contentsOf: ["-l", stringValue(window["window_id"])])
        target = window
    } else {
        let x = intValue(args["x"])
        let y = intValue(args["y"])
        let width = intValue(args["width"])
        let height = intValue(args["height"])
        if width > 0 && height > 0 {
            command.append(contentsOf: ["-R", "\(x),\(y),\(width),\(height)"])
            target = ["x": x, "y": y, "width": width, "height": height, "screen": "rect"]
        } else {
            let bounds = CGDisplayBounds(CGMainDisplayID())
            target = ["x": Int(bounds.origin.x), "y": Int(bounds.origin.y), "width": Int(bounds.width), "height": Int(bounds.height), "screen": "main_display"]
        }
    }
    command.append(path)
    guard runProcess("/usr/sbin/screencapture", command) || runProcess("/usr/bin/screencapture", command) else {
        return (nil, "SCREENSHOT_FAILED", "screencapture failed for the requested macOS image.")
    }
    let size = imageSize(path)
    guard size.width > 0, size.height > 0 else {
        return (nil, "IMAGE_UNAVAILABLE", "screencapture produced an unreadable image.")
    }
    return ([
        "action": "computer.screenshot",
        "platform": "Darwin",
        "path": path,
        "width": size.width,
        "height": size.height,
        "method": "swift_screencapture",
        "coordinate_system": "screen_pixels",
        "driver": "mac_swift_host",
        "target_window": target
    ], "", "")
}

func captureScreenshot(args: [String: Any]) -> Never {
    let captured = screenshotPayload(args: args)
    guard let payload = captured.payload else {
        fail(captured.code, captured.message)
    }
    ok(payload)
}

func runProcess(_ executable: String, _ arguments: [String]) -> Bool {
    guard FileManager.default.isExecutableFile(atPath: executable) else {
        return false
    }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    do {
        try process.run()
        process.waitUntilExit()
        return process.terminationStatus == 0
    } catch {
        return false
    }
}

func imageSize(_ path: String) -> (width: Int, height: Int) {
    guard let image = NSImage(contentsOfFile: path) else {
        return (0, 0)
    }
    if let rep = image.representations.first {
        return (rep.pixelsWide, rep.pixelsHigh)
    }
    return (Int(image.size.width), Int(image.size.height))
}

func hostCapabilities(accessibilityTrusted: Bool? = nil) -> [String: Bool] {
    let trusted = accessibilityTrusted ?? AXIsProcessTrusted()
    let visionAvailable: Bool
    if #available(macOS 10.15, *) {
        visionAvailable = true
    } else {
        visionAvailable = false
    }
    return [
        "can_capture_background_window": true,
        "can_foreground_action": true,
        "can_semantic_action": trusted,
        "can_ax_tree": trusted,
        "can_ocr": visionAvailable,
        "can_click_text": visionAvailable,
        "requires_user_permission": true
    ]
}

func axAttribute(_ element: AXUIElement, _ attribute: CFString) -> Any? {
    var value: CFTypeRef?
    let error = AXUIElementCopyAttributeValue(element, attribute, &value)
    if error != .success {
        return nil
    }
    return value
}

func axStringAttribute(_ element: AXUIElement, _ attribute: CFString) -> String {
    stringValue(axAttribute(element, attribute))
}

func axBoolAttribute(_ element: AXUIElement, _ attribute: CFString, default fallback: Bool = true) -> Bool {
    boolValue(axAttribute(element, attribute), default: fallback)
}

func axActions(_ element: AXUIElement) -> [String] {
    var actionNames: CFArray?
    let error = AXUIElementCopyActionNames(element, &actionNames)
    if error != .success {
        return []
    }
    return (actionNames as? [String]) ?? []
}

func asAXUIElement(_ value: Any) -> AXUIElement? {
    let cfValue = value as CFTypeRef
    if CFGetTypeID(cfValue) != AXUIElementGetTypeID() {
        return nil
    }
    return (value as! AXUIElement)
}

func asAXValue(_ value: Any?) -> AXValue? {
    guard let value else {
        return nil
    }
    let cfValue = value as CFTypeRef
    if CFGetTypeID(cfValue) != AXValueGetTypeID() {
        return nil
    }
    return (value as! AXValue)
}

func axChildren(_ element: AXUIElement) -> [AXUIElement] {
    guard let value = axAttribute(element, kAXChildrenAttribute as CFString) else {
        return []
    }
    if let children = value as? [AXUIElement] {
        return children
    }
    if let children = value as? [Any] {
        return children.compactMap { asAXUIElement($0) }
    }
    return []
}

func axPoint(_ value: Any?) -> CGPoint? {
    guard let axValue = asAXValue(value), AXValueGetType(axValue) == .cgPoint else {
        return nil
    }
    var point = CGPoint.zero
    if AXValueGetValue(axValue, .cgPoint, &point) {
        return point
    }
    return nil
}

func axSize(_ value: Any?) -> CGSize? {
    guard let axValue = asAXValue(value), AXValueGetType(axValue) == .cgSize else {
        return nil
    }
    var size = CGSize.zero
    if AXValueGetValue(axValue, .cgSize, &size) {
        return size
    }
    return nil
}

func axFrame(_ element: AXUIElement) -> [String: Any] {
    guard
        let position = axPoint(axAttribute(element, kAXPositionAttribute as CFString)),
        let size = axSize(axAttribute(element, kAXSizeAttribute as CFString))
    else {
        return [:]
    }
    return [
        "x": Double(position.x),
        "y": Double(position.y),
        "width": Double(size.width),
        "height": Double(size.height),
        "center": [
            "x": Double(position.x + size.width / 2.0),
            "y": Double(position.y + size.height / 2.0)
        ],
        "coordinate_system": "screen_points"
    ]
}

func jsonScalar(_ value: Any?) -> Any {
    if let text = value as? String {
        return text
    }
    if let bool = value as? Bool {
        return bool
    }
    if let number = value as? NSNumber {
        return number
    }
    let text = stringValue(value)
    return text
}

func axElementId(pid: pid_t, path: String) -> String {
    "ax:\(Int(pid)):\(path)"
}

func axSummary(_ element: AXUIElement, pid: pid_t, path: String) -> [String: Any] {
    let role = axStringAttribute(element, kAXRoleAttribute as CFString)
    let title = axStringAttribute(element, kAXTitleAttribute as CFString)
    let description = axStringAttribute(element, kAXDescriptionAttribute as CFString)
    let roleDescription = axStringAttribute(element, kAXRoleDescriptionAttribute as CFString)
    let value = jsonScalar(axAttribute(element, kAXValueAttribute as CFString))
    let valueText = stringValue(value)
    let actions = axActions(element)
    var summary: [String: Any] = [
        "id": axElementId(pid: pid, path: path),
        "path": path,
        "pid": Int(pid),
        "role": role,
        "title": title,
        "description": description,
        "enabled": axBoolAttribute(element, kAXEnabledAttribute as CFString, default: true),
        "frame": axFrame(element),
        "actions": actions
    ]
    if !roleDescription.isEmpty {
        summary["role_description"] = roleDescription
    }
    if !valueText.isEmpty {
        summary["value"] = value
    }
    return summary
}

func buildAXTree(
    element: AXUIElement,
    pid: pid_t,
    path: String,
    depth: Int,
    maxDepth: Int,
    maxElements: Int,
    elements: inout [[String: Any]]
) -> [String: Any] {
    var node = axSummary(element, pid: pid, path: path)
    if elements.count >= maxElements {
        node["truncated"] = true
        return node
    }
    elements.append(node)
    if depth >= maxDepth {
        return node
    }
    var childrenPayload: [[String: Any]] = []
    let children = axChildren(element)
    for (index, child) in children.enumerated() {
        if elements.count >= maxElements {
            node["truncated"] = true
            break
        }
        childrenPayload.append(buildAXTree(
            element: child,
            pid: pid,
            path: "\(path).\(index)",
            depth: depth + 1,
            maxDepth: maxDepth,
            maxElements: maxElements,
            elements: &elements
        ))
    }
    if !childrenPayload.isEmpty {
        node["children"] = childrenPayload
    }
    return node
}

func targetPid(args: [String: Any]) -> pid_t {
    let explicitPid = intValue(args["pid"])
    if explicitPid > 0 {
        return pid_t(explicitPid)
    }
    if let window = matchingWindow(args: args) {
        let pid = intValue(window["pid"])
        if pid > 0 {
            return pid_t(pid)
        }
    }
    let nameNeedle = stringValue(args["app"] ?? args["application"] ?? args["name"]).lowercased()
    let bundleNeedle = stringValue(args["bundle_id"] ?? args["bundleIdentifier"]).lowercased()
    if !nameNeedle.isEmpty || !bundleNeedle.isEmpty {
        for app in NSWorkspace.shared.runningApplications {
            let appName = (app.localizedName ?? "").lowercased()
            let bundleId = (app.bundleIdentifier ?? "").lowercased()
            if (!bundleNeedle.isEmpty && bundleId.contains(bundleNeedle))
                || (!nameNeedle.isEmpty && (appName.contains(nameNeedle) || bundleId.contains(nameNeedle))) {
                return app.processIdentifier
            }
        }
    }
    return frontmostPid()
}

func axWindows(_ appElement: AXUIElement) -> [AXUIElement] {
    guard let value = axAttribute(appElement, kAXWindowsAttribute as CFString) else {
        return []
    }
    if let windows = value as? [AXUIElement] {
        return windows
    }
    if let windows = value as? [Any] {
        return windows.compactMap { asAXUIElement($0) }
    }
    return []
}

func selectedAXRoot(args: [String: Any]) -> (pid: pid_t, root: AXUIElement, targetWindow: [String: Any])? {
    let pid = targetPid(args: args)
    guard pid > 0 else {
        return nil
    }
    let appElement = AXUIElementCreateApplication(pid)
    let cgWindow = matchingWindow(args: args)
    let requestedTitle = stringValue(
        args["title"] ?? args["window_title"] ?? args["title_contains"] ?? cgWindow?["title"]
    ).lowercased()
    if !requestedTitle.isEmpty {
        for window in axWindows(appElement) {
            let axTitle = axStringAttribute(window, kAXTitleAttribute as CFString).lowercased()
            if !axTitle.isEmpty && (axTitle.contains(requestedTitle) || requestedTitle.contains(axTitle)) {
                return (pid, window, cgWindow ?? ["pid": Int(pid), "title": axTitle])
            }
        }
    }
    if let focusedValue = axAttribute(appElement, kAXFocusedWindowAttribute as CFString),
       let focused = asAXUIElement(focusedValue) {
        return (pid, focused, cgWindow ?? ["pid": Int(pid)])
    }
    if let first = axWindows(appElement).first {
        return (pid, first, cgWindow ?? ["pid": Int(pid)])
    }
    return (pid, appElement, cgWindow ?? ["pid": Int(pid)])
}

func axTreePayload(args: [String: Any]) -> [String: Any] {
    let trusted = AXIsProcessTrusted()
    var payload: [String: Any] = [
        "action": "computer.ax_tree",
        "platform": "Darwin",
        "driver": "mac_swift_host",
        "elements": [],
        "capabilities": hostCapabilities(accessibilityTrusted: trusted)
    ]
    guard trusted else {
        payload["ax_tree"] = [
            "error_code": "ACCESSIBILITY_NOT_TRUSTED",
            "error": "macOS Accessibility permission is required to read AX elements."
        ]
        return payload
    }
    guard let selected = selectedAXRoot(args: args) else {
        payload["ax_tree"] = [
            "error_code": "AX_TARGET_NOT_FOUND",
            "error": "No macOS Accessibility target matched the request."
        ]
        return payload
    }
    let maxDepth = max(1, intValue(args["max_depth"], default: 8))
    let maxElements = max(1, intValue(args["max_elements"], default: 500))
    var elements: [[String: Any]] = []
    let root = buildAXTree(
        element: selected.root,
        pid: selected.pid,
        path: "0",
        depth: 0,
        maxDepth: maxDepth,
        maxElements: maxElements,
        elements: &elements
    )
    payload["ax_tree"] = [
        "root": root,
        "coordinate_system": "screen_points",
        "element_count": elements.count,
        "truncated": elements.count >= maxElements
    ]
    payload["elements"] = elements
    payload["target_window"] = selected.targetWindow
    return payload
}

func axTree(args: [String: Any]) -> Never {
    ok(axTreePayload(args: args))
}

func observe(args: [String: Any]) -> Never {
    let captured = screenshotPayload(args: args)
    guard var payload = captured.payload else {
        fail(captured.code, captured.message)
    }
    payload["action"] = "computer.observe"
    let axPayload = axTreePayload(args: args)
    if let axTree = axPayload["ax_tree"] {
        payload["ax_tree"] = axTree
    }
    if let elements = axPayload["elements"] {
        payload["elements"] = elements
    }
    if let capabilities = axPayload["capabilities"] {
        payload["capabilities"] = capabilities
    }
    if let targetWindow = axPayload["target_window"] as? [String: Any], !targetWindow.isEmpty {
        payload["target_window"] = targetWindow
    }
    ok(payload)
}

func textTokens(_ text: String) -> [String] {
    let normalized = text.lowercased()
        .components(separatedBy: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters).union(.symbols))
        .filter { !$0.isEmpty }
    let stopWords: Set<String> = [
        "a", "an", "and", "button", "click", "control", "element", "for", "item",
        "link", "menu", "on", "open", "press", "select", "tap", "the", "to"
    ]
    return normalized.filter { !stopWords.contains($0) }
}

func normalizedText(_ text: String) -> String {
    text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
}

func containsLoose(_ haystack: String, _ needle: String) -> Bool {
    let h = normalizedText(haystack)
    let n = normalizedText(needle)
    if n.isEmpty {
        return false
    }
    if h.contains(n) {
        return true
    }
    let compactH = h.replacingOccurrences(of: " ", with: "")
    let compactN = n.replacingOccurrences(of: " ", with: "")
    return !compactN.isEmpty && compactH.contains(compactN)
}

func semanticText(args: [String: Any]) -> String {
    for key in ["text", "title", "label", "name", "value"] {
        let value = stringValue(args[key]).trimmingCharacters(in: .whitespacesAndNewlines)
        if !value.isEmpty {
            return value
        }
    }
    let intent = stringValue(args["intent"] ?? args["query"]).trimmingCharacters(in: .whitespacesAndNewlines)
    if intent.isEmpty {
        return ""
    }
    let tokens = textTokens(intent)
    return tokens.isEmpty ? intent : tokens.joined(separator: " ")
}

struct AXCandidate {
    let element: AXUIElement
    let summary: [String: Any]
    let score: Int
}

func scoreAXSummary(_ summary: [String: Any], args: [String: Any]) -> Int {
    let requestedText = semanticText(args: args)
    let requestedRole = stringValue(args["role"]).lowercased()
    let intent = stringValue(args["intent"] ?? args["query"])
    let title = stringValue(summary["title"])
    let description = stringValue(summary["description"])
    let value = stringValue(summary["value"])
    let role = stringValue(summary["role"]).lowercased()
    let roleDescription = stringValue(summary["role_description"]).lowercased()
    let actions = (summary["actions"] as? [String]) ?? []
    let enabled = boolValue(summary["enabled"], default: true)
    let haystack = [title, description, value, role, roleDescription].joined(separator: " ")
    var score = 0
    if actions.contains(kAXPressAction as String) {
        score += 25
    }
    if enabled {
        score += 5
    } else {
        score -= 100
    }
    if ["axbutton", "axmenuitem", "axcheckbox", "axradiobutton", "axlink", "axtab"].contains(role) {
        score += 10
    }
    if !requestedRole.isEmpty && (role.contains(requestedRole) || roleDescription.contains(requestedRole)) {
        score += 35
    }
    if !requestedText.isEmpty {
        if normalizedText(title) == normalizedText(requestedText) || normalizedText(value) == normalizedText(requestedText) {
            score += 100
        } else if containsLoose(haystack, requestedText) {
            score += 70
        }
        let tokens = textTokens(requestedText)
        if !tokens.isEmpty {
            let matched = tokens.filter { containsLoose(haystack, $0) }.count
            score += matched * 12
            if matched == tokens.count {
                score += 30
            }
        }
    }
    let intentTokens = textTokens(intent)
    if !intentTokens.isEmpty {
        let matched = intentTokens.filter { containsLoose(haystack, $0) }.count
        score += matched * 8
        if matched == intentTokens.count {
            score += 20
        }
    }
    if requestedText.isEmpty && requestedRole.isEmpty && intentTokens.isEmpty {
        return 0
    }
    return score
}

func collectAXCandidates(
    element: AXUIElement,
    pid: pid_t,
    path: String,
    args: [String: Any],
    depth: Int,
    maxDepth: Int,
    maxElements: Int,
    visited: inout Int,
    candidates: inout [AXCandidate]
) {
    if visited >= maxElements {
        return
    }
    visited += 1
    let summary = axSummary(element, pid: pid, path: path)
    let score = scoreAXSummary(summary, args: args)
    if score > 25 {
        candidates.append(AXCandidate(element: element, summary: summary, score: score))
    }
    if depth >= maxDepth {
        return
    }
    for (index, child) in axChildren(element).enumerated() {
        collectAXCandidates(
            element: child,
            pid: pid,
            path: "\(path).\(index)",
            args: args,
            depth: depth + 1,
            maxDepth: maxDepth,
            maxElements: maxElements,
            visited: &visited,
            candidates: &candidates
        )
        if visited >= maxElements {
            break
        }
    }
}

func axPathFromElementId(_ elementId: String, expectedPid: pid_t) -> [Int]? {
    let parts = elementId.split(separator: ":", maxSplits: 2).map(String.init)
    guard parts.count == 3, parts[0] == "ax", Int(parts[1]) == Int(expectedPid) else {
        return nil
    }
    let indices = parts[2].split(separator: ".").compactMap { Int($0) }
    if indices.isEmpty || indices[0] != 0 {
        return nil
    }
    return indices
}

func resolveAXElement(root: AXUIElement, path: [Int]) -> AXUIElement? {
    var current = root
    for index in path.dropFirst() {
        let children = axChildren(current)
        guard index >= 0, index < children.count else {
            return nil
        }
        current = children[index]
    }
    return current
}

func pressAXElement(_ element: AXUIElement) -> AXError {
    AXUIElementPerformAction(element, kAXPressAction as CFString)
}

func ocrPayload(args: [String: Any]) -> (payload: [String: Any]?, code: String, message: String) {
    if #available(macOS 10.15, *) {
        return ocrPayloadAvailable(args: args)
    }
    return (nil, "VISION_UNAVAILABLE", "Vision text recognition requires macOS 10.15 or newer.")
}

@available(macOS 10.15, *)
func ocrPayloadAvailable(args: [String: Any]) -> (payload: [String: Any]?, code: String, message: String) {
    let captured = screenshotPayload(args: args)
    guard let screenshot = captured.payload else {
        return (nil, captured.code, captured.message)
    }
    let path = stringValue(screenshot["path"])
    let imageUrl = URL(fileURLWithPath: path)
    guard FileManager.default.isReadableFile(atPath: path) else {
        return (nil, "OCR_IMAGE_UNAVAILABLE", "OCR screenshot image was not readable.")
    }
    let width = max(1, intValue(screenshot["width"]))
    let height = max(1, intValue(screenshot["height"]))
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    if let languages = args["recognition_languages"] as? [String], !languages.isEmpty {
        request.recognitionLanguages = languages
    }
    let handler = VNImageRequestHandler(url: imageUrl, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return (nil, "OCR_FAILED", "Vision OCR failed: \(String(describing: error))")
    }
    let observations = request.results ?? []
    var items: [[String: Any]] = []
    var textLines: [String] = []
    for observation in observations {
        guard let candidate = observation.topCandidates(1).first else {
            continue
        }
        let rect = observation.boundingBox
        let x = rect.origin.x * CGFloat(width)
        let y = (1.0 - rect.origin.y - rect.height) * CGFloat(height)
        let w = rect.width * CGFloat(width)
        let h = rect.height * CGFloat(height)
        let centerX = x + w / 2.0
        let centerY = y + h / 2.0
        let text = candidate.string
        textLines.append(text)
        items.append([
            "text": text,
            "bbox": [
                "x": Double(x),
                "y": Double(y),
                "width": Double(w),
                "height": Double(h)
            ],
            "center": [
                "x": Double(centerX),
                "y": Double(centerY)
            ],
            "confidence": Double(candidate.confidence),
            "coordinate_system": "screenshot_pixels_top_left"
        ])
    }
    return ([
        "action": "computer.ocr",
        "platform": "Darwin",
        "driver": "mac_swift_host",
        "executed": true,
        "text": textLines.joined(separator: "\n"),
        "items": items,
        "elements": items,
        "coordinate_system": "screenshot_pixels_top_left",
        "screenshot": screenshot
    ], "", "")
}

func ocr(args: [String: Any]) -> Never {
    let result = ocrPayload(args: args)
    guard let payload = result.payload else {
        fail(result.code, result.message, [
            "action": "computer.ocr",
            "platform": "Darwin",
            "driver": "mac_swift_host"
        ])
    }
    ok(payload)
}

func screenPointFromOCRCenter(_ center: [String: Any], screenshot: [String: Any]) -> CGPoint? {
    let imageWidth = Double(max(1, intValue(screenshot["width"])))
    let imageHeight = Double(max(1, intValue(screenshot["height"])))
    guard let target = screenshot["target_window"] as? [String: Any] else {
        return nil
    }
    let targetX = Double(intValue(target["x"]))
    let targetY = Double(intValue(target["y"]))
    let targetWidth = Double(max(1, intValue(target["width"], default: Int(imageWidth))))
    let targetHeight = Double(max(1, intValue(target["height"], default: Int(imageHeight))))
    let x = doubleValue(center["x"]) * targetWidth / imageWidth
    let y = doubleValue(center["y"]) * targetHeight / imageHeight
    return CGPoint(x: targetX + x, y: targetY + y)
}

func scoreOCRItem(_ item: [String: Any], query: String) -> Int {
    let text = stringValue(item["text"])
    if query.isEmpty || text.isEmpty {
        return 0
    }
    var score = 0
    if normalizedText(text) == normalizedText(query) {
        score += 100
    } else if containsLoose(text, query) || containsLoose(query, text) {
        score += 70
    }
    let tokens = textTokens(query)
    if !tokens.isEmpty {
        let matched = tokens.filter { containsLoose(text, $0) }.count
        score += matched * 15
        if matched == tokens.count {
            score += 25
        }
    }
    return score
}

func semanticOCRFallback(args: [String: Any], actionName: String, reason: String) -> Never {
    let query = semanticText(args: args)
    guard !query.isEmpty else {
        fail("SEMANTIC_TARGET_REQUIRED", "semantic_action requires element_id, text, title, role, or intent.", [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "reason": reason
        ])
    }
    let ocrResult = ocrPayload(args: args)
    guard let payload = ocrResult.payload else {
        fail(ocrResult.code, ocrResult.message, [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "reason": reason
        ])
    }
    let items = (payload["items"] as? [[String: Any]]) ?? []
    let ranked = items
        .map { (item: $0, score: scoreOCRItem($0, query: query)) }
        .filter { $0.score > 30 }
        .sorted { $0.score > $1.score }
    guard let match = ranked.first, let center = match.item["center"] as? [String: Any], let screenshot = payload["screenshot"] as? [String: Any] else {
        fail("SEMANTIC_TARGET_NOT_FOUND", "No AX element or OCR text matched the semantic request.", [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "reason": reason,
            "query": query,
            "ocr": payload
        ])
    }
    guard let point = screenPointFromOCRCenter(center, screenshot: screenshot) else {
        fail("OCR_COORDINATE_UNAVAILABLE", "OCR matched text but could not map it to screen coordinates.", [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "query": query,
            "match": match.item
        ])
    }
    CGWarpMouseCursorPosition(point)
    postMouse(.leftMouseDown, point: point, button: .left)
    usleep(35_000)
    postMouse(.leftMouseUp, point: point, button: .left)
    ok([
        "action": actionName,
        "platform": "Darwin",
        "driver": "mac_swift_host",
        "executed": true,
        "method": "ocr_click_fallback",
        "uses_physical_input": true,
        "query": query,
        "x": Int(point.x),
        "y": Int(point.y),
        "coordinate_system": "screen_points",
        "match": match.item,
        "ocr": payload,
        "fallback_reason": reason
    ])
}

func semanticAction(args: [String: Any], actionName: String = "computer.semantic_action") -> Never {
    let elementId = stringValue(args["element_id"] ?? args["id"])
    if !elementId.isEmpty && !AXIsProcessTrusted() {
        fail("ACCESSIBILITY_NOT_TRUSTED", "macOS Accessibility permission is required to press AX elements.", [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "element_id": elementId
        ])
    }
    if AXIsProcessTrusted(), let selected = selectedAXRoot(args: args) {
        if !elementId.isEmpty {
            if let path = axPathFromElementId(elementId, expectedPid: selected.pid),
               let element = resolveAXElement(root: selected.root, path: path) {
                let error = pressAXElement(element)
                if error == .success {
                    ok([
                        "action": actionName,
                        "platform": "Darwin",
                        "driver": "mac_swift_host",
                        "executed": true,
                        "method": "ax_press",
                        "uses_physical_input": false,
                        "element": axSummary(element, pid: selected.pid, path: path.map(String.init).joined(separator: "."))
                    ])
                }
                fail("AX_PRESS_FAILED", "AXPress failed for element_id \(elementId): \(error.rawValue)", [
                    "action": actionName,
                    "platform": "Darwin",
                    "driver": "mac_swift_host",
                    "executed": false,
                    "element_id": elementId
                ])
            }
            fail("AX_ELEMENT_NOT_FOUND", "No AX element matched element_id \(elementId).", [
                "action": actionName,
                "platform": "Darwin",
                "driver": "mac_swift_host",
                "executed": false,
                "element_id": elementId
            ])
        }
        var visited = 0
        var candidates: [AXCandidate] = []
        collectAXCandidates(
            element: selected.root,
            pid: selected.pid,
            path: "0",
            args: args,
            depth: 0,
            maxDepth: max(1, intValue(args["max_depth"], default: 8)),
            maxElements: max(1, intValue(args["max_elements"], default: 500)),
            visited: &visited,
            candidates: &candidates
        )
        for candidate in candidates.sorted(by: { $0.score > $1.score }) {
            let error = pressAXElement(candidate.element)
            if error == .success {
                ok([
                    "action": actionName,
                    "platform": "Darwin",
                    "driver": "mac_swift_host",
                    "executed": true,
                    "method": "ax_press",
                    "uses_physical_input": false,
                    "score": candidate.score,
                    "element": candidate.summary
                ])
            }
        }
        semanticOCRFallback(args: args, actionName: actionName, reason: "No matching AX candidate could be pressed.")
    }
    if !elementId.isEmpty {
        fail("AX_TARGET_NOT_FOUND", "No macOS Accessibility target matched the element_id request.", [
            "action": actionName,
            "platform": "Darwin",
            "driver": "mac_swift_host",
            "executed": false,
            "element_id": elementId
        ])
    }
    semanticOCRFallback(args: args, actionName: actionName, reason: "Accessibility target unavailable.")
}

func postMouse(_ type: CGEventType, point: CGPoint, button: CGMouseButton) {
    let event = CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: point, mouseButton: button)
    event?.post(tap: .cghidEventTap)
}

func mouseButton(_ raw: String) -> (CGMouseButton, CGEventType, CGEventType, CGEventType) {
    switch raw.lowercased() {
    case "right":
        return (.right, .rightMouseDown, .rightMouseUp, .rightMouseDragged)
    case "middle", "center":
        return (.center, .otherMouseDown, .otherMouseUp, .otherMouseDragged)
    default:
        return (.left, .leftMouseDown, .leftMouseUp, .leftMouseDragged)
    }
}

func move(args: [String: Any]) -> Never {
    let point = CGPoint(x: intValue(args["x"]), y: intValue(args["y"]))
    CGWarpMouseCursorPosition(point)
    CGAssociateMouseAndMouseCursorPosition(boolean_t(1))
    ok(["action": "computer.move", "platform": "Darwin", "executed": true, "x": Int(point.x), "y": Int(point.y), "driver": "mac_swift_host"])
}

func click(args: [String: Any]) -> Never {
    let point = CGPoint(x: intValue(args["x"]), y: intValue(args["y"]))
    let buttonSpec = mouseButton(stringValue(args["button"]).isEmpty ? "left" : stringValue(args["button"]))
    CGWarpMouseCursorPosition(point)
    postMouse(buttonSpec.1, point: point, button: buttonSpec.0)
    usleep(35_000)
    postMouse(buttonSpec.2, point: point, button: buttonSpec.0)
    ok(["action": "computer.click", "platform": "Darwin", "executed": true, "x": Int(point.x), "y": Int(point.y), "driver": "mac_swift_host"])
}

func drag(args: [String: Any]) -> Never {
    let start = CGPoint(x: intValue(args["x1"] ?? args["from_x"]), y: intValue(args["y1"] ?? args["from_y"]))
    let end = CGPoint(x: intValue(args["x2"] ?? args["to_x"]), y: intValue(args["y2"] ?? args["to_y"]))
    let buttonSpec = mouseButton(stringValue(args["button"]).isEmpty ? "left" : stringValue(args["button"]))
    CGWarpMouseCursorPosition(start)
    postMouse(buttonSpec.1, point: start, button: buttonSpec.0)
    let steps = 16
    for index in 1...steps {
        let t = CGFloat(index) / CGFloat(steps)
        let point = CGPoint(x: start.x + (end.x - start.x) * t, y: start.y + (end.y - start.y) * t)
        postMouse(buttonSpec.3, point: point, button: buttonSpec.0)
        usleep(10_000)
    }
    postMouse(buttonSpec.2, point: end, button: buttonSpec.0)
    ok(["action": "computer.drag", "platform": "Darwin", "executed": true, "driver": "mac_swift_host"])
}

func typeText(args: [String: Any]) -> Never {
    let text = stringValue(args["text"])
    for scalar in text.unicodeScalars {
        var value = UniChar(scalar.value)
        if let down = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: true) {
            down.keyboardSetUnicodeString(stringLength: 1, unicodeString: &value)
            down.post(tap: .cghidEventTap)
        }
        if let up = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: false) {
            up.keyboardSetUnicodeString(stringLength: 1, unicodeString: &value)
            up.post(tap: .cghidEventTap)
        }
    }
    ok(["action": "computer.type", "platform": "Darwin", "executed": true, "length": text.count, "driver": "mac_swift_host"])
}

func keyCode(_ key: String) -> CGKeyCode? {
    let lower = key.lowercased()
    let map: [String: CGKeyCode] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
        "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
        "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
        "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
        "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "return": 36,
        "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
        ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
        "`": 50, "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
        "left": 123, "right": 124, "down": 125, "up": 126
    ]
    if let code = map[lower] {
        return code
    }
    if lower.hasPrefix("f"), let number = Int(lower.dropFirst()), number >= 1, number <= 20 {
        return CGKeyCode(121 + number)
    }
    return nil
}

func flags(_ modifiers: [String]) -> CGEventFlags {
    var result = CGEventFlags()
    for modifier in modifiers.map({ $0.lowercased() }) {
        switch modifier {
        case "cmd", "command", "meta":
            result.insert(.maskCommand)
        case "ctrl", "control":
            result.insert(.maskControl)
        case "alt", "option":
            result.insert(.maskAlternate)
        case "shift":
            result.insert(.maskShift)
        default:
            continue
        }
    }
    return result
}

func key(args: [String: Any]) -> Never {
    let combo = stringValue(args["key_combo"])
    var parts = combo.isEmpty ? [] : combo.split(separator: "+").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
    if parts.isEmpty {
        let keyName = stringValue(args["key"])
        if keyName.isEmpty {
            fail("KEY_REQUIRED", "key or key_combo is required.")
        }
        var modifiers = (args["modifiers"] as? [String]) ?? []
        let modifier = stringValue(args["modifier"])
        if !modifier.isEmpty {
            modifiers.append(modifier)
        }
        parts = modifiers + [keyName]
    }
    let keyName = parts.removeLast()
    guard let code = keyCode(keyName) else {
        fail("UNSUPPORTED_KEY", "Unsupported key: \(keyName)")
    }
    let eventFlags = flags(parts)
    if let down = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: true) {
        down.flags = eventFlags
        down.post(tap: .cghidEventTap)
    }
    if let up = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: false) {
        up.flags = eventFlags
        up.post(tap: .cghidEventTap)
    }
    ok(["action": "computer.key", "platform": "Darwin", "executed": true, "key": keyName, "modifiers": parts, "driver": "mac_swift_host"])
}

func scroll(args: [String: Any]) -> Never {
    let direction = stringValue(args["direction"]).isEmpty ? "down" : stringValue(args["direction"]).lowercased()
    let amount = max(1, intValue(args["amount"] ?? args["clicks"], default: 3))
    let dy = direction == "up" ? amount : (direction == "down" ? -amount : 0)
    let dx = direction == "left" ? amount : (direction == "right" ? -amount : 0)
    let event = CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 2, wheel1: Int32(dy), wheel2: Int32(dx), wheel3: 0)
    event?.post(tap: .cghidEventTap)
    ok(["action": "computer.scroll", "platform": "Darwin", "executed": true, "direction": direction, "amount": amount, "driver": "mac_swift_host"])
}

func clipboardRead() -> Never {
    let pasteboard = NSPasteboard.general
    let content = pasteboard.string(forType: .string) ?? ""
    ok(["action": "computer.clipboard.read", "platform": "Darwin", "format": "text/plain", "content": content, "length": content.count, "driver": "mac_swift_host"])
}

func clipboardWrite(args: [String: Any]) -> Never {
    let content = stringValue(args["content"] ?? args["value"] ?? args["text"])
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(content, forType: .string)
    ok(["action": "computer.clipboard.write", "platform": "Darwin", "executed": true, "length": content.count, "driver": "mac_swift_host"])
}

func clipboardClear() -> Never {
    NSPasteboard.general.clearContents()
    ok(["action": "computer.clipboard.clear", "platform": "Darwin", "executed": true, "driver": "mac_swift_host"])
}

func doctor() -> Never {
    ok([
        "action": "computer.doctor",
        "platform": "Darwin",
        "host": hostVersion,
        "accessibility_trusted": AXIsProcessTrusted(),
        "screen_count": NSScreen.screens.count,
        "driver": "mac_swift_host"
    ])
}

do {
    let request = try readRequest()
    let action = stringValue(request["action"] ?? request["function_id"])
    let args = (request["args"] as? [String: Any]) ?? (request["payload"] as? [String: Any]) ?? request
    switch action {
    case "computer.doctor", "doctor":
        doctor()
    case "computer.apps", "apps":
        ok(["action": "computer.apps", "platform": "Darwin", "apps": runningApps(), "driver": "mac_swift_host"])
    case "computer.windows", "windows":
        ok(["action": "computer.windows", "platform": "Darwin", "windows": windowRecords(), "driver": "mac_swift_host"])
    case "computer.activate_app", "activate_app", "activate":
        activateApp(args: args)
    case "computer.screenshot", "screenshot":
        captureScreenshot(args: args)
    case "computer.observe", "observe":
        observe(args: args)
    case "computer.ax_tree", "ax_tree":
        axTree(args: args)
    case "computer.ocr", "ocr":
        ocr(args: args)
    case "computer.move", "move":
        move(args: args)
    case "computer.click", "click":
        click(args: args)
    case "computer.semantic_action", "semantic_action":
        semanticAction(args: args)
    case "computer.click_text", "click_text":
        semanticAction(args: args, actionName: "computer.click_text")
    case "computer.drag", "drag":
        drag(args: args)
    case "computer.type", "type":
        typeText(args: args)
    case "computer.key", "key":
        key(args: args)
    case "computer.scroll", "scroll":
        scroll(args: args)
    case "computer.clipboard.read", "clipboard", "clipboard_read":
        clipboardRead()
    case "computer.clipboard.write", "clipboard_write":
        clipboardWrite(args: args)
    case "computer.clipboard.clear", "clipboard_clear":
        clipboardClear()
    default:
        fail("UNSUPPORTED_ACTION", "Unsupported macOS computer action: \(action)")
    }
} catch {
    fail("HOST_EXCEPTION", String(describing: error))
}
