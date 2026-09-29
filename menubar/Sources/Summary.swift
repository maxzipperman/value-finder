import Foundation

/// What GET /api/summary returns, after every field has been checked against the contract.
/// Anything that fails a check is refused as a whole, and the light shows gray.
struct Summary: Equatable, Sendable {
    enum Health: String, Sendable {
        case ok, warn, fail
    }

    let generatedUTC: String
    let health: Health
    let signalsLive: Int
    let gamesOnBoard: Int
    /// "HH:MM", 24-hour, the Mac's local time.
    let nextRunLocal: String
    let creditsRemaining: Int?
    let problems: [String]
}

/// Why an answer from the dashboard could not be used. Shown only by the self-test.
enum SummaryError: Error, Equatable, Sendable {
    case notJSON
    case notAnObject
    case missing(String)
    case wrongType(String, expected: String)

    var detail: String {
        switch self {
        case .notJSON:
            return "the answer is not valid JSON"
        case .notAnObject:
            return "the answer is JSON but not an object with named fields"
        case .missing(let field):
            return "the field \(field) is missing"
        case .wrongType(let field, let expected):
            return "the field \(field) should be \(expected)"
        }
    }
}

extension Summary {
    /// Checks every field of the contract. Extra fields are ignored.
    static func parse(_ data: Data) -> Result<Summary, SummaryError> {
        let top: Any
        do {
            top = try JSONSerialization.jsonObject(with: data, options: [])
        } catch {
            return .failure(.notJSON)
        }
        guard let object = top as? [String: Any] else { return .failure(.notAnObject) }
        do {
            let fields = Fields(object)
            return .success(Summary(
                generatedUTC: try fields.utcTime("generated_utc"),
                health: try fields.health("health"),
                signalsLive: try fields.count("signals_live"),
                gamesOnBoard: try fields.count("games_on_board"),
                nextRunLocal: try fields.clockTime("next_run_local"),
                creditsRemaining: try fields.countOrNull("credits_remaining"),
                problems: try fields.sentences("problems")
            ))
        } catch let error as SummaryError {
            return .failure(error)
        } catch {
            return .failure(.notAnObject)
        }
    }
}

/// Reads one field at a time and refuses a missing field or a wrong type.
private struct Fields {
    let object: [String: Any]

    init(_ object: [String: Any]) {
        self.object = object
    }

    func value(_ name: String) throws -> Any {
        guard let value = object[name] else { throw SummaryError.missing(name) }
        return value
    }

    func string(_ name: String, expected: String) throws -> String {
        guard let text = try value(name) as? String else {
            throw SummaryError.wrongType(name, expected: expected)
        }
        return text
    }

    func health(_ name: String) throws -> Summary.Health {
        let expected = "one of \"ok\", \"warn\" or \"fail\""
        guard let health = Summary.Health(rawValue: try string(name, expected: expected)) else {
            throw SummaryError.wrongType(name, expected: expected)
        }
        return health
    }

    func utcTime(_ name: String) throws -> String {
        let expected = "a UTC time like 2026-09-29T17:31:00Z"
        let text = try string(name, expected: expected)
        guard Pattern.matches(text, Pattern.utcTime) else {
            throw SummaryError.wrongType(name, expected: expected)
        }
        return text
    }

    func clockTime(_ name: String) throws -> String {
        let expected = "a 24-hour time like 15:30"
        let text = try string(name, expected: expected)
        guard Pattern.matches(text, Pattern.clockTime) else {
            throw SummaryError.wrongType(name, expected: expected)
        }
        return text
    }

    func count(_ name: String) throws -> Int {
        guard let number = Fields.wholeNumber(try value(name)) else {
            throw SummaryError.wrongType(name, expected: "a whole number of 0 or more")
        }
        return number
    }

    func countOrNull(_ name: String) throws -> Int? {
        let raw = try value(name)
        if raw is NSNull { return nil }
        guard let number = Fields.wholeNumber(raw) else {
            throw SummaryError.wrongType(name, expected: "a whole number of 0 or more, or null")
        }
        return number
    }

    func sentences(_ name: String) throws -> [String] {
        let expected = "a list of sentences"
        guard let items = try value(name) as? [Any] else {
            throw SummaryError.wrongType(name, expected: expected)
        }
        return try items.map { item in
            guard let text = item as? String else {
                throw SummaryError.wrongType(name, expected: expected)
            }
            return text
        }
    }

    /// A JSON number with no fraction, from 0 to one billion. true and false are refused,
    /// and so is text such as "2". A number written 2.0 is the number 2 and is accepted.
    static func wholeNumber(_ raw: Any) -> Int? {
        guard let number = raw as? NSNumber,
              CFGetTypeID(number as CFTypeRef) != CFBooleanGetTypeID() else { return nil }
        let value = number.doubleValue
        guard value.isFinite, value >= 0, value <= 1_000_000_000,
              value == value.rounded(.towardZero) else { return nil }
        return Int(value)
    }
}

enum Pattern {
    static let utcTime = #"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z\z"#
    static let clockTime = #"\A([01][0-9]|2[0-3]):[0-5][0-9]\z"#

    static func matches(_ text: String, _ pattern: String) -> Bool {
        text.range(of: pattern, options: .regularExpression) != nil
    }
}
