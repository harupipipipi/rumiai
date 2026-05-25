import AppKit
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

func leaseIsCurrent() -> Bool {
    let path = env("RUMI_EDGE_HAZE_LEASE_PATH", "")
    let expectedSequenceID = env("RUMI_EDGE_HAZE_SEQUENCE_ID", "")
    if path.isEmpty || expectedSequenceID.isEmpty {
        return true
    }
    guard let data = FileManager.default.contents(atPath: path) else {
        return false
    }
    guard let lease = try? JSONDecoder().decode(HazeLease.self, from: data) else {
        return false
    }
    guard lease.schema == "rumi.edge_haze_lease.v1" else {
        return false
    }
    guard lease.sequence_id == expectedSequenceID else {
        return false
    }
    guard let deadline = lease.deadline_epoch else {
        return false
    }
    return deadline >= Date().timeIntervalSince1970
}

final class EdgeHazeWindow: NSWindow {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class EdgeHazeView: NSView {
    let config: HazeConfig
    let startedAt = Date()

    init(frame frameRect: NSRect, config: HazeConfig) {
        self.config = config
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

        let bounds = self.bounds
        let width = min(config.edgeWidth, min(bounds.width, bounds.height) * 0.42)
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

        vertical?.draw(in: NSRect(x: 0, y: 0, width: width, height: bounds.height), angle: 0)
        vertical?.draw(in: NSRect(x: bounds.maxX - width, y: 0, width: width, height: bounds.height), angle: 180)
        horizontal?.draw(in: NSRect(x: 0, y: bounds.maxY - width, width: bounds.width, height: width), angle: 270)
        horizontal?.draw(in: NSRect(x: 0, y: 0, width: bounds.width, height: width), angle: 90)

        let elapsed = CGFloat(Date().timeIntervalSince(startedAt)) * config.speed
        drawGlow(
            center: NSPoint(x: bounds.width * (0.18 + 0.04 * sin(elapsed * 0.7)), y: bounds.height * (0.22 + 0.05 * cos(elapsed * 0.9))),
            radius: width * (1.05 + 0.08 * sin(elapsed)),
            color: config.accentColor
        )
        drawGlow(
            center: NSPoint(x: bounds.width * (0.86 + 0.03 * cos(elapsed * 0.8)), y: bounds.height * (0.72 + 0.05 * sin(elapsed * 0.65))),
            radius: width * (1.22 + 0.1 * cos(elapsed * 0.9)),
            color: config.startColor
        )
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
    window.contentView = EdgeHazeView(frame: NSRect(origin: .zero, size: screen.frame.size), config: config)
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
