import Foundation
import os.log

/// Lightweight telemetry shared between the App and Widget extension.
///
/// Goals:
///   1. **Console.app observability** — every event is mirrored to `os_log`
///      under subsystem `com.sportsnot.app`, category `WidgetTelemetry`.
///      Connect the iPhone to a Mac via USB and filter on the subsystem
///      to see every decision the widget pipeline makes in real time.
///   2. **No external dependencies / no hardcoded credentials** — this
///      path must work even when `SUPABASE_URL` / `SUPABASE_ANON_KEY` in
///      Info.plist are broken (which is the precise failure mode we're
///      trying to diagnose). So we deliberately avoid network I/O here.
///   3. **In-process ring buffer** — events are also appended to a bounded
///      ring buffer in App Group `UserDefaults`. The App can read this
///      buffer on launch to surface widget-side events that happened
///      while the App wasn't running, without requiring the user to grab
///      device logs.
public enum WidgetTelemetry {
    private static let log = OSLog(subsystem: "com.sportsnot.app", category: "WidgetTelemetry")
    private static let bufferKey = "widgetTelemetryEvents.v1"
    /// Cap the buffer so a misbehaving extension can't fill App Group
    /// storage. ~200 events is enough to cover several timeline cycles
    /// while staying well under the 1 MB UserDefaults soft limit.
    public static let maxEvents = 200

    /// Identifies which target produced the event. Inferred from the
    /// bundle identifier so callers don't have to thread a target tag
    /// through every call site.
    public static var target: String {
        let bid = Bundle.main.bundleIdentifier ?? "unknown"
        if bid.contains("Widget") || bid.contains("widget") { return "widget" }
        return "app"
    }

    public struct Event: Codable, Sendable {
        public let timestamp: Date
        public let target: String
        public let name: String
        public let context: [String: String]
    }

    /// Records a structured event. Safe to call from any thread; never
    /// throws and never blocks on the network.
    public static func record(_ name: String, _ context: [String: String] = [:]) {
        let event = Event(
            timestamp: Date(),
            target: target,
            name: name,
            context: context
        )

        // 1. Mirror to os_log so the event is visible in Console.app the
        //    instant it happens. Use %{public}@ so the message isn't
        //    redacted on a production build, and `.default` level so the
        //    line shows up in Console without the user having to toggle
        //    "Include Info Messages" first (`.info` is hidden by default).
        os_log(
            "%{public}@ | %{public}@ | %{public}@",
            log: log,
            type: .default,
            event.target,
            event.name,
            formatContext(context)
        )

        // 2. Append to the App Group ring buffer for later inspection.
        //    Wrapped in a do/catch-equivalent so any encoding failure can
        //    never break the actual widget code path.
        guard let defaults = UserDefaults(suiteName: AppGroup.identifier) else { return }
        var existing: [Event] = []
        if let data = defaults.data(forKey: bufferKey),
           let decoded = try? JSONDecoder().decode([Event].self, from: data) {
            existing = decoded
        }
        existing.append(event)
        if existing.count > maxEvents {
            existing.removeFirst(existing.count - maxEvents)
        }
        if let encoded = try? JSONEncoder().encode(existing) {
            defaults.set(encoded, forKey: bufferKey)
        }
    }

    /// Returns the most recent events from the ring buffer (newest last).
    /// Use from the App to display / share widget diagnostics.
    public static func recent(limit: Int = maxEvents) -> [Event] {
        guard
            let defaults = UserDefaults(suiteName: AppGroup.identifier),
            let data = defaults.data(forKey: bufferKey),
            let decoded = try? JSONDecoder().decode([Event].self, from: data)
        else { return [] }
        if decoded.count <= limit { return decoded }
        return Array(decoded.suffix(limit))
    }

    /// Clears the ring buffer. Useful when reproducing a bug to start
    /// from a clean slate.
    public static func clear() {
        UserDefaults(suiteName: AppGroup.identifier)?.removeObject(forKey: bufferKey)
    }

    // MARK: - Helpers

    /// Sanitizes a SUPABASE-style value for telemetry: never logs the
    /// actual content, just enough metadata to diagnose substitution
    /// problems (presence, length, whether it looks like an
    /// unsubstituted Info.plist macro).
    public static func describe(_ value: String?) -> [String: String] {
        guard let value else { return ["present": "false"] }
        return [
            "present": "true",
            "length": String(value.count),
            "isMacro": value.contains("$(") ? "true" : "false",
            "hasHttpPrefix": value.hasPrefix("http") ? "true" : "false",
            "isEmpty": value.isEmpty ? "true" : "false",
        ]
    }

    private static func formatContext(_ context: [String: String]) -> String {
        if context.isEmpty { return "{}" }
        // Sort keys so log lines are easy to diff across runs.
        let pairs = context.keys.sorted().map { "\($0)=\(context[$0] ?? "")" }
        return "{\(pairs.joined(separator: " "))}"
    }
}
