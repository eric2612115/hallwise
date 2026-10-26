import Foundation

// How the badge reads its own orientation, as plain arithmetic on CoreMotion's numbers, so it compiles and can be
// checked without a device.
//
// The badge hangs on the chest in portrait with the screen facing out, so the wearer faces where the screen
// normal (device +z) points. Its Euler yaw is no good for that: an upright phone sits at pitch ≈ 90°, which is
// exactly the gimbal-lock point of CoreMotion's Z-X-Y Euler angles, so a body turn can leak into roll instead of
// yaw. The heading here comes straight from the attitude's rotation matrix instead.
//
// CMAttitude.rotationMatrix maps the reference frame to the device frame (v_device = R · v_reference): its rows
// are the device's x, y and z axes written in reference coordinates, and its columns are the reference axes
// written in device coordinates. So (m31, m32, m33) is where the screen normal points in the room, and
// -(m13, m23, m33) is gravity in device coordinates, which is what CMDeviceMotion.gravity reports.

/// The direction the wearer faces, in degrees in (-180, 180], counter-clockwise seen from above (the same sense as
/// CoreMotion yaw), in the attitude's reference frame (.xArbitraryZVertical: zero is wherever motion updates began).
///
/// It is the horizontal direction of the screen normal. As the badge tilts towards flat that direction shrinks
/// to nothing, so the phone's long axis takes over smoothly: with the screen facing up, the top of the phone points
/// back towards the wearer; facing down, it points ahead. Blending as `z - z_up · top` gives the exact facing for
/// any lean of the torso and never divides by zero, so the value stays finite and does not jump when the badge
/// lies flat. `inverted` means the phone hangs top-down, so its "top" is device -y.
func badgeHeading(m11: Double, m12: Double, m13: Double,
                  m21: Double, m22: Double, m23: Double,
                  m31: Double, m32: Double, m33: Double,
                  inverted: Bool = false) -> Double {
    let top = inverted ? -1.0 : 1.0
    let (zx, zy, zUp) = (m31, m32, m33)          // screen normal in the reference frame
    let (tx, ty) = (top * m21, top * m22)         // the phone's top edge, horizontally
    var fx = zx - zUp * tx
    var fy = zy - zUp * ty
    if !(hypot(fx, fy) > 1e-6) {
        // Only reachable for poses the badge never holds (top edge well below the horizon, or garbage input).
        (fx, fy) = hypot(zx, zy) > 1e-9 ? (zx, zy) : (tx, ty)
    }
    guard hypot(fx, fy) > 1e-12, fx.isFinite, fy.isFinite else { return 0 }
    return wrapDegrees(atan2(fy, fx) * 180 / .pi)
}

/// Whether the phone hangs top-down (rotated 180° about the screen normal), from gravity in device coordinates
/// (CMDeviceMotion.gravity, in g). Upright portrait has gravity.y ≈ -1; top-down has gravity.y ≈ +1. Between
/// ±0.5 (the long axis within 30° of horizontal: lying flat, or swinging sideways) the previous answer holds, so the
/// state does not flicker.
func badgeInverted(gravityX: Double, gravityY: Double, gravityZ: Double, wasInverted: Bool) -> Bool {
    let g = (gravityX * gravityX + gravityY * gravityY + gravityZ * gravityZ).squareRoot()
    guard g > 0.1, g.isFinite else { return wasInverted }
    let y = gravityY / g
    if y > 0.5 { return true }
    if y < -0.5 { return false }
    return wasInverted
}

/// Degrees in (-180, 180].
func wrapDegrees(_ degrees: Double) -> Double {
    let a = (degrees + 180).truncatingRemainder(dividingBy: 360)
    let w = (a < 0 ? a + 360 : a) - 180
    return w == -180 ? 180 : w
}
