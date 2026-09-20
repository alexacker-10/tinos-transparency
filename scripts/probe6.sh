#!/usr/bin/env bash
set -uo pipefail
API="https://diavgeia.gov.gr/opendata"; UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; D="6296"; mkdir -p "$OUT"
get(){ curl -sS -A "$UA" -H 'Accept: application/json' --max-time 30 "$1"; sleep 0.35; }
hr(){ echo; echo "===== $1 ====="; }
enc(){ printf %s "$1" | jq -sRr @uri; }

hr "A. LUCENE q= SYNTAX — FULL query echo, no truncation"
for Q in 'organizationUid:6296' \
         'organizationUid:6296 AND decisionTypeId:"Β.2.2"' \
         'giverAFM:099361052' \
         'receiverAFM:099361052' \
         'afm:099361052' \
         'cpv:45000000' ; do
  echo "--- q=$Q"
  get "$API/search.json?q=$(enc "$Q")&size=1" | jq -r '"    total=\(.info.total)\n    exec: \(.info.query)"'
done

hr "B. WHAT IS 31,033,256.60 ?  (context lines in the budget)"
grep -nB2 -A2 "31\.033\.256,60" "$OUT/b_ΨΞΕΟΩΗ6-2ΥΑ.txt" | head -30
echo "--- the ΑΝΑΚΕΦΑΛΑΙΩΣΗ block:"
sed -n '3042,3080p' "$OUT/b_ΨΞΕΟΩΗ6-2ΥΑ.txt"

hr "C. PARSE THE DECEMBER 2024 EXECUTION STATEMENT — expenditure side + totals"
curl -sS -A "$UA" -L --max-time 60 "https://diavgeia.gov.gr/doc/Ψ68ΩΩΗ6-3ΓΦ" -o "$OUT/exec2412.pdf"
pdftotext -layout "$OUT/exec2412.pdf" "$OUT/exec2412.txt"
echo "pages=$(pdfinfo "$OUT/exec2412.pdf"|awk '/^Pages/{print $2}')"
echo "--- section headers:"
grep -nE "^\s*(ΕΣΟΔΑ|ΕΞΟΔΑ|ΣΥΝΟΛΟ|ΓΕΝΙΚΟ)" "$OUT/exec2412.txt" | head -20
echo "--- expenditure columns header:"
grep -n "Ενταλθέντα\|Πληρωθέντα\|Δεσμευθέντα\|Τιμολογηθέντα" "$OUT/exec2412.txt" | head -5
echo "--- last 30 lines (totals):"
tail -30 "$OUT/exec2412.txt"

hr "D. MACHINE-PARSE TEST: extract ΚΑΕ rows"
awk '
  match($0, /^[[:space:]]*([0-9]{2}\.)?[0-9]{4}(\.[0-9]{4})?[[:space:]]+/) {
    n=split($0,f," "); kae=f[1];
    a=f[n-2]; b=f[n-1]; c=f[n];
    if (c ~ /^[0-9.]+,[0-9]{2}$/) printf "%s\t%s\t%s\t%s\n", kae, a, b, c
  }' "$OUT/exec2412.txt" > "$OUT/kae2412.tsv"
echo "rows parsed: $(wc -l < "$OUT/kae2412.tsv")"
head -8 "$OUT/kae2412.tsv" | column -t -s$'\t'
echo "--- sum of last column (naive):"
awk -F'\t' '{gsub(/\./,"",$4); gsub(/,/,".",$4); s+=$4} END{printf "%.2f\n", s}' "$OUT/kae2412.tsv"

hr "E. MISSING 2025-06 STATEMENT — does it exist under another type?"
for t in "Β.3" "2.4.2" "Α.2"; do
  printf 'type %-8s ' "$t"
  get "$API/search.json?org=$D&type=$(enc "$t")&from_issue_date=2025-06-01&to_issue_date=2025-08-15&size=50" \
    | jq -r '[.decisions[]?|select(.subject|test("ΕΚΤΕΛΕΣΗ|ΕΚΤΕΛΕΣΗΣ"))|.ada+" "+(.subject[0:60])]|length|tostring' 
done
get "$API/search.json?org=$D&from_issue_date=2025-06-01&to_issue_date=2025-08-15&size=500" \
  | jq -r '.decisions[]?|select(.subject|test("ΕΚΤΕΛΕΣΗΣ ΠΡΟ"))|.ada+"  "+(.issueDate/1000|strftime("%Y-%m-%d"))+"  "+(.subject[0:75])'

hr "F. WORDPRESS TOTALS (fixed header parse)"
for t in posts pages media lsvr_document lsvr_notice lsvr_event lsvr_person lsvr_listing; do
  h=$(curl -sS -A "$UA" -I --max-time 25 "https://dimostinou.gr/wp-json/wp/v2/$t?per_page=1" 2>/dev/null | tr -d '\r')
  printf '%-16s total=%-6s pages=%s\n' "$t" \
    "$(grep -i '^x-wp-total:' <<<"$h" | cut -d' ' -f2)" \
    "$(grep -i '^x-wp-totalpages:' <<<"$h" | cut -d' ' -f2)"
done

hr "G. FIND THE YOUTUBE CHANNEL — read a live-stream post body"
curl -sS -A "$UA" --max-time 30 \
  'https://dimostinou.gr/wp-json/wp/v2/posts?search=Παρακολουθήστε%20live&per_page=5&_fields=id,date,link,content' \
  > "$OUT/livepost.json"
jq -r '.[]? | .date+"  "+.link' "$OUT/livepost.json"
echo "--- URLs inside those post bodies:"
jq -r '.[]?.content.rendered' "$OUT/livepost.json" \
  | grep -oE 'https?://[^"<> ]*(youtube|youtu\.be|facebook|fb\.watch|zoom|webex|teams)[^"<> ]*' \
  | sed 's/&amp;/\&/g' | sort -u | head -20
echo "--- iframe srcs:"
jq -r '.[]?.content.rendered' "$OUT/livepost.json" | grep -oE '<iframe[^>]*src="[^"]*"' | head -10

hr "H. VIDEO CATEGORY — Βίντεο Συνεδριάσεων (46 posts)"
CID=$(curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/categories?slug=vinteo-synedriaseon' | jq -r '.[0].id')
echo "category id: $CID"
curl -sS -A "$UA" --max-time 30 "https://dimostinou.gr/wp-json/wp/v2/posts?categories=$CID&per_page=5&_fields=date,title,link,content" \
  > "$OUT/vidposts.json"
jq -r '.[]? | .date+"  "+.title.rendered' "$OUT/vidposts.json"
echo "--- video URLs:"
jq -r '.[]?.content.rendered' "$OUT/vidposts.json" \
  | grep -oE 'https?://[^"<> ]*(youtube|youtu\.be)[^"<> ]*' | sed 's/&amp;/\&/g' | sort -u

hr "I. LEGACY BLOGGER SITE — dimostinou.eu"
curl -sS -A "$UA" --max-time 30 'https://www.dimostinou.eu/feeds/posts/default?alt=json&max-results=1' \
  | jq -r '.feed | {title:.title."$t", total:.openSearch$totalResults."$t", updated:.updated."$t"}' 2>/dev/null \
  || curl -sS -A "$UA" --max-time 30 'http://www.dimostinou.eu/feeds/posts/default?alt=json&max-results=1' | head -c 400

hr "J. KIMDIS ACCESS PATH"
curl -sS -A "$UA" -o /dev/null -w 'promitheus portal http=%{http_code}\n' --max-time 25 -L 'https://www.promitheus.gov.gr/'
curl -sS -A "$UA" --max-time 25 -L 'https://data.gov.gr/api/3/action/package_show?id=khmahe-api' \
  | jq -r '.result | {maintainer, author, license_title, num_resources, (.extras//[])|tostring}' 2>/dev/null

hr DONE
