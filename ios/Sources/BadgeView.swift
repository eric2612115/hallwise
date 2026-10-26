import CoreImage.CIFilterBuiltins
import SwiftUI

/// The face of the badge: a paper name card, readable from a metre away, with a QR contact card.
struct BadgeView: View {
    @ObservedObject var settings: BadgeSettings
    let listening: Bool

    var body: some View {
        ZStack {
            Color(red: 0.93, green: 0.91, blue: 0.86).ignoresSafeArea()
            VStack(spacing: 28) {
                Spacer()
                Text(initials)
                    .font(.system(size: 34, weight: .semibold, design: .serif))
                    .foregroundStyle(Color(red: 0.93, green: 0.91, blue: 0.86))
                    .frame(width: 84, height: 84)
                    .background(Circle().fill(ink))
                VStack(spacing: 8) {
                    Text(settings.ownerName)
                        .font(.system(size: 56, weight: .bold, design: .serif))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                    Text(settings.ownerCompany)
                        .font(.system(size: 28, weight: .medium, design: .serif))
                    if !settings.ownerTitle.isEmpty {
                        Text(settings.ownerTitle).font(.system(size: 20, design: .serif)).opacity(0.7)
                    }
                }
                .foregroundStyle(ink)
                if let qr = qrImage(settings.vCard) {
                    Image(uiImage: qr)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 170, height: 170)
                        .padding(10)
                        .background(RoundedRectangle(cornerRadius: 10).fill(.white.opacity(0.6)))
                }
                Spacer()
                HStack(spacing: 8) {
                    Circle().fill(listening ? Color.red : Color.gray.opacity(0.5)).frame(width: 10, height: 10)
                    Text(listening ? "Hallwise is taking notes" : "Hallwise")
                        .font(.system(size: 15, design: .serif))
                        .foregroundStyle(ink.opacity(0.7))
                }
                .padding(.bottom, 24)
            }
            .padding(.horizontal, 32)
        }
    }

    private let ink = Color(red: 0.16, green: 0.15, blue: 0.13)

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
