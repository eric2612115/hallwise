#!/bin/zsh
# Render one PNG per "<composition> <frame> <name>" line on stdin into out/qa, to look at a cut without playing it.
#   printf 'XRay 330 xray_330\nDeckMorph 149 deck_149\n' | tools/stills.sh
set -euo pipefail
mkdir -p out/qa
while read -r comp frame name; do
  [[ -z "${comp:-}" ]] && continue
  npx remotion still src/index.ts "$comp" "out/qa/$name.png" --frame="$frame" 2>&1 | grep -iE "error" || true
  echo "out/qa/$name.png"
done
