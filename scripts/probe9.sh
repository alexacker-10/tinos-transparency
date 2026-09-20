#!/usr/bin/env bash
set -uo pipefail
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; mkdir -p "$OUT"
hr(){ echo; echo "===== $1 ====="; }
DIMOS="UCDY6BWFDvNgUg9YeYkmhS7g"
SEP='|'

hr "A. DIMOS CHANNEL — videos tab, with approximate dates"
yt-dlp --flat-playlist --skip-download --no-warnings \
  --extractor-args "youtubetab:approximate_date" \
  --print "%(upload_date)s|%(duration)s|%(id)s|%(title)s" \
  "https://www.youtube.com/channel/$DIMOS/videos" 2>/dev/null > "$OUT/yt_v.psv"
echo "rows: $(wc -l < "$OUT/yt_v.psv")"
head -3 "$OUT/yt_v.psv"

hr "B. DIMOS CHANNEL — streams tab"
yt-dlp --flat-playlist --skip-download --no-warnings \
  --extractor-args "youtubetab:approximate_date" \
  --print "%(upload_date)s|%(duration)s|%(id)s|%(title)s" \
  "https://www.youtube.com/channel/$DIMOS/streams" 2>/dev/null > "$OUT/yt_s.psv"
echo "rows: $(wc -l < "$OUT/yt_s.psv")"
head -3 "$OUT/yt_s.psv"

hr "C. MERGE + DEDUP by video id"
cat "$OUT/yt_v.psv" "$OUT/yt_s.psv" | gawk -F'|' '!seen[$3]++' > "$OUT/yt_all.psv"
echo "unique videos: $(wc -l < "$OUT/yt_all.psv")"

hr "D. BY YEAR"
gawk -F'|' '{y=substr($1,1,4); if(y ~ /^[0-9]{4}$/) c[y]++ } END{for(k in c) printf "%s  %4d\n", k, c[k]}' \
  "$OUT/yt_all.psv" | sort

hr "E. COUNCIL SESSIONS ONLY"
gawk -F'|' 'tolower($4) ~ /συνεδρ|ΣΥΝΕΔΡ/ || $4 ~ /Συνεδρίασ|ΣΥΝΕΔΡΙΑΣ|συνεδρίασ/' "$OUT/yt_all.psv" \
  > "$OUT/yt_sessions.psv"
echo "session videos: $(wc -l < "$OUT/yt_sessions.psv")"
gawk -F'|' '{y=substr($1,1,4); if(y ~ /^[0-9]{4}$/) c[y]++} END{for(k in c) printf "%s  %4d\n", k, c[k]}' \
  "$OUT/yt_sessions.psv" | sort

hr "F. TRANSCRIPTION WORKLOAD"
gawk -F'|' '$2 ~ /^[0-9]+$/ {s+=$2; n++} END{printf "all videos:    %d with duration, %.1f hours total\n", n, s/3600}' "$OUT/yt_all.psv"
gawk -F'|' '$2 ~ /^[0-9]+$/ {s+=$2; n++} END{printf "sessions only: %d with duration, %.1f hours total\n", n, s/3600}' "$OUT/yt_sessions.psv"
echo "--- 10 longest sessions:"
gawk -F'|' '$2 ~ /^[0-9]+$/ {printf "%5.2fh  %s  %s\n", $2/3600, $1, substr($4,1,62)}' "$OUT/yt_sessions.psv" \
  | sort -rn | head -10

hr "G. CAPTIONS on a real session video"
V=$(gawk -F'|' '$2 ~ /^[0-9]+$/ && $2>3000 {print $3; exit}' "$OUT/yt_sessions.psv")
echo "video: $V"
yt-dlp --list-subs --skip-download --no-warnings "https://www.youtube.com/watch?v=$V" 2>&1 | head -25

hr "H. AUDIO SIZE ESTIMATE — one session"
yt-dlp -f "bestaudio" --skip-download --no-warnings \
  --print "%(duration)s s | %(filesize_approx)s bytes | %(acodec)s | %(abr)s kbps" \
  "https://www.youtube.com/watch?v=$V" 2>/dev/null

hr "I. LOCAL MEDIA — local-government coverage volume by year"
for spec in "tinosnews.gr|topiki-aftodioikisi" "tinostoday.gr|%ce%b4%ce%ae%ce%bc%ce%bf%cf%82-%cf%84%ce%ae%ce%bd%ce%bf%cf%85"; do
  d="${spec%%|*}"; slug="${spec##*|}"
  echo "--- $d / $slug"
  cid=$(curl -sS -A "$UA" --max-time 25 "https://$d/wp-json/wp/v2/categories?slug=$slug" | jq -r '.[0].id')
  echo "    category id: $cid"
  for y in 2019 2021 2023 2025 2026; do
    n=$(curl -sS -A "$UA" -I --max-time 25 \
      "https://$d/wp-json/wp/v2/posts?categories=$cid&after=${y}-01-01T00:00:00&before=${y}-12-31T23:59:59&per_page=1" \
      2>/dev/null | tr -d '\r' | grep -i '^x-wp-total:' | cut -d' ' -f2)
    printf '    %s: %s\n' "$y" "${n:-0}"
  done
done

hr "J. TINOSNEWS PODCAST — is it audio?"
curl -sS -A "$UA" -L --max-time 30 'https://tinosnews.gr/category/podcast/feed' -o "$OUT/podcast.xml"
echo "items: $(grep -c '<item>' "$OUT/podcast.xml")"
grep -oP '(?<=<title>)[^<]{5,90}' "$OUT/podcast.xml" | head -8
echo "--- enclosures / audio urls:"
grep -oE 'https?://[^"<> ]+\.(mp3|m4a|wav)' "$OUT/podcast.xml" | head -5
grep -oE '<enclosure[^>]*>' "$OUT/podcast.xml" | head -3

hr "K. BLOGGER LEGACY — sample the oldest posts"
curl -sS -A "$UA" --max-time 40 \
  'http://www.dimostinou.eu/feeds/posts/default?alt=json&max-results=5&start-index=4630' -o "$OUT/blogger_old.json"
jq -r '.feed.entry[]? | (.published."$t"[0:10]) + "  " + (.title."$t"[0:70])' "$OUT/blogger_old.json" 2>/dev/null
echo "--- newest 5:"
curl -sS -A "$UA" --max-time 40 \
  'http://www.dimostinou.eu/feeds/posts/default?alt=json&max-results=5' -o "$OUT/blogger_new.json"
jq -r '.feed.entry[]? | (.published."$t"[0:10]) + "  " + (.title."$t"[0:70])' "$OUT/blogger_new.json" 2>/dev/null

hr DONE
