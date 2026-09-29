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
    /// a redirect, text that is not JSON, a missing field, a wrong type, or an answer
    /// too large or too deeply nested to read).
    case unreadable(String)
}

/// Asks one local address for the summary with a plain GET. It keeps no cache and no cookies,
/// ignores any system proxy, never follows a redirect, refuses any address that is not
/// http on 127.0.0.1, and stops reading an answer as soon as it passes 256 KB, so a large
/// answer never fills memory.
final class SummaryFetcher: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    static let timeoutSeconds: TimeInterval = 10
    static let largestAnswer = 256 * 1024

    /// One request in flight: the bytes received so far, the reason it was stopped early
    /// (if it was), and what to call when it ends. Touched only on the session's own queue,
    /// which runs one thing at a time, except when `fetch` files it under `lock`.
    private final class Pending: @unchecked Sendable {
        let completion: @Sendable (FetchOutcome) -> Void
        var data = Data()
        var stopped: FetchOutcome?

        init(_ completion: @escaping @Sendable (FetchOutcome) -> Void) {
            self.completion = completion
        }
    }

    private var session: URLSession?
    private let lock = NSLock()
    private var pending: [Int: Pending] = [:]

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
        // A task without a completion handler, so the answer arrives piece by piece through
        // the delegate methods below and can be cut off at 256 KB.
        let task = session.dataTask(with: request)
        lock.lock()
        pending[task.taskIdentifier] = Pending(completion)
        lock.unlock()
        task.resume()
    }

    private func entry(for task: URLSessionTask, remove: Bool = false) -> Pending? {
        lock.lock()
        defer { lock.unlock() }
        return remove ? pending.removeValue(forKey: task.taskIdentifier) : pending[task.taskIdentifier]
    }

    private static let tooLarge = FetchOutcome.unreadable(
        "the answer was larger than \(largestAnswer / 1024) KB, so the light stopped reading it")

    /// The status and length arrive before the body: stop here for anything but a 200,
    /// or for a body that says it is larger than 256 KB.
    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping @Sendable (URLSession.ResponseDisposition) -> Void
    ) {
        let stop: FetchOutcome?
        if let http = response as? HTTPURLResponse {
            if http.statusCode != 200 {
                stop = .unreadable("it answered with HTTP status \(http.statusCode), not 200")
            } else if response.expectedContentLength > Int64(Self.largestAnswer) {
                stop = Self.tooLarge
            } else {
                stop = nil
            }
        } else {
            stop = .unreadable("the answer was not an HTTP response")
        }
        if let stop {
            entry(for: dataTask)?.stopped = stop
            completionHandler(.cancel)
        } else {
            completionHandler(.allow)
        }
    }

    /// Each piece of the body: keep it, unless the total passes 256 KB, and then stop reading.
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let entry = entry(for: dataTask), entry.stopped == nil else { return }
        if entry.data.count + data.count > Self.largestAnswer {
            entry.stopped = Self.tooLarge
            entry.data = Data()
            dataTask.cancel()
        } else {
            entry.data.append(data)
        }
    }

    /// The request is over, finished, failed or stopped: work out the outcome, once.
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let entry = entry(for: task, remove: true) else { return }
        if let stopped = entry.stopped {
            entry.completion(stopped)
        } else {
            entry.completion(Self.outcome(data: entry.data, response: task.response, error: error))
        }
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
        guard let data, !data.isEmpty else {
            return .unreadable("the answer was empty")
        }
        guard data.count <= largestAnswer else {
            return tooLarge
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
