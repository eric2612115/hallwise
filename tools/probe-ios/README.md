# Hallwise Probe

A throwaway test app that answers one question on a real iPhone: which microphone formats can an app
capture live, with no video?

1. **Spatial capture** (AVCaptureSession, iOS 26): asks for first-order ambisonics. If supported it receives
   two live streams at once — 4-channel FOA (W, Y, Z, X) and 2-channel stereo — writes each to a `.caf`,
   and shows an arrow toward the loudest sound computed from the FOA channels.
2. **Stereo route** (AVAudioSession + AVAudioEngine): built-in mic, stereo polar pattern, portrait.
   Shows left/right levels.

Four FOA channels is the most an app gets; individual microphones are not exposed.

## Build and install (on a Mac with Xcode)

```
brew install xcodegen
cd tools/probe-ios && xcodegen
open HallwiseProbe.xcodeproj
```

In Xcode: select the HallwiseProbe target → Signing & Capabilities → Team: your Apple ID (Personal Team).
Plug the iPhone in, pick it as the run destination, press Run.
First time on the phone: Settings → Privacy & Security → Developer Mode → on (restart), then
Settings → General → VPN & Device Management → trust your developer certificate.

## What to do on the phone

1. Section 1, "Record 10 s". Hold the phone upright, screen facing you. Clap about 1 m away: in front,
   on the left, behind, on the right. Note whether "4-channel FOA supported" is yes, how many FOA channels
   arrived, and whether the arrow follows the claps.
2. Section 2, "Record 10 s". Clap on your left, then your right. "Left minus right" should flip sign.
3. "Share all" → AirDrop the recordings to the Mac for analysis.
