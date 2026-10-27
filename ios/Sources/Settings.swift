import SwiftUI

/// What the badge shows and where it streams. Stored on the phone.
final class BadgeSettings: ObservableObject {
    /// No default: an address left from somewhere else would stream to whoever holds it now. ws://, or wss://
    /// for a Tailscale or TLS setup.
    @AppStorage("serverURL") var serverURL = ""
    /// The server's shared secret, kept in the Keychain (see ServerKey), never in UserDefaults.
    @Published var serverKey = ServerKey.read() {
        didSet { if serverKey != oldValue { ServerKey.save(serverKey) } }
    }
    @AppStorage("ownerName") var ownerName = "Eric"
    @AppStorage("ownerCompany") var ownerCompany = "Hallwise"
    @AppStorage("ownerTitle") var ownerTitle = ""
    @AppStorage("contact") var contact = ""          // email or handle, goes into the QR card
    @AppStorage("keywords") var keywords = "Hallwise"  // comma-separated recognition hints
    @AppStorage("eventName") var eventName = ""      // tonight's event, stored with each recording
    @AppStorage("venue") var venue = ""
    @AppStorage("venueGuessed") var venueGuessed = ""  // what Start last filled the venue with; a typed one is kept
    @AppStorage("yawOffset") var yawOffset = 0.0     // degrees, calibrates the badge's forward direction
    @AppStorage("appearance") var appearance = Theme.Appearance.system.rawValue
    @AppStorage("followRecording") var followRecording = ""  // debug: watch this recording instead of capturing
    @AppStorage("replayPace") var replayPace = 1.0  // debug: a finished recording followed plays at this speed; 0 = all at once
    @AppStorage("keepLocalAudio") var keepLocalAudio = false  // debug: a raw copy of each take on this phone, kept 7 days
    @AppStorage("captureSetup") var captureSetup = CaptureSetup.standard.rawValue  // debug: who sets up the audio session, applied at Start
    @AppStorage("deckURL") var deckURL = ""        // the things people ask for, one tap to share
    @AppStorage("onePagerURL") var onePagerURL = ""
    @AppStorage("blurb") var blurb = ""            // two lines about you, for pasting

    /// What the owner can hand over, by the names the server uses for attachments.
    var links: [String: String] {
        ["deck": deckURL, "one_pager": onePagerURL, "blurb": blurb].filter { !$0.value.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    /// Why Start cannot run yet, in the app's words; nil once there is a usable address.
    var serverAddressProblem: String? {
        let address = serverURL.trimmingCharacters(in: .whitespaces)
        if address.isEmpty { return "Hallwise needs your server's address first. Add it in the menu, under Listening." }
        let lower = address.lowercased()
        guard lower.hasPrefix("ws://") || lower.hasPrefix("wss://"), URL(string: address)?.host() != nil else {
            return "The server's address starts with ws://, or wss:// over Tailscale or TLS."
        }
        return nil
    }

    var colorScheme: ColorScheme? { Theme.Appearance(rawValue: appearance)?.colorScheme }

    var captureSetupChoice: CaptureSetup { CaptureSetup(rawValue: captureSetup) ?? .standard }

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
