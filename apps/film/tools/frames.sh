#!/bin/zsh
# One frame per second out of a rendered film, to look at a cut without playing it.
#   tools/frames.sh <film.mp4> <out_dir> [fps=1]
set -euo pipefail
src=$1; dir=$2; fps=${3:-1}
mkdir -p "$dir"
ffmpeg -hide_banner -loglevel error -y -i "$src" -vf "fps=${fps}" "$dir/f%03d.png"
ls "$dir" | wc -l
