#!/usr/bin/env bash
set -uo pipefail
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; K="https://cerpp.eprocurement.gov.gr/khmdhs-opendata"; mkdir -p "$OUT"
hr(){ echo; echo "===== $1 ====="; }

hr "A. KIMDIS — is it really keyless?"
curl -sS -A "$UA" -H 'Accept: application/json' --max-time 40 "$K/request" \
  -o "$OUT/k_probe.json" -w 'http=%{http_code} type=%{content_type} bytes=%{size_download}\n'
head -c 500 "$OUT/k_probe.json"; echo

hr "B. KIMDIS OpenAPI spec — the full endpoint list"
for p in "v3/api-docs" "v3/api-docs/swagger-config" "swagger-ui/index.html"; do
  printf '%-32s ' "$p"
  curl -sS -A "$UA" --max-time 30 -o "$OUT/k_$(basename $p).out" \
    -w 'http=%{http_code} type=%{content_type} bytes=%{size_download}\n' "$K/$p"
done
echo "--- endpoints found:"
jq -r '.paths｜keys[]' "$OUT/k_api-docs.out" 2>/dev/null \
  || jq -r '.paths | keys[]' "$OUT/k_api-docs.out" 2>/dev/null \
  || grep -oE '"/[a-zA-Z0-9/_{}-]+"' "$OUT/k_api-docs.out" 2>/dev/null | sort -u | head -40

hr "C. KIMDIS — Tinos contracts. org uid 6296 (Diavgeia) may or may not match"
for ORG in 6296 800302968; do
  echo "--- organizations: [\"$ORG\"]"
  curl -sS -A "$UA" --max-time 60 -X POST "$K/request?page=0" \
    -H 'Content-Type: application/json' -H 'Accept: application/json' \
    -d "{\"organizations\":[\"$ORG\"],\"dateFrom\":\"2024-01-01\",\"dateTo\":\"2024-12-31\"}" \
    -o "$OUT/k_$ORG.json" -w '    http=%{http_code} bytes=%{size_download}\n'
  jq -r '{total:(.totalElements//.total//"?"), pages:(.totalPages//"?"), first:(.content[0]//empty)}' "$OUT/k_$ORG.json" 2>/dev/null | head -40
done

hr "D. KIMDIS — free-text fallback"
curl -sS -A "$UA" --max-time 60 -X POST "$K/request?page=0" \
  -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -d '{"title":"ΤΗΝΟΥ","dateFrom":"2024-01-01","dateTo":"2024-12-31"}' \
  -o "$OUT/k_text.json" -w 'http=%{http_code} bytes=%{size_download}\n'
jq -r '.content[]? | [.referenceNumber, (.title[0:60])] | @tsv' "$OUT/k_text.json" 2>/dev/null | head -10 | column -t -s$'\t'

hr "E. RE-PARSE execution statement with gawk"
gawk '
/^[[:space:]]*[0-9]/ {
  if (match($0, /^[[:space:]]*([0-9]{2}\.)?[0-9]{4}(\.[0-9]{4})?[[:space:]]/, m)) {
    n=split($0,f," ")
    if (f[n] ~ /^[0-9.]+,[0-9]{2}$/ && f[n-1] ~ /^[0-9.]+,[0-9]{2}$/)
      printf "%s\t%s\t%s\t%s\n", f[1], f[n-2], f[n-1], f[n]
  }
}' "$OUT/exec2412.txt" > "$OUT/kae2412.tsv"
echo "rows: $(wc -l < "$OUT/kae2412.tsv")"
head -6 "$OUT/kae2412.tsv" | column -t -s$'\t'
echo "--- sum of Πληρωθέντα for expenditure KAE (6/7/8/9 prefix):"
gawk -F'\t' '$1 ~ /^(6|7|8|9)/ {v=$4; gsub(/\./,"",v); gsub(/,/,".",v); s+=v} END{printf "%.2f\n", s}' "$OUT/kae2412.tsv"

hr "F. THE TWO 2025-07 STATEMENTS — which months?"
for a in Ρ2ΓΨΩΗ6-ΓΕΗ 9ΡΝΕΩΗ6-8Θ5 602ΣΩΗ6-Ν3Κ; do
  curl -sS -A "$UA" -L --max-time 60 "https://diavgeia.gov.gr/doc/$a" -o "$OUT/e_$a.pdf"
  printf '%-14s %s\n' "$a" "$(pdftotext -layout "$OUT/e_$a.pdf" - 2>/dev/null | grep -m1 'Περίοδος')"
done

hr "G. YOUTUBE — resolve channel from a video id"
for v in OTBlpES4eK4 GuPLO2Vwh20; do
  curl -sS -A "$UA" --max-time 30 \
    "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=$v&format=json" \
    | jq -r '"\(.author_name)  |  \(.author_url)  |  \(.title)"' 2>/dev/null
done

hr "H. HARVEST ALL VIDEO IDS FROM WORDPRESS (46 posts in cat 166)"
: > "$OUT/videos.tsv"
for p in 1 2 3; do
  curl -sS -A "$UA" --max-time 40 \
    "https://dimostinou.gr/wp-json/wp/v2/posts?categories=166&per_page=20&page=$p&_fields=date,title,link,content" \
    | jq -r '.[]? | (.date) + "\t" + (.title.rendered) + "\t" + ([.content.rendered | scan("youtube\\.com/embed/([A-Za-z0-9_-]{11})")[]] | join(","))' \
    >> "$OUT/videos.tsv" 2>/dev/null
done
echo "posts: $(wc -l < "$OUT/videos.tsv")"
gawk -F'\t' '{print $1"  "$3"  "substr($2,1,60)}' "$OUT/videos.tsv" | sort | head -25
echo "--- distinct video ids: $(cut -f3 "$OUT/videos.tsv" | tr ',' '\n' | grep -c . )"

hr "I. LEGACY BLOGGER (http, not https)"
curl -sS -A "$UA" --max-time 40 'http://www.dimostinou.eu/feeds/posts/default?alt=json&max-results=1' -o "$OUT/blogger.json"
jq -r '.feed | "title: \(.title."$t")\ntotal posts: \(.openSearch$totalResults."$t")\nupdated: \(.updated."$t")"' "$OUT/blogger.json" 2>/dev/null \
  || grep -oE '"openSearch\$totalResults":\{"\$t":"[0-9]+"' "$OUT/blogger.json"

hr "J. WAYBACK coverage for both domains"
for d in dimostinou.gr dimostinou.eu; do
  printf '%-16s ' "$d"
  curl -sS -A "$UA" --max-time 40 \
    "http://web.archive.org/cdx/search/cdx?url=$d*&output=json&limit=1&showNumPages=true" || echo "-"
done

hr DONE
