import SwiftUI
import UIKit

/// One palette for the badge app and the web dashboard: paper, ink, one accent, one "live" red.
/// Light mode is cream paper with dark ink; dark mode is charcoal paper with pale ink.
enum Theme {
    static let paper = Color(light: 0xEDE8DC, dark: 0x1C1A17)
    static let paperDeep = Color(light: 0xE2DBC9, dark: 0x26231F)
    static let ink = Color(light: 0x2A2622, dark: 0xE8E2D6)
    static let inkStrong = Color(light: 0x1A1613, dark: 0xFAF6EE)  // the badge name
    static let inkSoft = Color(light: 0x6E675E, dark: 0xA39B8F)
    static let rule = Color(light: 0xD3CBB9, dark: 0x35312B)
    static let accent = Color(light: 0x2F7F72, dark: 0x6FB9AB)
    static let live = Color(light: 0xC8402F, dark: 0xE2644F)

    /// One colour per person met, in the order they appeared; distinct on cream and on charcoal.
    static let people: [Color] = [
        Color(light: 0x2F7F72, dark: 0x6FB9AB),  // teal
        Color(light: 0xC8702F, dark: 0xE89A5C),  // terracotta
        Color(light: 0x7A4FA3, dark: 0xB08AD8),  // plum
        Color(light: 0xB8862B, dark: 0xE0B45A),  // ochre
        Color(light: 0x3B63A8, dark: 0x7FA3E0),  // indigo
        Color(light: 0x5F8A3C, dark: 0x9BC46A),  // moss
        Color(light: 0xB8475F, dark: 0xE07A91),  // rose
        Color(light: 0x5B6B78, dark: 0x9FB0BE),  // slate
    ]

    enum Appearance: String, CaseIterable {
        case system, light, dark
        var colorScheme: ColorScheme? {
            switch self {
            case .system: return nil
            case .light: return .light
            case .dark: return .dark
            }
        }
    }
}

extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { trait in
            UIColor(hex: trait.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

extension Color {
    init(hex: UInt32) { self.init(uiColor: UIColor(hex: hex)) }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

/// Paper: the base colour, a tiled grain of tiny specks, and a faint vignette. Drawn in code, so it works in
/// both colour schemes and costs nothing to ship.
struct PaperBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        ZStack {
            Theme.paper
            Image(uiImage: PaperGrain.tile(dark: scheme == .dark))
                .resizable(resizingMode: .tile)
                .opacity(scheme == .dark ? 0.18 : 0.11)
            RadialGradient(
                colors: [.clear, Theme.ink.opacity(scheme == .dark ? 0.0 : 0.06), Color.black.opacity(scheme == .dark ? 0.25 : 0.0)],
                center: .center, startRadius: 140, endRadius: 560
            )
        }
        .ignoresSafeArea()
    }
}

enum PaperGrain {
    private static var cache: [Bool: UIImage] = [:]

    /// A 128×128 tile of specks. Dark specks on light paper, light specks on dark paper.
    static func tile(dark: Bool) -> UIImage {
        if let image = cache[dark] { return image }
        let size = CGSize(width: 128, height: 128)
        var rng = SplitMix64(seed: dark ? 7 : 3)
        let image = UIGraphicsImageRenderer(size: size).image { ctx in
            let cg = ctx.cgContext
            for _ in 0..<2600 {
                let x = CGFloat(rng.next() % 128), y = CGFloat(rng.next() % 128)
                let r = 0.35 + CGFloat(rng.next() % 100) / 100 * 0.75
                let a = 0.25 + CGFloat(rng.next() % 100) / 100 * 0.75
                cg.setFillColor(dark ? UIColor(white: 1, alpha: a).cgColor : UIColor(white: 0, alpha: a).cgColor)
                cg.fillEllipse(in: CGRect(x: x, y: y, width: r, height: r))
            }
            // a few longer fibres
            cg.setLineWidth(0.5)
            for _ in 0..<90 {
                let x = CGFloat(rng.next() % 128), y = CGFloat(rng.next() % 128)
                let dx = CGFloat(Int(rng.next() % 13) - 6), dy = CGFloat(Int(rng.next() % 5) - 2)
                cg.setStrokeColor((dark ? UIColor(white: 1, alpha: 0.35) : UIColor(white: 0, alpha: 0.3)).cgColor)
                cg.move(to: CGPoint(x: x, y: y))
                cg.addLine(to: CGPoint(x: x + dx, y: y + dy))
                cg.strokePath()
            }
        }
        cache[dark] = image
        return image
    }
}

/// Deterministic random numbers, so the grain is the same on every launch.
struct SplitMix64 {
    private var state: UInt64
    init(seed: UInt64) { state = seed &* 0x9E3779B97F4A7C15 }
    mutating func next() -> UInt64 {
        state &+= 0x9E3779B97F4A7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
}

/// Small helpers shared by the screens.
struct Tag: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(Capsule().fill(Theme.paperDeep))
            .overlay(Capsule().stroke(Theme.rule, lineWidth: 0.5))
    }
}
