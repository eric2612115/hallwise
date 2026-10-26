import ActivityKit
import CoreImage.CIFilterBuiltins
import SwiftUI

/// What the lock screen shows while the badge is worn: the same name card, nothing about recording.
/// Shared by the app (which starts it) and the widget extension (which draws it).
struct BadgeActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {}
    var name: String
    var company: String
    var title: String
    var vcard: String

    var initials: String { name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined() }
    var firstName: String { name.split(separator: " ").first.map(String.init) ?? name }
}

/// The contact card as a QR image, drawn at one pixel per module; scale it with `.interpolation(.none)`.
func badgeQR(_ text: String) -> UIImage? {
    let filter = CIFilter.qrCodeGenerator()
    filter.message = Data(text.utf8)
    filter.correctionLevel = "M"
    guard let output = filter.outputImage,
          let cg = CIContext().createCGImage(output, from: output.extent) else { return nil }
    return UIImage(cgImage: cg)
}
