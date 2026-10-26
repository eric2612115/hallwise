import CoreLocation

/// One fix, reverse-geocoded to "Place, City", so a recording knows where it happened without anyone typing.
final class Whereabouts: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var waiting: CheckedContinuation<String?, Never>?

    func venue() async -> String? {
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() }
        return await withCheckedContinuation { c in
            waiting = c
            manager.requestLocation()
            DispatchQueue.main.asyncAfter(deadline: .now() + 8) { [weak self] in self?.finish(nil) }
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return finish(nil) }
        CLGeocoder().reverseGeocodeLocation(loc) { [weak self] marks, _ in
            let m = marks?.first
            let parts = [m?.name, m?.locality].compactMap { $0 }.filter { !$0.isEmpty }
            self?.finish(parts.isEmpty ? nil : Array(NSOrderedSet(array: parts)).compactMap { $0 as? String }.joined(separator: ", "))
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) { finish(nil) }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            manager.requestLocation()
        }
    }

    private func finish(_ venue: String?) {
        waiting?.resume(returning: venue)
        waiting = nil
    }
}
