import SwiftUI

/// The face of the badge: a paper name card, readable from a metre away, with a QR contact card.
/// Nothing else — no recording light, no app name — so it reads as a badge, not a device.
/// If the lanyard leaves the phone hanging top-down, the card turns itself the right way up.
struct BadgeView: View {
    @ObservedObject var settings: BadgeSettings
    @Environment(\.colorScheme) private var scheme
    @StateObject private var hanging = BadgeHanging()

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(spacing: 26) {
                Spacer(minLength: 20)
                Text(initials)
                    .font(.system(size: 34, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.paper)
                    .frame(width: 86, height: 86)
                    .background(Circle().fill(Theme.ink))
                VStack(spacing: 8) {
                    Text(settings.ownerName)
                        .font(.system(size: 58, weight: .bold, design: .serif))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                        .foregroundStyle(Theme.inkStrong)
                    Text(settings.ownerCompany)
                        .font(.system(size: 28, weight: .medium, design: .serif))
                        .foregroundStyle(Theme.inkStrong)
                    if !settings.ownerTitle.isEmpty {
                        Text(settings.ownerTitle)
                            .font(.system(size: 20, design: .serif))
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .multilineTextAlignment(.center)
                Rectangle().fill(Theme.rule).frame(width: 120, height: 1)
                if let qr = badgeQR(settings.vCard) {
                    // Always dark on light so any phone can scan it, whatever the colour scheme.
                    Image(uiImage: qr)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 164, height: 164)
                        .padding(10)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Color(hex: 0xF6F2E8)))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.rule, lineWidth: 0.5))
                    Text("scan to save my contact")
                        .font(.system(size: 13, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .padding(.top, -14)
                }
                Spacer()
                Spacer(minLength: 28)
            }
            .padding(.horizontal, 32)
            .rotationEffect(.degrees(hanging.upsideDown ? 180 : 0))
            .animation(.easeInOut(duration: 0.35), value: hanging.upsideDown)
        }
        .onAppear { hanging.start() }
        .onDisappear { hanging.stop() }
    }

    private var initials: String {
        settings.ownerName.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined()
    }
}

/// Whether the badge hangs top-down. The app is locked to portrait, and UIDevice's orientation stops updating when
/// the owner has rotation lock on, so this listens to the motion sensor itself (through the app's one motion
/// manager), whether or not a recording is running: the badge is on show before anyone presses Start.
final class BadgeHanging: ObservableObject {
    @Published private(set) var upsideDown = false
    private var listener: UUID?

    func start() {
        guard listener == nil else { return }
        listener = BadgeMotion.shared.listen { [weak self] _, inverted in
            DispatchQueue.main.async {
                if let self, self.upsideDown != inverted { self.upsideDown = inverted }
            }
        }
    }

    func stop() {
        if let listener { BadgeMotion.shared.stopListening(listener) }
        listener = nil
    }

    deinit { stop() }
}
