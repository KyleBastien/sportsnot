import Foundation

public enum AppGroup {
    public static let identifier = "group.com.sportsnot.widget"

    public static var defaults: UserDefaults {
        guard let d = UserDefaults(suiteName: identifier) else {
            preconditionFailure("App Group \(identifier) is not configured on this target. Enable it in Signing & Capabilities for both the App and Widget targets.")
        }
        return d
    }

    private enum Keys {
        static let featuredShareCode = "featuredShareCode"
        static let shareCodes = "shareCodes"
        static let lastSnapshot = "lastSnapshot"
        static let lastSnapshotAt = "lastSnapshotAt"
    }

    public static var featuredShareCode: String? {
        get { defaults.string(forKey: Keys.featuredShareCode) }
        set { defaults.set(newValue, forKey: Keys.featuredShareCode) }
    }

    /// All share codes the user has ever linked to this device, used to
    /// populate the widget configuration picker.
    public static var shareCodes: [String] {
        get { defaults.stringArray(forKey: Keys.shareCodes) ?? [] }
        set { defaults.set(newValue, forKey: Keys.shareCodes) }
    }

    public static func rememberShareCode(_ code: String) {
        var all = shareCodes
        if !all.contains(code) {
            all.append(code)
            shareCodes = all
        }
    }

    public static func cacheSnapshot(_ snapshot: WidgetSnapshot) throws {
        let data = try JSONEncoder().encode(snapshot)
        defaults.set(data, forKey: Keys.lastSnapshot)
        defaults.set(Date(), forKey: Keys.lastSnapshotAt)
    }

    public static func cachedSnapshot() -> (snapshot: WidgetSnapshot, stored: Date)? {
        guard let data = defaults.data(forKey: Keys.lastSnapshot),
              let snapshot = try? JSONDecoder().decode(WidgetSnapshot.self, from: data),
              let stored = defaults.object(forKey: Keys.lastSnapshotAt) as? Date
        else { return nil }
        return (snapshot, stored)
    }
}
