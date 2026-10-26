import ActivityKit
import SwiftUI
import WidgetKit

@main
struct HallwiseWidgets: WidgetBundle {
    var body: some Widget { BadgeLiveActivity() }
}

/// The badge on the lock screen and in the Dynamic Island: name, company, QR. No dot, no timer, no waveform,
/// so a locked phone on a chest still reads as a name badge.
struct BadgeLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: BadgeActivityAttributes.self) { context in
            LockScreenBadge(badge: context.attributes)
                .activityBackgroundTint(Theme.paper)
                .activitySystemActionForegroundColor(Theme.ink)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Monogram(text: context.attributes.initials, size: 44, fill: Color(hex: 0xEDE8DC), ink: Color(hex: 0x2A2622))
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.attributes.name)
                            .font(.system(size: 22, weight: .bold, design: .serif))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                        Text(context.attributes.company)
                            .font(.system(size: 15, design: .serif))
                            .foregroundStyle(.white.opacity(0.8))
                            .lineLimit(1)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if let qr = badgeQR(context.attributes.vcard) {
                        Image(uiImage: qr).interpolation(.none).resizable()
                            .frame(width: 40, height: 40).padding(3)
                            .background(RoundedRectangle(cornerRadius: 4).fill(Color(hex: 0xF6F2E8)))
                    }
                }
            } compactLeading: {
                Monogram(text: context.attributes.initials, size: 22, fill: Color(hex: 0xEDE8DC), ink: Color(hex: 0x2A2622))
            } compactTrailing: {
                Text(context.attributes.firstName)
                    .font(.system(size: 14, weight: .semibold, design: .serif))
                    .foregroundStyle(.white)
            } minimal: {
                Monogram(text: context.attributes.initials, size: 22, fill: Color(hex: 0xEDE8DC), ink: Color(hex: 0x2A2622))
            }
        }
    }
}

struct LockScreenBadge: View {
    let badge: BadgeActivityAttributes

    var body: some View {
        HStack(spacing: 14) {
            Monogram(text: badge.initials, size: 52, fill: Theme.ink, ink: Theme.paper)
            VStack(alignment: .leading, spacing: 3) {
                Text(badge.name)
                    .font(.system(size: 30, weight: .bold, design: .serif))
                    .foregroundStyle(Theme.inkStrong)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text([badge.company, badge.title].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.system(size: 16, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                Text("scan to save my contact")
                    .font(.system(size: 11, design: .serif))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.top, 2)
            }
            Spacer(minLength: 8)
            if let qr = badgeQR(badge.vcard) {
                Image(uiImage: qr).interpolation(.none).resizable()
                    .frame(width: 76, height: 76).padding(5)
                    .background(RoundedRectangle(cornerRadius: 6).fill(Color(hex: 0xF6F2E8)))
            }
        }
        .padding(16)
    }
}

struct Monogram: View {
    let text: String
    let size: CGFloat
    let fill: Color
    let ink: Color

    var body: some View {
        Text(text)
            .font(.system(size: size * 0.42, weight: .semibold, design: .serif))
            .foregroundStyle(ink)
            .frame(width: size, height: size)
            .background(Circle().fill(fill))
    }
}
