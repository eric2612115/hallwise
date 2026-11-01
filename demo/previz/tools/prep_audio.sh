#!/bin/zsh
# Copies the real v5 guest audio (and the v4 waiter + hall bed) into public/audio,
# and makes stand-in clips for the LIVE lines that have no recording yet (macOS `say`).
# Stand-ins are for timing only; nothing here is final sound.
set -e
PREVIZ=/Users/eric-air/Projects/Hackathon/Meta/demo/previz
V5=/private/tmp/claude-501/-Users-eric-air-Projects-Hackathon/5b519b28-54f4-4d88-b96d-e944df388e04/scratchpad/rehearsal-v5
V4=/Users/eric-air/Projects/Hackathon/Meta/demo/rig/v4
RIG=/Users/eric-air/Projects/Hackathon/Meta/demo/rig
FF=/opt/homebrew/bin/ffmpeg
OUT=$PREVIZ/public/audio
mkdir -p $OUT/say

# Guest cues, the v5 casting (mix/cast-v5-final.json).
cp $V5/cues/leo-01@alan/phoneL-leo-01.wav          $OUT/phoneL-leo-01.wav
cp $V5/cues/leo-02@alan/phoneL-leo-02.wav          $OUT/phoneL-leo-02.wav
cp $V5/cues/sofa-chat@fr1/mac1-margaux-01.wav      $OUT/mac1-margaux-01.wav
cp $V5/cues/sofa-chat@fr1/mac2-julien-01.wav       $OUT/mac2-julien-01.wav
cp $V5/cues/sofa-intros@lison/mac1-margaux-02.wav  $OUT/mac1-margaux-02.wav
cp $V5/cues/sofa-intros@lison/mac2-julien-02.wav   $OUT/mac2-julien-02.wav
cp $V5/cues/margaux-03@lison/mac1-margaux-03.wav   $OUT/mac1-margaux-03.wav
cp $V5/cues/julien-03@marcel/mac2-julien-03.wav    $OUT/mac2-julien-03.wav
cp $V5/cues/kenji-call@taro/iphoneK-kenji-00.wav   $OUT/iphoneK-kenji-00.wav
cp $V5/cues/table-intros@ruhaan/mac3-02-siddharth.wav $OUT/mac3-02-siddharth.wav
cp $V5/cues/table-intros@ruhaan/iphoneK-kenji-01.wav  $OUT/iphoneK-kenji-01.wav
cp $V5/cues/kenji-02@taro/iphoneK-kenji-02.wav     $OUT/iphoneK-kenji-02.wav
# Kenji's murmur is cut (DIRECTION.md): trim the file after "Friday is better." (speech ends 5.91 s).
$FF -y -loglevel error -i $V5/cues/kenji-03@taro/iphoneK-kenji-03.wav -af "atrim=0:6.5,afade=t=out:st=6.3:d=0.2" -ar 48000 -ac 1 -c:a pcm_s16le $OUT/iphoneK-kenji-03.wav
cp $V4/mac3-01-waiter.wav                           $OUT/mac3-01-waiter.wav
# The Chloé exchange (rig-v5/CUES-additions.md): Margaux's two answers and Eric's three stand-ins.
cp $V5/rig-v5/mac1-margaux-02a.wav                 $OUT/mac1-margaux-02a.wav
cp $V5/rig-v5/mac1-margaux-02b.wav                 $OUT/mac1-margaux-02b.wav
for n in 1 2 3; do cp $V5/rig-v5/standin-eric-chloe-$n.wav $OUT/standin-eric-chloe-$n.wav; done
# The hall bed, re-encoded to 48 kHz mono so it loops cleanly.
$FF -y -loglevel error -i $RIG/tv-hall-bed.wav -ar 48000 -ac 1 -c:a pcm_s16le $OUT/tv-hall-bed.wav

# Eric's rehearsal stand-ins (rehearsal-v5/eric), where the line is unchanged.
for n in 03 04 05 06 08 09 11; do cp $V5/eric/eric-$n.wav $OUT/eric-$n.wav; done

# New LIVE lines: macOS say, for timing only.
say_wav() { # voice, name, text
  say -v "$1" -o $OUT/say/$2.aiff "$3"
  $FF -y -loglevel error -i $OUT/say/$2.aiff -ar 48000 -ac 1 -c:a pcm_s16le $OUT/say/$2.wav
  rm -f $OUT/say/$2.aiff
}
say_wav Daniel   eric-bed-1      "Great to meet you at... at..."
say_wav Daniel   eric-bed-2      "...Yeah."
say_wav Samantha friend-knock    "Eric! People are here."
say_wav Daniel   eric-wear       "So tonight, I wear this. I don't type a thing."
say_wav Samantha friend-come     "Eric, come. You should meet Margaux and Julien."
say_wav Daniel   eric-whisper    "I don't speak any French. At all."
say_wav Samantha friend-intro    "Margaux, Julien, this is Eric. He makes the badge."
say_wav Daniel   eric-chloe      "Do you know Chloé?"
say_wav Daniel   eric-itdoes     "...It does."
say_wav Daniel   eric-japanese   "...Or Japanese."
say_wav Daniel   eric-progress   "Progress."

# A phone buzz (two short 180 Hz bursts) for the live notifications.
$FF -y -loglevel error -f lavfi -i "sine=frequency=180:duration=0.18" -f lavfi -i "anullsrc=r=48000:cl=mono:d=0.1" -f lavfi -i "sine=frequency=180:duration=0.18" -filter_complex "[0][1][2]concat=n=3:v=0:a=1,volume=0.5" -ar 48000 -ac 1 -c:a pcm_s16le $OUT/buzz.wav

echo "prepared:"; for f in $OUT/*.wav $OUT/say/*.wav; do printf "  %-28s %s\n" "$(basename $f)" "$(/opt/homebrew/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 $f)"; done
