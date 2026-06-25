import AppKit
import CoreGraphics
import Foundation

struct HazeConfig {
    let preset: String
    let startColor: NSColor
    let endColor: NSColor
    let accentColor: NSColor
    let opacity: CGFloat
    let edgeWidth: CGFloat
    let speed: CGFloat
}

struct HazeLease: Decodable {
    let schema: String?
    let pid: Int?
    let sequence_id: String?
    let deadline_epoch: Double?
    let action: String?
    let active: Bool?
    let status_text: String?
    let virtual_pointer: VirtualPointerLease?
    let target_window: TargetWindowLease?
}

struct TargetWindowLease: Decodable {
    let app: String?
    let pid: Int?
    let window_id: Int?
    let window_title: String?
    let x: Double?
    let y: Double?
    let width: Double?
    let height: Double?
    let frame_window_ids: [Int]?
}

struct VirtualPointerLease: Decodable {
    let x: Double?
    let y: Double?
    let origin: String?
    let visible: Bool?
    let phase: String?
    let updated_at_epoch: Double?
    let expires_at_epoch: Double?
}

func env(_ key: String, _ fallback: String) -> String {
    let value = ProcessInfo.processInfo.environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return value.isEmpty ? fallback : value
}

func envCGFloat(_ key: String, _ fallback: CGFloat, min minimum: CGFloat, max maximum: CGFloat) -> CGFloat {
    guard let raw = ProcessInfo.processInfo.environment[key], let number = Double(raw) else {
        return fallback
    }
    return CGFloat(Swift.max(Double(minimum), Swift.min(Double(maximum), number)))
}

func colorFromHex(_ hex: String, alpha: CGFloat) -> NSColor {
    var value = hex.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    if value.hasPrefix("#") {
        value.removeFirst()
    }
    guard value.count == 6, let rgb = UInt64(value, radix: 16) else {
        return NSColor(calibratedRed: 0.43, green: 0.91, blue: 0.98, alpha: alpha)
    }
    return NSColor(
        calibratedRed: CGFloat((rgb >> 16) & 0xff) / 255.0,
        green: CGFloat((rgb >> 8) & 0xff) / 255.0,
        blue: CGFloat(rgb & 0xff) / 255.0,
        alpha: alpha
    )
}

func resolvedConfig() -> HazeConfig {
    let opacity = envCGFloat("RUMI_EDGE_HAZE_OPACITY", 0.36, min: 0.05, max: 0.9)
    let preset = env("RUMI_EDGE_HAZE_PRESET", "aurora")
    let fallback: (String, String, String)
    switch preset {
    case "ocean":
        fallback = ("#67E8F9", "#38BDF8", "#A5F3FC")
    case "ember":
        fallback = ("#FDBA74", "#FB7185", "#FDE68A")
    default:
        fallback = ("#6EE7F9", "#A78BFA", "#F0ABFC")
    }
    return HazeConfig(
        preset: preset,
        startColor: colorFromHex(env("RUMI_EDGE_HAZE_START_COLOR", fallback.0), alpha: opacity),
        endColor: colorFromHex(env("RUMI_EDGE_HAZE_END_COLOR", fallback.1), alpha: opacity),
        accentColor: colorFromHex(env("RUMI_EDGE_HAZE_ACCENT_COLOR", fallback.2), alpha: opacity * 0.86),
        opacity: opacity,
        edgeWidth: envCGFloat("RUMI_EDGE_HAZE_EDGE_WIDTH", 150, min: 40, max: 420),
        speed: envCGFloat("RUMI_EDGE_HAZE_SPEED", 1, min: 0.1, max: 4)
    )
}

func currentLease() -> HazeLease? {
    let path = env("RUMI_EDGE_HAZE_LEASE_PATH", "")
    let expectedSequenceID = env("RUMI_EDGE_HAZE_SEQUENCE_ID", "")
    if path.isEmpty || expectedSequenceID.isEmpty {
        return HazeLease(schema: "rumi.edge_haze_lease.v1", pid: nil, sequence_id: expectedSequenceID, deadline_epoch: Date().timeIntervalSince1970 + 60, action: nil, active: true, status_text: "作業中", virtual_pointer: nil, target_window: nil)
    }
    guard let data = FileManager.default.contents(atPath: path) else {
        return nil
    }
    guard let lease = try? JSONDecoder().decode(HazeLease.self, from: data) else {
        return nil
    }
    guard lease.schema == "rumi.edge_haze_lease.v1" else {
        return nil
    }
    guard lease.sequence_id == expectedSequenceID else {
        return nil
    }
    guard let deadline = lease.deadline_epoch else {
        return nil
    }
    return deadline >= Date().timeIntervalSince1970 ? lease : nil
}

func leaseIsCurrent() -> Bool {
    return currentLease() != nil
}

final class EdgeHazeWindow: NSWindow {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class EdgeHazeView: NSView {
    let config: HazeConfig
    let screenFrame: NSRect
    let startedAt = Date()

    init(frame frameRect: NSRect, screenFrame: NSRect, config: HazeConfig) {
        self.config = config
        self.screenFrame = screenFrame
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSColor.clear.setFill()
        dirtyRect.fill()

        guard let lease = currentLease(), let drawRect = targetWindowDrawRect(for: lease) else {
            return
        }

        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect: drawRect).addClip()

        let width = min(config.edgeWidth, min(drawRect.width, drawRect.height) * 0.42)
        let vertical = NSGradient(colors: [
            config.startColor,
            config.endColor.withAlphaComponent(config.opacity * 0.32),
            NSColor.clear
        ])
        let horizontal = NSGradient(colors: [
            config.endColor,
            config.accentColor.withAlphaComponent(config.opacity * 0.28),
            NSColor.clear
        ])

        vertical?.draw(in: NSRect(x: drawRect.minX, y: drawRect.minY, width: width, height: drawRect.height), angle: 0)
        vertical?.draw(in: NSRect(x: drawRect.maxX - width, y: drawRect.minY, width: width, height: drawRect.height), angle: 180)
        horizontal?.draw(in: NSRect(x: drawRect.minX, y: drawRect.maxY - width, width: drawRect.width, height: width), angle: 270)
        horizontal?.draw(in: NSRect(x: drawRect.minX, y: drawRect.minY, width: drawRect.width, height: width), angle: 90)

        let elapsed = CGFloat(Date().timeIntervalSince(startedAt)) * config.speed
        drawGlow(
            center: NSPoint(
                x: drawRect.minX + drawRect.width * (0.18 + 0.04 * sin(elapsed * 0.7)),
                y: drawRect.minY + drawRect.height * (0.22 + 0.05 * cos(elapsed * 0.9))
            ),
            radius: width * (1.05 + 0.08 * sin(elapsed)),
            color: config.accentColor
        )
        drawGlow(
            center: NSPoint(
                x: drawRect.minX + drawRect.width * (0.86 + 0.03 * cos(elapsed * 0.8)),
                y: drawRect.minY + drawRect.height * (0.72 + 0.05 * sin(elapsed * 0.65))
            ),
            radius: width * (1.22 + 0.1 * cos(elapsed * 0.9)),
            color: config.startColor
        )
        drawVirtualPointer(in: drawRect)
        drawStatusText(in: drawRect, lease: lease)
        NSGraphicsContext.restoreGraphicsState()
    }

    private func drawGlow(center: NSPoint, radius: CGFloat, color: NSColor) {
        let gradient = NSGradient(colors: [
            color.withAlphaComponent(config.opacity * 0.48),
            color.withAlphaComponent(config.opacity * 0.16),
            NSColor.clear
        ])
        gradient?.draw(
            fromCenter: center,
            radius: 0,
            toCenter: center,
            radius: radius,
            options: [.drawsBeforeStartingLocation, .drawsAfterEndingLocation]
        )
    }

    private func drawVirtualPointer(in area: NSRect) {
        guard let pointer = currentLease()?.virtual_pointer else {
            return
        }
        if pointer.visible == false {
            return
        }
        if let expiresAt = pointer.expires_at_epoch, expiresAt < Date().timeIntervalSince1970 {
            return
        }
        guard let screenPoint = screenPoint(for: pointer, in: area) else {
            return
        }

        let accent = NSColor(calibratedRed: 0.31, green: 0.85, blue: 1.0, alpha: 0.96)
        let shadow = NSColor.black.withAlphaComponent(0.42)
        let fill = NSColor.white.withAlphaComponent(0.96)

        let arrow = NSBezierPath()
        arrow.move(to: NSPoint(x: screenPoint.x, y: screenPoint.y))
        arrow.line(to: NSPoint(x: screenPoint.x + 18, y: screenPoint.y - 42))
        arrow.line(to: NSPoint(x: screenPoint.x + 25, y: screenPoint.y - 24))
        arrow.line(to: NSPoint(x: screenPoint.x + 43, y: screenPoint.y - 22))
        arrow.line(to: NSPoint(x: screenPoint.x, y: screenPoint.y))
        arrow.close()

        NSGraphicsContext.saveGraphicsState()
        shadow.setStroke()
        arrow.lineWidth = 5
        arrow.stroke()
        fill.setFill()
        arrow.fill()
        accent.setStroke()
        arrow.lineWidth = 2
        arrow.stroke()

        let ringRect = NSRect(x: screenPoint.x - 13, y: screenPoint.y - 13, width: 26, height: 26)
        accent.withAlphaComponent(0.20).setFill()
        NSBezierPath(ovalIn: ringRect).fill()
        accent.withAlphaComponent(0.88).setStroke()
        let ring = NSBezierPath(ovalIn: ringRect)
        ring.lineWidth = 2
        ring.stroke()

        let label = NSAttributedString(
            string: "AI",
            attributes: [
                .font: NSFont.systemFont(ofSize: 11, weight: .bold),
                .foregroundColor: NSColor.black.withAlphaComponent(0.78)
            ]
        )
        label.draw(at: NSPoint(x: screenPoint.x + 22, y: screenPoint.y - 41))
        NSGraphicsContext.restoreGraphicsState()
    }

    private func screenPoint(for pointer: VirtualPointerLease, in area: NSRect) -> NSPoint? {
        guard let x = pointer.x, let y = pointer.y else {
            return nil
        }
        let origin = (pointer.origin ?? "top_left").lowercased()
        let localX = CGFloat(x) - screenFrame.minX
        let localY: CGFloat
        if origin == "appkit_bottom_left" || origin == "bottom_left" {
            localY = CGFloat(y) - screenFrame.minY
        } else {
            localY = screenFrame.maxY - CGFloat(y)
        }
        let margin: CGFloat = 64
        if localX < area.minX - margin || localX > area.maxX + margin || localY < area.minY - margin || localY > area.maxY + margin {
            return nil
        }
        return NSPoint(x: localX, y: localY)
    }

    private func drawStatusText(in area: NSRect, lease: HazeLease) {
        let raw = lease.status_text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let text = raw.isEmpty ? fallbackStatusText(for: lease.action, active: lease.active ?? true) : raw
        if text.isEmpty {
            return
        }
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 15, weight: .semibold),
            .foregroundColor: NSColor.white.withAlphaComponent(0.92)
        ]
        let attributed = NSAttributedString(string: text, attributes: attrs)
        let textSize = attributed.size()
        let padX: CGFloat = 14
        let padY: CGFloat = 8
        let rect = NSRect(
            x: area.midX - (textSize.width + padX * 2) / 2,
            y: area.maxY - textSize.height - padY * 2 - 18,
            width: textSize.width + padX * 2,
            height: textSize.height + padY * 2
        )
        NSColor.black.withAlphaComponent(0.30).setFill()
        NSBezierPath(roundedRect: rect, xRadius: 12, yRadius: 12).fill()
        attributed.draw(at: NSPoint(x: rect.minX + padX, y: rect.minY + padY))
    }

    private func targetWindowDrawRect(for lease: HazeLease) -> NSRect? {
        guard let target = lease.target_window else {
            return nil
        }
        guard let targetRect = visibleTargetWindowRect(for: target) else {
            return nil
        }
        let clipped = targetRect.intersection(bounds)
        if clipped.isNull || clipped.isEmpty || clipped.width < 80 || clipped.height < 60 {
            return nil
        }
        return clipped
    }

    private func visibleTargetWindowRect(for target: TargetWindowLease) -> NSRect? {
        guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
            return nil
        }
        let frontmostPID = NSWorkspace.shared.frontmostApplication?.processIdentifier ?? 0
        var candidates: [(score: Int, area: CGFloat, rect: NSRect)] = []
        for info in windows {
            guard let ownerPID = intValue(info[kCGWindowOwnerPID as String]) else {
                continue
            }
            if frontmostPID > 0 && ownerPID != frontmostPID {
                continue
            }
            guard windowInfoMatches(info, target: target) else {
                continue
            }
            guard let rect = appKitRect(from: info[kCGWindowBounds as String]) else {
                continue
            }
            let clipped = rect.intersection(bounds)
            if clipped.isNull || clipped.isEmpty {
                continue
            }
            candidates.append((windowMatchScore(info, target: target), clipped.width * clipped.height, clipped))
        }
        return candidates.sorted { lhs, rhs in
            if lhs.score == rhs.score {
                return lhs.area > rhs.area
            }
            return lhs.score > rhs.score
        }.first?.rect
    }

    private func windowInfoMatches(_ info: [String: Any], target: TargetWindowLease) -> Bool {
        let layer = intValue(info[kCGWindowLayer as String]) ?? 0
        if layer != 0 {
            return false
        }
        let windowNumber = intValue(info[kCGWindowNumber as String]) ?? 0
        if let targetWindowID = target.window_id, targetWindowID > 0 {
            if windowNumber == targetWindowID || (target.frame_window_ids ?? []).contains(windowNumber) {
                return true
            }
        }
        let ownerPID = intValue(info[kCGWindowOwnerPID as String]) ?? 0
        if let targetPID = target.pid, targetPID > 0, ownerPID != targetPID {
            return false
        }
        let ownerName = stringValue(info[kCGWindowOwnerName as String])
        if let appName = target.app, !appName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !appNameMatches(appName, ownerName) {
            return false
        }
        let targetTitle = target.window_title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !targetTitle.isEmpty && target.pid == nil && target.window_id == nil {
            let windowTitle = stringValue(info[kCGWindowName as String])
            if !windowTitle.isEmpty && !windowTitle.localizedCaseInsensitiveContains(targetTitle) && !targetTitle.localizedCaseInsensitiveContains(windowTitle) {
                return false
            }
        }
        return target.pid != nil || target.window_id != nil || !(target.app ?? "").isEmpty || !targetTitle.isEmpty
    }

    private func windowMatchScore(_ info: [String: Any], target: TargetWindowLease) -> Int {
        var score = 0
        let windowNumber = intValue(info[kCGWindowNumber as String]) ?? 0
        if let targetWindowID = target.window_id, targetWindowID == windowNumber {
            score += 100
        }
        if (target.frame_window_ids ?? []).contains(windowNumber) {
            score += 80
        }
        let ownerPID = intValue(info[kCGWindowOwnerPID as String]) ?? 0
        if let targetPID = target.pid, targetPID == ownerPID {
            score += 40
        }
        if let appName = target.app, appNameMatches(appName, stringValue(info[kCGWindowOwnerName as String])) {
            score += 20
        }
        return score
    }

    private func appKitRect(from value: Any?) -> NSRect? {
        guard let bounds = value as? [String: Any] else {
            return nil
        }
        guard
            let x = doubleValue(bounds["X"]),
            let y = doubleValue(bounds["Y"]),
            let width = doubleValue(bounds["Width"]),
            let height = doubleValue(bounds["Height"]),
            width > 0,
            height > 0
        else {
            return nil
        }
        return NSRect(
            x: CGFloat(x) - screenFrame.minX,
            y: screenFrame.maxY - CGFloat(y + height),
            width: CGFloat(width),
            height: CGFloat(height)
        )
    }

    private func intValue(_ value: Any?) -> Int? {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let int = value as? Int {
            return int
        }
        if let string = value as? String {
            return Int(string)
        }
        return nil
    }

    private func doubleValue(_ value: Any?) -> Double? {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let double = value as? Double {
            return double
        }
        if let string = value as? String {
            return Double(string)
        }
        return nil
    }

    private func stringValue(_ value: Any?) -> String {
        return (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private func appNameMatches(_ left: String, _ right: String) -> Bool {
        let lhs = normalizedAppName(left)
        let rhs = normalizedAppName(right)
        if lhs.isEmpty || rhs.isEmpty {
            return false
        }
        return lhs == rhs || lhs.contains(rhs) || rhs.contains(lhs)
    }

    private func normalizedAppName(_ value: String) -> String {
        let lower = value.lowercased()
        let filtered = lower.unicodeScalars.map { scalar -> Character in
            CharacterSet.alphanumerics.contains(scalar) ? Character(scalar) : " "
        }
        return String(filtered).split(separator: " ").joined()
    }

    private func fallbackStatusText(for action: String?, active: Bool) -> String {
        if !active {
            return "考え中"
        }
        switch action ?? "" {
        case "computer.screenshot", "computer.observe":
            return "確認中"
        case "browser.open_url":
            return "移動中"
        case "computer.type", "computer.key", "computer.click", "computer.move", "computer.drag", "computer.scroll", "computer.semantic_action", "computer.pid_event":
            return "操作中"
        default:
            return "作業中"
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

let config = resolvedConfig()
var windows: [NSWindow] = []

for screen in NSScreen.screens {
    let window = EdgeHazeWindow(
        contentRect: screen.frame,
        styleMask: [.borderless],
        backing: .buffered,
        defer: false,
        screen: screen
    )
    window.backgroundColor = .clear
    window.isOpaque = false
    window.hasShadow = false
    window.ignoresMouseEvents = true
    window.level = .screenSaver
    window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
    window.contentView = EdgeHazeView(frame: NSRect(origin: .zero, size: screen.frame.size), screenFrame: screen.frame, config: config)
    window.orderFrontRegardless()
    windows.append(window)
}

Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { _ in
    for window in windows {
        window.contentView?.needsDisplay = true
    }
}

Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
    if !leaseIsCurrent() {
        app.terminate(nil)
    }
}

app.run()
