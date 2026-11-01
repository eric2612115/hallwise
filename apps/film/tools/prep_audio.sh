#!/bin/zsh
# Cut a window out of a badge FOA recording and decode it to stereo for the film (read-only on the source).
# The badge records ambisonics, ACN order W Y Z X, SN3D (server/hallwise/recording.py). Two virtual cardioids
# pointing left and right: L = (W + Y) / 2, R = (W - Y) / 2 for the rehearsal's "screen" frame (direction.py
# FRAME_ROTATION); an iPhone take ("camera" frame) is rotated 180 degrees, so swap the sign of Y: L = (W - Y) / 2.
# ffmpeg guesses "4.0" (FL FR FC BC) for a 4-channel WAV; never let it auto-downmix, address c0..c3 explicitly.
# Loudness is normalised to -18 LUFS (the replay export's level) so a quiet room does not come out silent.
#
#   tools/prep_audio.sh <audio.wav> <start_s> <dur_s> <out.wav> [screen|camera] [gain_db]
set -euo pipefail
src=$1; start=$2; dur=$3; out=$4; frame=${5:-screen}; gain=${6:-0}
if [[ "$frame" == "camera" ]]; then pan="pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c0+0.5*c1"; else pan="pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0-0.5*c1"; fi
mkdir -p "$(dirname "$out")"
ffmpeg -hide_banner -loglevel error -y -ss "$start" -t "$dur" -i "$src" \
  -af "${pan},highpass=f=70,loudnorm=I=-18:TP=-1.5:LRA=11,volume=${gain}dB" \
  -ar 48000 -c:a pcm_s16le "$out"
echo "$out"
