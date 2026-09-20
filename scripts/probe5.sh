#!/usr/bin/env bash
set -uo pipefail
API="https://diavgeia.gov.gr/opendata"; UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; D="6296"; mkdir -p "$OUT"
get(){ curl -sS -A "$UA" -H 'Accept: application/json' --max-time 30 "$1"; sleep 0.35; }
hr(){ echo; echo "===== $1 ====="; }
pdf(){ curl -sS -A "$UA" -L --max-time 60 "https://diavgeia.gov.gr/doc/$1" -o "$2"; }

hr "A. THE REAL 2024 BUDGET"
for a in ΨΞΕΟΩΗ6-2ΥΑ 66ΛΧΩΗ6-ΟΕΚ; do
  echo "--- $a"; pdf "$a" "$OUT/b_$a.pdf"
  pdftotext -layout "$OUT/b_$a.pdf" "$OUT/b_$a.txt" 2>/dev/null
  echo "pages=$(pdfinfo "$OUT/b_$a.pdf" 2>/dev/null|awk '/^Pages/{print $2}') chars=$(wc -c <"$OUT/b_$a.txt")"
  grep -nE "ΓΕΝΙΚΟ ΣΥΝΟΛΟ|ΣΥΝΟΛΟ ΕΞΟΔΩΝ|ΣΥΝΟΛΟ ΕΣΟΔΩΝ|ΑΝΑΚΕΦΑΛΑΙΩΣΗ" "$OUT/b_$a.txt" | head -12
  echo "  top numbers:"
  grep -oE '[0-9]{1,3}(\.[0-9]{3}){2,},[0-9]{2}' "$OUT/b_$a.txt" | tr -d '.' | tr ',' '.' | sort -rn | uniq | head -6
done

hr "B. MONTHLY BUDGET EXECUTION STATEMENTS — the reconciliation denominator"
: > "$OUT/exec.ndjson"
for h in "2024-01-01 2024-06-30" "2024-07-01 2024-12-31" "2025-01-01 2025-06-30" "2025-07-01 2025-12-31"; do
  set -- $h
  get "$API/search.json?org=$D&type=$(printf %s 'Β.3'|jq -sRr @uri)&from_issue_date=$1&to_issue_date=$2&size=200" \
    | jq -c '.decisions[]?' >> "$OUT/exec.ndjson"
done
jq -r 'select(.subject|test("ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ|ΕΚΤΕΛΕΣΗΣ ΠΡΟΥΠΟΛΟΓΙΣΜΟΥ"))
  | [.ada,(.issueDate/1000|strftime("%Y-%m")),(.subject[0:70])]|@tsv' "$OUT/exec.ndjson" | sort -k2 | column -t -s$'\t'

hr "C. PARSE ONE EXECUTION STATEMENT"
EADA=$(jq -r 'select(.subject|test("ΕΚΤΕΛΕΣΗΣ ΠΡΟ.ΠΟΛΟΓΙΣΜΟΥ")) | select(.subject|test("ΔΗΜΟΥ ΤΗΝΟΥ")) | .ada' "$OUT/exec.ndjson" | head -1)
echo "ADA: ${EADA:-NONE}"
[ -n "${EADA:-}" ] && { pdf "$EADA" "$OUT/exec.pdf"; pdftotext -layout "$OUT/exec.pdf" - 2>/dev/null | head -60; }

hr "D. ADVANCED SEARCH SYNTAX — can we reach searchTerms?"
for attempt in \
  "q=giverAFM:099361052" \
  "query=giverAFM:099361052" \
  "advanced=true&q=giverAFM:099361052" \
  "q=organizationUid:6296"; do
  printf '%-42s ' "$attempt"
  get "$API/search/advanced.json?$attempt&size=1" | jq -r '"total="+((.info.total//"ERR")|tostring)' 2>/dev/null || echo "endpoint 404"
done
echo "--- plain /search with q=organizationUid:"
get "$API/search.json?q=organizationUid:6296&size=1" | jq -r '.info.query[0:150]'

hr "E. WORDPRESS INVENTORY"
for t in posts pages media lsvr_document lsvr_notice lsvr_event lsvr_person lsvr_listing; do
  printf '%-16s ' "$t"
  curl -sS -A "$UA" -o /dev/null -D - --max-time 25 \
    "https://dimostinou.gr/wp-json/wp/v2/$t?per_page=1" 2>/dev/null \
    | awk -F': ' '/[Xx]-WP-Total:/{gsub(/\r/,"");print "total="$2} /^HTTP/{c=$0} END{if(!/Total/)print ""}' \
    || echo "-"
done
echo "--- oldest & newest post:"
curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/posts?per_page=1&order=asc&orderby=date' | jq -r '.[0]|.date+"  "+.title.rendered' 2>/dev/null
curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/posts?per_page=1' | jq -r '.[0]|.date+"  "+.title.rendered' 2>/dev/null
echo "--- categories:"
curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/categories?per_page=50' | jq -r '.[]?|[(.count|tostring),.slug,.name]|@tsv' 2>/dev/null | sort -rn | head -25 | column -t -s$'\t'

hr "F. FIND THE YOUTUBE CHANNEL"
curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/posts?search=live%20%CE%A3%CF%85%CE%BD%CE%B5%CE%B4%CF%81%CE%AF%CE%B1%CF%83%CE%B7&per_page=3' \
  | jq -r '.[]?|.link' 2>/dev/null
echo "--- youtube urls found in those posts:"
curl -sS -A "$UA" --max-time 25 'https://dimostinou.gr/wp-json/wp/v2/posts?search=live&per_page=10' \
  | grep -oE 'https?://(www\.)?(youtube\.com|youtu\.be)/[A-Za-z0-9_@?=/&.-]+' | sort -u | head -20

hr "G. KIMDIS — proper endpoints via data.gov.gr"
curl -sS -A "$UA" --max-time 30 'https://data.gov.gr/api/3/action/package_show?id=khmahe-api' \
  | jq -r '.result | {title, notes: (.notes[0:400]), url, resources: [.resources[]?|{name,url,format}]}' 2>/dev/null
echo "--- try the documented help page as JSON:"
curl -sS -A "$UA" --max-time 25 -H 'Accept: application/json' \
  'https://cerpp.eprocurement.gov.gr/kimds-opendata/api/searchContracts?searchTerm=&page=0' \
  | head -c 600; echo

hr DONE
