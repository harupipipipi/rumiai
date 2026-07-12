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

struct WindowSnapshot {
    let info: [String: Any]
    let windowNumber: Int
    let ownerPID: Int
    let ownerName: String
    let title: String
    let layer: Int
    let bounds: Any?
}

final class EdgeHazeController {
    private(set) var lease: HazeLease?
    private(set) var windows: [WindowSnapshot] = []
    private(set) var frontmostPID: Int = 0

    func poll() {
        lease = currentLease()
        frontmostPID = Int(NSWorkspace.shared.frontmostApplication?.processIdentifier ?? 0)
        windows = currentWindowSnapshot()
    }

    var leaseIsCurrent: Bool {
        return lease != nil
    }

    func targetWindowDrawRect(for lease: HazeLease, displayBounds: CGRect, viewBounds: NSRect) -> NSRect? {
        guard let target = lease.target_window else {
            return fallbackDrawRect(viewBounds)
        }
        guard let targetRect = visibleTargetWindowRect(for: target, displayBounds: displayBounds, viewBounds: viewBounds) else {
            return fallbackDrawRect(viewBounds)
        }
        let clipped = targetRect.intersection(viewBounds)
        if clipped.isNull || clipped.isEmpty || clipped.width < 80 || clipped.height < 60 {
            return fallbackDrawRect(viewBounds)
        }
        return clipped
    }

    private func visibleTargetWindowRect(for target: TargetWindowLease, displayBounds: CGRect, viewBounds: NSRect) -> NSRect? {
        var candidates: [(score: Int, area: CGFloat, rect: NSRect)] = []
        for snapshot in windows {
            guard windowInfoMatches(snapshot.info, target: target) else {
                continue
            }
            guard let rect = appKitRect(from: snapshot.bounds, displayBounds: displayBounds) else {
                continue
            }
            let clipped = rect.intersection(viewBounds)
            if clipped.isNull || clipped.isEmpty {
                continue
            }
            candidates.append((windowMatchScore(snapshot.info, target: target), clipped.width * clipped.height, clipped))
        }
        return candidates.sorted { lhs, rhs in
            if lhs.score == rhs.score {
                return lhs.area > rhs.area
            }
            return lhs.score > rhs.score
        }.first?.rect
    }

    private func fallbackDrawRect(_ viewBounds: NSRect) -> NSRect? {
        if viewBounds.isNull || viewBounds.isEmpty || viewBounds.width <= 0 || viewBounds.height <= 0 {
            return nil
        }
        return viewBounds
    }

    func installSelfTestState(lease: HazeLease?, windows: [WindowSnapshot], frontmostPID: Int) {
        self.lease = lease
        self.windows = windows
        self.frontmostPID = frontmostPID
    }

    private func currentWindowSnapshot() -> [WindowSnapshot] {
        guard let windowInfos = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
            return []
        }
        return windowInfos.compactMap { info in
            guard let ownerPID = intValue(info[kCGWindowOwnerPID as String]) else {
                return nil
            }
            return WindowSnapshot(
                info: info,
                windowNumber: intValue(info[kCGWindowNumber as String]) ?? 0,
                ownerPID: ownerPID,
                ownerName: stringValue(info[kCGWindowOwnerName as String]),
                title: stringValue(info[kCGWindowName as String]),
                layer: intValue(info[kCGWindowLayer as String]) ?? 0,
                bounds: info[kCGWindowBounds as String]
            )
        }
    }
}

final class EdgeHazeWindow: NSWindow {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class EdgeHazeView: NSView {
    let config: HazeConfig
    let displayBounds: CGRect
    let controller: EdgeHazeController
    let startedAt = Date()

    init(frame frameRect: NSRect, displayBounds: CGRect, config: HazeConfig, controller: EdgeHazeController) {
        self.config = config
        self.displayBounds = displayBounds
        self.controller = controller
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

        guard let lease = controller.lease, let drawRect = controller.targetWindowDrawRect(for: lease, displayBounds: displayBounds, viewBounds: bounds) else {
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
        drawVirtualPointer(in: drawRect, lease: lease)
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

    private func drawVirtualPointer(in area: NSRect, lease: HazeLease) {
        guard let pointer = lease.virtual_pointer else {
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
        let localX = CGFloat(x) - CGFloat(displayBounds.origin.x)
        let localY: CGFloat
        if origin == "appkit_bottom_left" || origin == "bottom_left" {
            localY = CGFloat(y) - CGFloat(displayBounds.origin.y)
        } else {
            localY = CGFloat(displayBounds.origin.y + displayBounds.height) - CGFloat(y)
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

func windowInfoMatches(_ info: [String: Any], target: TargetWindowLease) -> Bool {
    let layer = intValue(info[kCGWindowLayer as String]) ?? 0
    if layer != 0 {
        return false
    }
    let hasWindowID = (target.window_id ?? 0) > 0 || !(target.frame_window_ids ?? []).isEmpty
    let windowNumber = intValue(info[kCGWindowNumber as String]) ?? 0
    if hasWindowID {
        let acceptedIDs = Set(([target.window_id].compactMap { $0 } + (target.frame_window_ids ?? [])).filter { $0 > 0 })
        if !acceptedIDs.contains(windowNumber) {
            return false
        }
    }
    let ownerPID = intValue(info[kCGWindowOwnerPID as String]) ?? 0
    if let targetPID = target.pid, targetPID > 0, ownerPID != targetPID {
        return false
    }
    let appName = target.app?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !appName.isEmpty && !appNameMatches(appName, stringValue(info[kCGWindowOwnerName as String])) {
        return false
    }
    let targetTitle = target.window_title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !targetTitle.isEmpty {
        let windowTitle = stringValue(info[kCGWindowName as String])
        if windowTitle.isEmpty || !windowTitle.localizedCaseInsensitiveContains(targetTitle) {
            return false
        }
    }
    return hasWindowID || target.pid != nil || !appName.isEmpty || !targetTitle.isEmpty
}

func windowMatchScore(_ info: [String: Any], target: TargetWindowLease) -> Int {
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
    let targetTitle = target.window_title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !targetTitle.isEmpty && stringValue(info[kCGWindowName as String]).localizedCaseInsensitiveContains(targetTitle) {
        score += 10
    }
    return score
}

func appKitRect(from value: Any?, displayBounds: CGRect) -> NSRect? {
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
        x: CGFloat(x - Double(displayBounds.origin.x)),
        y: CGFloat(Double(displayBounds.origin.y + displayBounds.height) - (y + height)),
        width: CGFloat(width),
        height: CGFloat(height)
    )
}

func displayBounds(for screen: NSScreen) -> CGRect {
    if let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber {
        let displayID = CGDirectDisplayID(number.uint32Value)
        let bounds = CGDisplayBounds(displayID)
        if bounds.width > 0 && bounds.height > 0 {
            return bounds
        }
    }
    return CGRect(x: screen.frame.origin.x, y: screen.frame.origin.y, width: screen.frame.width, height: screen.frame.height)
}

func intValue(_ value: Any?) -> Int? {
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

func doubleValue(_ value: Any?) -> Double? {
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

func stringValue(_ value: Any?) -> String {
    return (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}

func appNameMatches(_ left: String, _ right: String) -> Bool {
    let lhs = normalizedAppName(left)
    let rhs = normalizedAppName(right)
    if lhs.isEmpty || rhs.isEmpty {
        return false
    }
    if lhs == rhs {
        return true
    }
    let aliases: [String: Set<String>] = [
        "googlechrome": ["chrome"],
        "microsoftedge": ["edge", "msedge"],
        "bravebrowser": ["brave"],
        "operagx": ["opera"]
    ]
    return aliases[lhs]?.contains(rhs) == true || aliases[rhs]?.contains(lhs) == true
}

func normalizedAppName(_ value: String) -> String {
    let lower = value.lowercased()
    let withoutSuffix = lower.hasSuffix(".app") ? String(lower.dropLast(4)) : lower
    let filtered = withoutSuffix.unicodeScalars.map { scalar -> Character in
        CharacterSet.alphanumerics.contains(scalar) ? Character(scalar) : " "
    }
    return String(filtered).split(separator: " ").joined()
}

func runSelfTests() {
    let baseWindow: [String: Any] = [
        kCGWindowLayer as String: 0,
        kCGWindowNumber as String: 101,
        kCGWindowOwnerPID as String: 222,
        kCGWindowOwnerName as String: "Vivaldi",
        kCGWindowName as String: "Google - Vivaldi",
        kCGWindowBounds as String: ["X": 10, "Y": 20, "Width": 800, "Height": 600],
    ]
    let samePIDOtherWindow: [String: Any] = [
        kCGWindowLayer as String: 0,
        kCGWindowNumber as String: 102,
        kCGWindowOwnerPID as String: 222,
        kCGWindowOwnerName as String: "Vivaldi",
        kCGWindowName as String: "Settings",
        kCGWindowBounds as String: ["X": 20, "Y": 30, "Width": 900, "Height": 700],
    ]
    let target = TargetWindowLease(app: "Vivaldi", pid: 222, window_id: 101, window_title: "Google", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)
    precondition(windowInfoMatches(baseWindow, target: target), "exact target should match")
    precondition(!windowInfoMatches(samePIDOtherWindow, target: target), "same PID with different window id/title must not match")
    precondition(!windowInfoMatches(baseWindow, target: TargetWindowLease(app: "Safari", pid: 222, window_id: 101, window_title: "Google", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)), "app mismatch must fail")
    precondition(!windowInfoMatches(baseWindow, target: TargetWindowLease(app: "Vivaldi", pid: 333, window_id: 101, window_title: "Google", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)), "PID mismatch must fail")
    precondition(!windowInfoMatches(baseWindow, target: TargetWindowLease(app: "Vivaldi", pid: 222, window_id: 999, window_title: "Google", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)), "window id mismatch must fail")
    precondition(!windowInfoMatches(baseWindow, target: TargetWindowLease(app: "Vivaldi", pid: 222, window_id: 101, window_title: "Mail", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)), "title mismatch must fail")

    let displays = [
        CGRect(x: 0, y: 0, width: 1440, height: 900),
        CGRect(x: 1440, y: 0, width: 1080, height: 1920),
        CGRect(x: 0, y: -1200, width: 1600, height: 1200),
        CGRect(x: -1280, y: 200, width: 1280, height: 1024),
    ]
    for display in displays {
        let rect = appKitRect(from: ["X": display.origin.x + 10, "Y": display.origin.y + 20, "Width": 200, "Height": 100], displayBounds: display)
        precondition(rect == NSRect(x: 10, y: display.height - 120, width: 200, height: 100), "display-local rect conversion failed")
    }

    let controller = EdgeHazeController()
    let displayBounds = CGRect(x: 0, y: 0, width: 1440, height: 900)
    let viewBounds = NSRect(x: 0, y: 0, width: 1440, height: 900)
    let backgroundWindow = WindowSnapshot(
        info: baseWindow,
        windowNumber: 101,
        ownerPID: 222,
        ownerName: "Vivaldi",
        title: "Google - Vivaldi",
        layer: 0,
        bounds: baseWindow[kCGWindowBounds as String]
    )
    let targetedLease = HazeLease(schema: "rumi.edge_haze_lease.v1", pid: nil, sequence_id: "self-test", deadline_epoch: Date().timeIntervalSince1970 + 60, action: "computer.type", active: true, status_text: nil, virtual_pointer: nil, target_window: target)
    controller.installSelfTestState(lease: targetedLease, windows: [backgroundWindow], frontmostPID: 999)
    let targetedRect = controller.targetWindowDrawRect(for: targetedLease, displayBounds: displayBounds, viewBounds: viewBounds)
    precondition(targetedRect == NSRect(x: 10, y: 280, width: 800, height: 600), "visible non-frontmost target should draw target rect")

    let untargetedLease = HazeLease(schema: "rumi.edge_haze_lease.v1", pid: nil, sequence_id: "self-test", deadline_epoch: Date().timeIntervalSince1970 + 60, action: "browser.open_url", active: true, status_text: nil, virtual_pointer: nil, target_window: nil)
    let fallbackRect = controller.targetWindowDrawRect(for: untargetedLease, displayBounds: displayBounds, viewBounds: viewBounds)
    precondition(fallbackRect == viewBounds, "untargeted lease should draw full-screen fallback")

    let missingTarget = TargetWindowLease(app: "Safari", pid: 333, window_id: 999, window_title: "Missing", x: nil, y: nil, width: nil, height: nil, frame_window_ids: nil)
    let missingLease = HazeLease(schema: "rumi.edge_haze_lease.v1", pid: nil, sequence_id: "self-test", deadline_epoch: Date().timeIntervalSince1970 + 60, action: "computer.type", active: true, status_text: nil, virtual_pointer: nil, target_window: missingTarget)
    let missingFallbackRect = controller.targetWindowDrawRect(for: missingLease, displayBounds: displayBounds, viewBounds: viewBounds)
    precondition(missingFallbackRect == viewBounds, "missing target should draw full-screen fallback")
}

if CommandLine.arguments.contains("--self-test") {
    runSelfTests()
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

let config = resolvedConfig()
let controller = EdgeHazeController()
controller.poll()
var windows: [NSWindow] = []

for screen in NSScreen.screens {
    let displayBounds = displayBounds(for: screen)
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
    window.contentView = EdgeHazeView(
        frame: NSRect(origin: .zero, size: screen.frame.size),
        displayBounds: displayBounds,
        config: config,
        controller: controller
    )
    window.orderFrontRegardless()
    windows.append(window)
}

Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { _ in
    controller.poll()
    if !controller.leaseIsCurrent {
        app.terminate(nil)
        return
    }
    for window in windows {
        window.contentView?.needsDisplay = true
    }
}

Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
    if !controller.leaseIsCurrent {
        app.terminate(nil)
    }
}

app.run()
