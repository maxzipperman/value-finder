import AppKit
import SwiftUI

/// Asks the dashboard for its summary at launch and then once a minute.
@MainActor
final class LightModel: ObservableObject {
    static let everySeconds: TimeInterval = 60

    @Published private(set) var state: DisplayState = .starting

    private let fetcher = SummaryFetcher()
    private var timer: Timer?
    private var asking = false

    init() {
        refresh()
        let timer = Timer(timeInterval: Self.everySeconds, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        timer.tolerance = 5
        // .common keeps the timer running while the menu is open.
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func refresh() {
        guard !asking else { return }
        asking = true
        fetcher.fetch(Address.summary) { outcome in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.asking = false
                self.state = DisplayState(outcome: outcome, checkedAt: Date())
            }
        }
    }
}

/// The menu-bar light. No window and no Dock icon (LSUIElement in Info.plist).
struct ValueFinderLight: App {
    @StateObject private var model = LightModel()

    var body: some Scene {
        MenuBarExtra {
            MenuContent(lines: model.state.menu)
        } label: {
            Image(nsImage: Icon.image(dot: model.state.dot,
                                      number: model.state.number,
                                      description: model.state.spoken))
                .renderingMode(.original)
                .accessibilityLabel(Text(model.state.spoken))
        }
        .menuBarExtraStyle(.menu)
    }
}

struct MenuContent: View {
    let lines: [MenuLine]

    var body: some View {
        ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
            switch line {
            case .text(let text):
                Text(text)
            case .separator:
                Divider()
            case .openDashboard:
                Button(MenuLine.openDashboardTitle) {
                    NSWorkspace.shared.open(Address.dashboard)
                }
            case .quit:
                Button(MenuLine.quitTitle) {
                    NSApplication.shared.terminate(nil)
                }
                .keyboardShortcut("q")
            }
        }
    }
}
