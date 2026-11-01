#!/bin/zsh
# Checks out/previz.mp4: length, a frame every 5 s, contact sheets, and the audio level per beat.
set -e
setopt +o nomatch
PREVIZ=/Users/eric-air/Projects/Hackathon/Meta/demo/previz
FF=/opt/homebrew/bin/ffmpeg
FP=/opt/homebrew/bin/ffprobe
MP4=$PREVIZ/out/previz.mp4
FR=$PREVIZ/out/frames
mkdir -p $FR
rm -f $FR/f_*.png $FR/sheet_*.png

echo "== container"
$FP -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of default=noprint_wrappers=1 $MP4

echo "== frames every 5 s"
$FF -y -loglevel error -i $MP4 -vf "fps=1/5" -start_number 0 $FR/f_%02d.png
ls $FR/f_*.png | wc -l

# Four readable sheets of 3x3 (640 px wide each tile), and one 6x6 overview.
for i in 0 1 2 3; do
  start=$((i*9))
  $FF -y -loglevel error -start_number $start -i $FR/f_%02d.png -frames:v 1 -vf "scale=640:-1,tile=3x3:padding=4:color=white" $FR/sheet_$i.png
done
$FF -y -loglevel error -start_number 0 -i $FR/f_%02d.png -frames:v 1 -vf "scale=320:-1,tile=6x6:padding=3:color=white" $FR/sheet_all.png

echo "== audio level per beat (mean dBFS; silence beats should be the quietest)"
python3 - <<'EOF'
import json, subprocess, re
sl = json.load(open('/Users/eric-air/Projects/Hackathon/Meta/demo/previz/shotlist.json'))
mp4 = '/Users/eric-air/Projects/Hackathon/Meta/demo/previz/out/previz.mp4'
for b in sl['beats']:
    out = subprocess.run(['/opt/homebrew/bin/ffmpeg', '-v', 'info', '-ss', str(b['start']), '-t', str(b['duration']), '-i', mp4,
                          '-vn', '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True).stderr
    m = re.search(r'mean_volume: ([-\d.]+) dB', out)
    mx = re.search(r'max_volume: ([-\d.]+) dB', out)
    flag = 'SILENCE' if b.get('silence') else ('cold' if b['temp'] == 'cold' else 'hot')
    print(f"  {b['id']:2d} {b['start']:6.1f}-{b['end']:6.1f} {flag:8s} mean {m.group(1) if m else '?':>7} dB  max {mx.group(1) if mx else '?':>6} dB  {b['name']}")
EOF
