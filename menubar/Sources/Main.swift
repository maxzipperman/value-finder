import Foundation

/// Starts the menu-bar light, or with --selftest <url> fetches that address once,
/// prints what the light would show, and exits without creating any menu-bar item.
@main
struct Main {
    @MainActor
    static func main() {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if let flag = arguments.firstIndex(of: "--selftest") {
            let address = flag + 1 < arguments.count ? arguments[flag + 1] : nil
            exit(SelfTest.run(address))
        }
        ValueFinderLight.main()
    }
}

enum SelfTest {
    static let usage = """
        usage: ValueFinder --selftest http://127.0.0.1:<port>/<path>
        The self-test only asks addresses on 127.0.0.1.

        """

    /// Returns the exit status: 0 when a state was printed, 64 for a bad address.
    static func run(_ address: String?) -> Int32 {
        guard let address, let url = URL(string: address), Address.isLocal(url) else {
            FileHandle.standardError.write(Data(usage.utf8))
            return 64
        }
        let finished = DispatchSemaphore(value: 0)
        let result = ResultBox()
        SummaryFetcher().fetch(url) { outcome in
            result.set(outcome)
            finished.signal()
        }
        // The fetch has its own 10-second limit; this is only a backstop so it can never hang.
        let outcome: FetchOutcome
        if finished.wait(timeout: .now() + SummaryFetcher.timeoutSeconds + 20) == .timedOut {
            outcome = .notAnswering("no answer at all")
        } else {
            outcome = result.get() ?? .unreachable("no result")
        }
        print(DisplayState(outcome: outcome, checkedAt: Date()).selftestReport)
        return 0
    }
}

private final class ResultBox: @unchecked Sendable {
    private let lock = NSLock()
    private var outcome: FetchOutcome?

    func set(_ value: FetchOutcome) {
        lock.lock()
        outcome = value
        lock.unlock()
    }

    func get() -> FetchOutcome? {
        lock.lock()
        defer { lock.unlock() }
        return outcome
    }
}
