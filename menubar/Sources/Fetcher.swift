import Foundation

/// The result of one attempt to ask the dashboard for its summary.
enum FetchOutcome: Equatable, Sendable {
    /// A summary that passed every check.
    case summary(Summary)
    /// Nothing is listening at the address: the dashboard is not running.
    case notRunning(String)
    /// Something is listening but gave no answer in time.
    case notAnswering(String)
    /// Any other failure to connect.
    case unreachable(String)
    /// It answered, but not with a summary the light can use (an HTTP error,
    /// a redirect, text that is not JSON, a missing field or a wrong type).
    case unreadable(String)
}

/// Asks one local address for the summary with a plain GET. It keeps no cache and no cookies,
/// ignores any system proxy, never follows a redirect, and refuses any address that is not
/// http on 127.0.0.1.
final class SummaryFetcher: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    static let timeoutSeconds: TimeInterval = 10
    static let largestAnswer = 256 * 1024

    private var session: URLSession?

    override init() {
        super.init()
        let config = URLSessionConfiguration.ephemeral
        config.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.httpCookieAcceptPolicy = .never
        config.urlCredentialStorage = nil
        config.timeoutIntervalForRequest = Self.timeoutSeconds
        config.timeoutIntervalForResource = Self.timeoutSeconds
        config.waitsForConnectivity = false
        config.httpMaximumConnectionsPerHost = 1
        // Connect directly, never through a proxy on another machine.
        config.connectionProxyDictionary = [
            kCFNetworkProxiesHTTPEnable as String: false,
            kCFNetworkProxiesHTTPSEnable as String: false,
            kCFNetworkProxiesSOCKSEnable as String: false,
            kCFNetworkProxiesProxyAutoConfigEnable as String: false,
            kCFNetworkProxiesProxyAutoDiscoveryEnable as String: false,
        ]
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        session = URLSession(configuration: config, delegate: self, delegateQueue: queue)
    }

    /// Calls `completion` exactly once, on a background queue.
    func fetch(_ url: URL, completion: @escaping @Sendable (FetchOutcome) -> Void) {
        guard Address.isLocal(url), let session else {
            completion(.unreachable("the address is not http on 127.0.0.1, so it was not asked"))
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.httpShouldHandleCookies = false
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = Self.timeoutSeconds
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        session.dataTask(with: request) { data, response, error in
            completion(Self.outcome(data: data, response: response, error: error))
        }.resume()
    }

    static func outcome(data: Data?, response: URLResponse?, error: Error?) -> FetchOutcome {
        if let error = error as? URLError {
            switch error.code {
            case .cannotConnectToHost:
                return .notRunning("nothing is listening at that address (connection refused)")
            case .timedOut:
                return .notAnswering("no answer within \(Int(timeoutSeconds)) seconds")
            default:
                return .unreachable("the connection failed (error \(error.code.rawValue))")
            }
        }
        if error != nil {
            return .unreachable("the connection failed")
        }
        guard let http = response as? HTTPURLResponse else {
            return .unreadable("the answer was not an HTTP response")
        }
        guard http.statusCode == 200 else {
            return .unreadable("it answered with HTTP status \(http.statusCode), not 200")
        }
        guard let data, data.count <= largestAnswer else {
            return .unreadable("the answer was empty or larger than \(largestAnswer / 1024) KB")
        }
        switch Summary.parse(data) {
        case .success(let summary):
            return .summary(summary)
        case .failure(let problem):
            return .unreadable(problem.detail)
        }
    }

    /// Never follow a redirect: the 3xx answer itself comes back and is treated as unreadable.
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}
