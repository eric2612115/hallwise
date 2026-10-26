import SwiftUI

/// What the badge shows and where it streams. Stored on the phone.
final class BadgeSettings: ObservableObject {
    @AppStorage("serverURL") var serverURL = "ws://192.168.0.142:8790"
    @AppStorage("ownerName") var ownerName = "Eric"
    @AppStorage("ownerCompany") var ownerCompany = "Hallwise"
    @AppStorage("ownerTitle") var ownerTitle = ""
    @AppStorage("contact") var contact = ""          // email or handle, goes into the QR card
    @AppStorage("keywords") var keywords = "Hallwise"  // comma-separated recognition hints
    @AppStorage("eventName") var eventName = ""      // tonight's event, stored with each recording
    @AppStorage("venue") var venue = ""
    @AppStorage("yawOffset") var yawOffset = 0.0     // degrees, calibrates the badge's forward direction
    @AppStorage("appearance") var appearance = Theme.Appearance.system.rawValue
    @AppStorage("followRecording") var followRecording = ""  // debug: watch this recording instead of capturing
    @AppStorage("deckURL") var deckURL = ""        // the things people ask for, one tap to share
    @AppStorage("onePagerURL") var onePagerURL = ""
    @AppStorage("blurb") var blurb = ""            // two lines about you, for pasting

    /// What the owner can hand over, by the names the server uses for attachments.
    var links: [String: String] {
        ["deck": deckURL, "one_pager": onePagerURL, "blurb": blurb].filter { !$0.value.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    var colorScheme: ColorScheme? { Theme.Appearance(rawValue: appearance)?.colorScheme }

    var keywordList: [String] {
        keywords.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    /// A corrected word becomes a recognition hint for the next recording.
    func remember(_ word: String) {
        let w = word.trimmingCharacters(in: .whitespaces)
        guard !w.isEmpty, !keywordList.contains(where: { $0.caseInsensitiveCompare(w) == .orderedSame }) else { return }
        keywords = (keywordList + [w]).joined(separator: ", ")
    }

    func forget(_ word: String) {
        keywords = keywordList.filter { $0 != word }.joined(separator: ", ")
    }

    /// A vCard for the badge's QR code.
    var vCard: String {
        var lines = ["BEGIN:VCARD", "VERSION:3.0", "FN:\(ownerName)", "ORG:\(ownerCompany)"]
        if !ownerTitle.isEmpty { lines.append("TITLE:\(ownerTitle)") }
        if contact.contains("@") { lines.append("EMAIL:\(contact)") } else if !contact.isEmpty { lines.append("NOTE:\(contact)") }
        lines.append("END:VCARD")
        return lines.joined(separator: "\n")
    }
}
