import CoreImage.CIFilterBuiltins
import SwiftUI

/// The face of the badge: a paper name card, readable from a metre away, with a QR contact card.
/// Nothing else — no recording light, no app name — so it reads as a badge, not a device.
struct BadgeView: View {
    @ObservedObject var settings: BadgeSettings
    @Environment(\.colorScheme) private var scheme

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
                        .foregroundStyle(Theme.ink)
                    Text(settings.ownerCompany)
                        .font(.system(size: 28, weight: .medium, design: .serif))
                        .foregroundStyle(Theme.ink)
                    if !settings.ownerTitle.isEmpty {
                        Text(settings.ownerTitle)
                            .font(.system(size: 20, design: .serif))
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .multilineTextAlignment(.center)
                Rectangle().fill(Theme.rule).frame(width: 120, height: 1)
                if let qr = qrImage(settings.vCard) {
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
        }
    }

    private var initials: String {
        settings.ownerName.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined()
    }

    private func qrImage(_ text: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage,
              let cg = CIContext().createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}

extension Color {
    init(hex: UInt32) { self.init(uiColor: UIColor(hex: hex)) }
}
