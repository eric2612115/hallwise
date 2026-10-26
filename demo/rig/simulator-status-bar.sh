#!/bin/sh
# A clean status bar on the booted iOS Simulator for screen recordings: 9:41, full battery, full bars.
#   ./simulator-status-bar.sh          set it
#   ./simulator-status-bar.sh clear    back to the real one
# DEVICE=<udid> picks a simulator other than the booted one.
set -e
device="${DEVICE:-booted}"
case "${1:-set}" in
    set)
        xcrun simctl status_bar "$device" override --time 9:41 --batteryState charged --batteryLevel 100 \
            --cellularMode active --cellularBars 4 --wifiBars 3
        echo "status bar overridden on $device"
        ;;
    clear)
        xcrun simctl status_bar "$device" clear
        echo "status bar cleared on $device"
        ;;
    *)
        echo "usage: $0 [set|clear]" >&2
        exit 2
        ;;
esac
