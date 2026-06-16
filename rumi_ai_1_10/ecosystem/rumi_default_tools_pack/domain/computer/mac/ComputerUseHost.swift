import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

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

func captureScreenshot(args: [String: Any]) -> Never {
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
        fail("SCREENSHOT_FAILED", "screencapture failed for the requested macOS image.")
    }
    let size = imageSize(path)
    ok([
        "action": "computer.screenshot",
        "platform": "Darwin",
        "path": path,
        "width": size.width,
        "height": size.height,
        "method": "swift_screencapture",
        "coordinate_system": "screen_pixels",
        "driver": "mac_swift_host",
        "target_window": target
    ])
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
    case "computer.screenshot", "screenshot", "computer.observe", "observe":
        captureScreenshot(args: args)
    case "computer.move", "move":
        move(args: args)
    case "computer.click", "click":
        click(args: args)
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
