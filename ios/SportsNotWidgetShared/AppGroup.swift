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
        static let myTeamNames = "myTeamNamesByShareCode"
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

    /// Per-league mapping of share code → the current user's `team_name`
    /// within that league. Used by the widget to compute the user's own
    /// fantasy total against an otherwise league-wide snapshot.
    public static var myTeamNamesByShareCode: [String: String] {
        get {
            (defaults.dictionary(forKey: Keys.myTeamNames) as? [String: String]) ?? [:]
        }
        set { defaults.set(newValue, forKey: Keys.myTeamNames) }
    }

    public static func myTeamName(forShareCode code: String) -> String? {
        myTeamNamesByShareCode[code]
    }

    public static func setMyTeamName(_ name: String?, forShareCode code: String) {
        var map = myTeamNamesByShareCode
        if let name, !name.isEmpty {
            map[code] = name
        } else {
            map.removeValue(forKey: code)
        }
        myTeamNamesByShareCode = map
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

    /// Returns the cached snapshot only if it was stored within `maxAge`
    /// seconds. Used by the widget extension to avoid showing yesterday's
    /// data when both fresh fetches and recent app-primed cache are absent.
    public static func cachedSnapshot(maxAge: TimeInterval) -> (snapshot: WidgetSnapshot, stored: Date)? {
        guard let cached = cachedSnapshot() else { return nil }
        guard Date().timeIntervalSince(cached.stored) <= maxAge else { return nil }
        return cached
    }

    /// Age in seconds of the most recently cached snapshot, or nil if none.
    public static var cachedSnapshotAge: TimeInterval? {
        guard let stored = defaults.object(forKey: Keys.lastSnapshotAt) as? Date else { return nil }
        return Date().timeIntervalSince(stored)
    }
}
