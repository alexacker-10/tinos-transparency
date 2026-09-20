#!/usr/bin/env bash
set -uo pipefail
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; mkdir -p "$OUT"
hr(){ echo; echo "===== $1 ====="; }
declare -A CH=(
  [dimos]="UCDY6BWFDvNgUg9YeYkmhS7g"
  [tinosnews]="UCikCfcrFBIbwhh68yrcP5KQ"
  [tinostoday]="UCP6pHhVmLU1fjECEk-IDGxA"
)

hr "A. RSS FEEDS (keyless, last ~15 each)"
for k in "${!CH[@]}"; do
  echo "--- $k (${CH[$k]})"
  curl -sS -A "$UA" --max-time 30 \
    "https://www.youtube.com/feeds/videos.xml?channel_id=${CH[$k]}" -o "$OUT/rss_$k.xml"
  echo "    title: $(grep -m1 -oP '(?<=<title>)[^<]+' "$OUT/rss_$k.xml")"
  echo "    items: $(grep -c '<entry>' "$OUT/rss_$k.xml")"
  grep -oP '(?<=<published>)[^<]+' "$OUT/rss_$k.xml" | head -3 | sed 's/^/    /'
done

hr "B. FULL CHANNEL ENUMERATION via yt-dlp (no API key)"
for k in "${!CH[@]}"; do
  echo "--- $k"
  yt-dlp --flat-playlist --skip-download --no-warnings \
    --print "%(upload_date)s\t%(duration)s\t%(id)s\t%(title).70s" \
    "https://www.youtube.com/channel/${CH[$k]}/videos" 2>/dev/null > "$OUT/yt_$k.tsv"
  echo "    videos: $(wc -l < "$OUT/yt_$k.tsv")"
  echo "    oldest / newest:"
  sort "$OUT/yt_$k.tsv" | sed -n '1p;$p' | sed 's/^/      /'
done

hr "C. DIMOS CHANNEL — council sessions only, by year"
gawk -F'\t' '$4 ~ /Συνεδρίασ|συνεδρίασ|ΣΥΝΕΔΡΙΑΣ/ {print substr($1,1,4)}' "$OUT/yt_dimos.tsv" \
  | sort | uniq -c
echo "--- total duration of all dimos videos (hours):"
gawk -F'\t' '$2 ~ /^[0-9]+$/ {s+=$2} END{printf "%.1f\n", s/3600}' "$OUT/yt_dimos.tsv"
echo "--- 10 longest:"
gawk -F'\t' '$2 ~ /^[0-9]+$/ {printf "%6.1fh  %s  %s\n", $2/3600, $1, substr($4,1,60)}' "$OUT/yt_dimos.tsv" \
  | sort -rn | head -10

hr "D. LIVE STREAMS + UNLISTED? check tabs"
for tab in videos streams playlists; do
  printf '%-12s ' "$tab"
  yt-dlp --flat-playlist --skip-download --no-warnings --print "%(id)s" \
    "https://www.youtube.com/channel/${CH[dimos]}/$tab" 2>/dev/null | wc -l
done

hr "E. CAPTIONS — does YouTube have any Greek subs already?"
V=$(head -1 "$OUT/yt_dimos.tsv" | cut -f3)
echo "sample video: $V"
yt-dlp --list-subs --skip-download --no-warnings "https://www.youtube.com/watch?v=$V" 2>&1 | head -20

hr "F. LOCAL MEDIA SITES — wp-json open?"
for d in tinosnews.gr tinostoday.gr; do
  echo "--- $d"
  curl -sS -A "$UA" -o /dev/null --max-time 25 \
    -w "    wp-json http=%{http_code}\n" "https://$d/wp-json/"
  h=$(curl -sS -A "$UA" -I --max-time 25 "https://$d/wp-json/wp/v2/posts?per_page=1" 2>/dev/null | tr -d '\r')
  echo "    posts total=$(grep -i '^x-wp-total:' <<<"$h" | cut -d' ' -f2)"
  curl -sS -A "$UA" --max-time 25 "https://$d/wp-json/wp/v2/categories?per_page=100" \
    | jq -r '.[]?|select(.name|test("Αυτοδιοίκησ|Δήμο|Podcast|Συμβούλ"))|[(.count|tostring),.slug,.name]|@tsv' 2>/dev/null \
    | column -t -s$'\t' | sed 's/^/    /'
done

hr "G. TINOSNEWS PODCAST FEED"
for u in "https://tinosnews.gr/feed/podcast" "https://tinosnews.gr/category/podcast/feed" "https://tinosnews.gr/feed"; do
  printf '%-45s ' "${u#https://}"
  curl -sS -A "$UA" -o /dev/null --max-time 25 -w 'http=%{http_code} type=%{content_type}\n' "$u"
done

hr "H. WAYBACK retry (was offline)"
for d in dimostinou.gr dimostinou.eu; do
  printf '%-16s ' "$d"
  curl -sS -A "$UA" --max-time 40 \
    "http://web.archive.org/cdx/search/cdx?url=$d*&output=json&limit=3&collapse=urlkey" 2>/dev/null | head -c 300
  echo
done

hr DONE
