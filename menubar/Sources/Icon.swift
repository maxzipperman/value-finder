import AppKit

/// Draws the menu-bar icon: the wind symbol, a coloured dot at its lower right, and the
/// number of live signals beside it when there are any. It is one image that is not a
/// template, so the dot keeps its colour. The symbol and the number are drawn in the
/// label colour of whatever appearance the menu bar is drawing in, light or dark.
enum Icon {
    static let height: CGFloat = 18
    static let dotDiameter: CGFloat = 7
    static let symbolPointSize: CGFloat = 14

    static func color(_ dot: Dot) -> NSColor {
        switch dot {
        case .green: return .systemGreen
        case .amber: return .systemOrange
        case .red: return .systemRed
        case .gray: return .systemGray
        }
    }

    static func image(dot: Dot, number: Int?, description: String) -> NSImage {
        let config = NSImage.SymbolConfiguration(pointSize: symbolPointSize, weight: .regular)
        let symbol = NSImage(systemSymbolName: "wind", accessibilityDescription: nil)?
            .withSymbolConfiguration(config)
        let symbolSize = symbol?.size ?? NSSize(width: 17, height: 13)
        let glyphWidth = ceil(symbolSize.width + dotDiameter / 2)

        let text = number.map(String.init)
        let font = NSFont.monospacedDigitSystemFont(ofSize: 13, weight: .regular)
        let textSize = text.map { ($0 as NSString).size(withAttributes: [.font: font]) } ?? .zero
        let width = glyphWidth + (text == nil ? 0 : ceil(3 + textSize.width))

        let image = NSImage(size: NSSize(width: width, height: height), flipped: false) { _ in
            let ink = NSColor.labelColor
            guard let context = NSGraphicsContext.current else { return false }

            // The wind symbol, tinted with the label colour.
            let symbolRect = NSRect(x: 0, y: floor((height - symbolSize.height) / 2),
                                    width: symbolSize.width, height: symbolSize.height)
            if let symbol {
                context.saveGraphicsState()
                symbol.draw(in: symbolRect)
                ink.setFill()
                symbolRect.fill(using: .sourceAtop)
                context.restoreGraphicsState()
            }

            // A clear ring around the dot so it stands apart from the symbol, then the dot.
            let dotRect = NSRect(x: glyphWidth - dotDiameter, y: 1,
                                 width: dotDiameter, height: dotDiameter)
            context.saveGraphicsState()
            context.compositingOperation = .clear
            NSBezierPath(ovalIn: dotRect.insetBy(dx: -1.5, dy: -1.5)).fill()
            context.restoreGraphicsState()
            color(dot).setFill()
            NSBezierPath(ovalIn: dotRect).fill()

            // The number of live signals.
            if let text {
                let origin = NSPoint(x: glyphWidth + 3, y: floor((height - textSize.height) / 2))
                (text as NSString).draw(at: origin, withAttributes: [.font: font, .foregroundColor: ink])
            }
            return true
        }
        image.isTemplate = false
        image.accessibilityDescription = description
        return image
    }
}
