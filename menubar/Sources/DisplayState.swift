import Foundation

/// The colour of the dot beside the wind symbol.
enum Dot: String, Sendable {
    case green, amber, red, gray
}

/// One line of the menu. The real menu and the self-test both print this list,
/// so what the self-test shows is what the menu shows.
enum MenuLine: Equatable, Sendable {
    case text(String)
    case separator
    case openDashboard
    case quit

    static let openDashboardTitle = "Open dashboard"
    static let quitTitle = "Quit"
}

/// Everything the menu-bar light shows, worked out from one fetch.
struct DisplayState: Equatable, Sendable {
    let dot: Dot
    /// The number beside the icon, or nil for none.
    let number: Int?
    let menu: [MenuLine]
    /// Read out by VoiceOver and shown as the icon's description.
    let spoken: String
    /// Why the dashboard could not be used. Printed by the self-test only, never in the menu.
    let detail: String?

    static let mostProblemLines = 8
    static let longestProblem = 160

    /// What shows for the moment between launch and the first answer.
    static let starting = DisplayState(
        dot: .gray,
        number: nil,
        menu: [.text("Checking the dashboard."), .separator, .openDashboard, .separator, .quit],
        spoken: "Value Finder: checking the dashboard.",
        detail: nil
    )

    init(dot: Dot, number: Int?, menu: [MenuLine], spoken: String, detail: String?) {
        self.dot = dot
        self.number = number
        self.menu = menu
        self.spoken = spoken
        self.detail = detail
    }

    init(outcome: FetchOutcome, checkedAt: Date, timeZone: TimeZone = .autoupdatingCurrent) {
        let checked = MenuLine.text("Checked at " + Clock.twelveHour(checkedAt, timeZone: timeZone))
        let footer: [MenuLine] = [.separator, .openDashboard, checked, .separator, .quit]

        switch outcome {
        case .summary(let summary):
            let headline = Self.headline(summary)
            var lines: [MenuLine] = [
                .text(headline),
                .text("Next alert run at " + Clock.twelveHour(hhmm: summary.nextRunLocal)),
                .text("Credits left: " + (summary.creditsRemaining.map(Self.grouped) ?? "not known")),
            ]
            let problems = Self.problemLines(summary.problems)
            if !problems.isEmpty {
                lines.append(.separator)
                lines += problems.map(MenuLine.text)
            }
            self.init(
                dot: Self.dot(for: summary.health),
                number: summary.signalsLive > 0 ? summary.signalsLive : nil,
                menu: lines + footer,
                spoken: "Value Finder: " + headline,
                detail: nil
            )

        case .notRunning(let why):
            self.init(unusable: "The dashboard is not running.", extra: nil, why: why, footer: footer)
        case .notAnswering(let why):
            self.init(unusable: "The dashboard is not answering.", extra: nil, why: why, footer: footer)
        case .unreachable(let why):
            self.init(unusable: "The dashboard cannot be reached.", extra: nil, why: why, footer: footer)
        case .unreadable(let why):
            self.init(unusable: "The dashboard cannot be reached.",
                      extra: "Its answer could not be read.", why: why, footer: footer)
        }
    }

    private init(unusable headline: String, extra: String?, why: String, footer: [MenuLine]) {
        var lines: [MenuLine] = [.text(headline)]
        if let extra { lines.append(.text(extra)) }
        self.init(dot: .gray, number: nil, menu: lines + footer,
                  spoken: "Value Finder: " + headline, detail: why)
    }

    static func dot(for health: Summary.Health) -> Dot {
        switch health {
        case .ok: return .green
        case .warn: return .amber
        case .fail: return .red
        }
    }

    static func headline(_ summary: Summary) -> String {
        let signals: String
        switch summary.signalsLive {
        case 0: signals = "No signals."
        case 1: signals = "1 signal is live."
        default: signals = "\(summary.signalsLive) signals are live."
        }
        switch summary.health {
        case .ok: return summary.signalsLive == 0 ? "All jobs ran. No signals." : signals
        case .warn: return "Something needs a look. " + signals
        case .fail: return "A scheduled job has a problem. " + signals
        }
    }

    /// Each problem on its own line: control characters become spaces, blank ones are dropped,
    /// a very long one is shortened, and after eight the rest are counted instead of listed.
    static func problemLines(_ problems: [String]) -> [String] {
        let cleaned = problems
            .map { text in
                String(String.UnicodeScalarView(text.unicodeScalars.map {
                    CharacterSet.controlCharacters.contains($0) ? " " : $0
                }))
                .trimmingCharacters(in: .whitespaces)
            }
            .filter { !$0.isEmpty }
            .map { $0.count > longestProblem ? String($0.prefix(longestProblem - 1)) + "…" : $0 }
        guard cleaned.count > mostProblemLines else { return cleaned }
        let shown = Array(cleaned.prefix(mostProblemLines - 1))
        let rest = cleaned.count - shown.count
        return shown + ["\(rest) more problems are on the dashboard."]
    }

    static func grouped(_ number: Int) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: number)) ?? String(number)
    }

    /// The plain-text report printed by --selftest.
    var selftestReport: String {
        var out = ["Dot: " + dot.rawValue,
                   "Number beside the icon: " + (number.map(String.init) ?? "none"),
                   "Menu:"]
        for line in menu {
            switch line {
            case .text(let text): out.append("  " + text)
            case .separator: out.append("  --------")
            case .openDashboard: out.append("  " + MenuLine.openDashboardTitle)
            case .quit: out.append("  " + MenuLine.quitTitle)
            }
        }
        if let detail { out.append("Detail (self-test only): " + detail) }
        return out.joined(separator: "\n")
    }
}

/// Times as "10:31 AM", always in the Mac's own time zone.
enum Clock {
    static func twelveHour(_ date: Date, timeZone: TimeZone) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }

    /// "15:30" becomes "3:30 PM". The summary already gives local time, so no zone change.
    static func twelveHour(hhmm: String) -> String {
        let parts = hhmm.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else { return hhmm }
        let shownHour = hour % 12 == 0 ? 12 : hour % 12
        return String(format: "%d:%02d %@", shownHour, minute, hour < 12 ? "AM" : "PM")
    }
}
