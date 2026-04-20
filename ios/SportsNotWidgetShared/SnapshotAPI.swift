import Foundation

public struct SnapshotAPIConfig: Sendable {
    public let supabaseURL: URL
    public let anonKey: String

    public init(supabaseURL: URL, anonKey: String) {
        self.supabaseURL = supabaseURL
        self.anonKey = anonKey
    }

    /// Reads SUPABASE_URL / SUPABASE_ANON_KEY from the target's Info.plist.
    /// These keys are wired via an Xcode build phase from environment
    /// variables at build time so the anon key never lives in source control.
    public static func fromBundle(_ bundle: Bundle = .main) -> SnapshotAPIConfig? {
        guard
            let urlString = bundle.object(forInfoDictionaryKey: "SUPABASE_URL") as? String,
            !urlString.isEmpty,
            // Reject unsubstituted Info.plist macros like "$(SUPABASE_URL)" —
            // these slip through when the build setting self-references and
            // Xcode resolves it to an empty / literal value. URL(string:) is
            // permissive enough to accept the literal so we have to guard
            // explicitly or the network call fails opaquely on-device.
            !urlString.contains("$("),
            urlString.hasPrefix("http"),
            let url = URL(string: urlString),
            let key = bundle.object(forInfoDictionaryKey: "SUPABASE_ANON_KEY") as? String,
            !key.isEmpty,
            !key.contains("$(")
        else { return nil }
        return SnapshotAPIConfig(supabaseURL: url, anonKey: key)
    }
}

public enum SnapshotAPIError: Error, Sendable {
    case missingConfig
    case badStatus(Int, String)
    case decoding(Error)
    case transport(Error)
}

public struct SnapshotAPI: Sendable {
    public let config: SnapshotAPIConfig
    public var session: URLSession

    public init(config: SnapshotAPIConfig, session: URLSession = .shared) {
        self.config = config
        self.session = session
    }

    public func fetchSnapshot(shareCode: String, date: String? = nil) async throws -> WidgetSnapshot {
        var components = URLComponents(
            url: config.supabaseURL.appendingPathComponent("functions/v1/widget-league-snapshot"),
            resolvingAgainstBaseURL: false
        )!
        var items = [URLQueryItem(name: "shareCode", value: shareCode)]
        if let date { items.append(URLQueryItem(name: "date", value: date)) }
        components.queryItems = items

        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        request.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw SnapshotAPIError.transport(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw SnapshotAPIError.badStatus(-1, "No HTTPURLResponse")
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw SnapshotAPIError.badStatus(http.statusCode, body)
        }

        do {
            return try JSONDecoder().decode(WidgetSnapshot.self, from: data)
        } catch {
            throw SnapshotAPIError.decoding(error)
        }
    }
}
