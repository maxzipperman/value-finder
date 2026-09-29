import Foundation

/// The only two addresses this app uses. They are fixed here and nowhere else.
enum Address {
    /// The dashboard's summary, asked once a minute.
    static let summary = URL(string: "http://127.0.0.1:8787/api/summary")!

    /// The dashboard's home page, opened in the default browser by "Open dashboard".
    static let dashboard = URL(string: "http://127.0.0.1:8787/")!

    /// True only for plain http on this Mac's own loopback address, 127.0.0.1.
    /// The fetcher refuses anything else, so the app can never reach another machine,
    /// even from the self-test, which takes its address from the command line.
    static func isLocal(_ url: URL) -> Bool {
        guard let parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return false }
        return parts.scheme == "http"
            && parts.host == "127.0.0.1"
            && parts.user == nil
            && parts.password == nil
    }
}
