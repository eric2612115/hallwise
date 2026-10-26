#!/bin/sh
# Record the booted iOS Simulator's screen (the follow view) to an H.264 QuickTime file; Ctrl-C stops it.
#   ./record-follow-view.sh [file.mov]     default: follow-view-<time>.mov here
# DEVICE=<udid> picks a simulator other than the booted one. Run simulator-status-bar.sh first for 9:41.
#
# simctl writes a frame only when the screen changes, so the file has a variable frame rate (a still screen
# is one long frame). The editor re-times it to a constant frame rate before cutting it against the audio.
device="${DEVICE:-booted}"
out="${1:-follow-view-$(date +%Y%m%d-%H%M%S).mov}"
echo "recording $device to $out; Ctrl-C to stop"
# Ctrl-C reaches simctl too: it finishes writing the file and exits. The trap keeps this script going so it
# can say where the file is.
trap ':' INT
xcrun simctl io "$device" recordVideo --codec=h264 --force "$out"
status=$?
[ -s "$out" ] && echo "saved $out" || echo "no recording written (simctl exit $status)" >&2
