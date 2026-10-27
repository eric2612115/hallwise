import CoreLocation

/// One fix at Start, with a name, so a recording knows where it happened without anyone typing. The coordinates
/// go to the server as the phone took them; the name is the point of interest there, or only the district when
/// the fix is a street address, so a recording made at home never names the door.
final class Whereabouts: NSObject, CLLocationManagerDelegate {
    struct Place {
        let name: String?
        let latitude: Double
        let longitude: Double
    }

    private let manager = CLLocationManager()
    private var waiting: CheckedContinuation<Place?, Never>?
    private var fix: CLLocation?
    private var clock = 0  // only the latest deadline counts: a late one from an earlier Start must not end this one

    func place() async -> Place? {
        if waiting != nil { finish(name: nil) }  // a Start still waiting gets its answer before this one asks
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        fix = nil
        return await withCheckedContinuation { c in
            waiting = c
            switch manager.authorizationStatus {
            case .notDetermined:
                // the first Start asks: the clock for the fix starts when the owner answers, not while they read
                manager.requestWhenInUseAuthorization()
                deadline(60)
            case .denied, .restricted:
                finish(name: nil)
            default:
                askForFix()
            }
        }
    }

    private func askForFix() {
        manager.requestLocation()
        deadline(8)  // the fix without a name if the geocoder is slow, nothing if there is no fix
    }

    private func deadline(_ seconds: Double) {
        clock += 1
        let this = clock
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in
            if self?.clock == this { self?.finish(name: nil) }
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard waiting != nil, fix == nil else { return }  // one fix per Start; a second answer changes nothing
        guard let loc = locations.last else { return finish(name: nil) }
        fix = loc
        CLGeocoder().reverseGeocodeLocation(loc) { [weak self] marks, _ in
            self?.finish(name: Self.label(marks?.first))
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if fix == nil { finish(name: nil) }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard waiting != nil, fix == nil else { return }
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: askForFix()
        case .denied, .restricted: finish(name: nil)
        default: break  // still deciding
        }
    }

    /// "Place, City"; a street address is not a place, so then "District, City".
    static func label(_ m: CLPlacemark?) -> String? {
        guard let m else { return nil }
        let name = m.name ?? ""
        let isAddress = [m.thoroughfare, m.subThoroughfare].contains { part in
            guard let part, !part.isEmpty else { return false }
            return name.contains(part)
        }
        let parts = [isAddress ? m.subLocality : m.name, m.locality].compactMap { $0 }.filter { !$0.isEmpty }
        let unique = parts.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        return unique.isEmpty ? nil : unique.joined(separator: ", ")
    }

    private func finish(name: String?) {
        guard let c = waiting else { return }
        waiting = nil
        c.resume(returning: fix.map { Place(name: name, latitude: $0.coordinate.latitude, longitude: $0.coordinate.longitude) })
    }
}
