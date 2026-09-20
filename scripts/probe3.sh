#!/usr/bin/env bash
set -uo pipefail
API="https://diavgeia.gov.gr/opendata"
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; D="6296"; mkdir -p "$OUT"
ENTS="6296 50256 52103 53404 53752 53952 54500 55049 100011442 100011650 100032995"
get(){ curl -sS -A "$UA" -H 'Accept: application/json' "$1"; sleep 0.35; }
hr(){ echo; echo "===== $1 ====="; }
tot(){ get "$1" | jq -r '.info.total // "ERR"'; }

hr "A. PAGING"
for p in 0 1 2 3; do
  r=$(get "$API/search.json?org=$D&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=500&page=$p")
  printf 'page=%s actualSize=%-5s first=%-14s last=%s\n' "$p" \
    "$(jq -r '.info.actualSize' <<<"$r")" \
    "$(jq -r '.decisions[0].ada // "-"' <<<"$r")" \
    "$(jq -r '.decisions[-1].ada // "-"' <<<"$r")"
done

hr "B. FULL 2024 HARVEST for 6296 (paged)"
: > "$OUT/2024.ndjson"
for half in "2024-01-01 2024-06-30" "2024-07-01 2024-12-31"; do
  set -- $half
  for p in 0 1 2 3 4 5; do
    r=$(get "$API/search.json?org=$D&from_issue_date=$1&to_issue_date=$2&size=500&page=$p")
    n=$(jq -r '.decisions|length' <<<"$r"); [ "$n" -eq 0 ] && break
    jq -c '.decisions[]' <<<"$r" >> "$OUT/2024.ndjson"
  done
done
echo "acts harvested: $(wc -l < "$OUT/2024.ndjson")"

echo "--- decisionTypeId distribution:"
jq -r '.decisionTypeId' "$OUT/2024.ndjson" | sort | uniq -c | sort -rn

echo "--- % of acts carrying ANY amount:"
jq -r 'if (.extraFieldValues|tostring|test("amount")) then "HAS" else "NONE" end' \
  "$OUT/2024.ndjson" | sort | uniq -c

echo "--- extraFieldValues key union:"
jq -r '.extraFieldValues|keys[]?' "$OUT/2024.ndjson" | sort | uniq -c | sort -rn

echo "--- distinct statuses:"
jq -r '.status' "$OUT/2024.ndjson" | sort | uniq -c

echo "--- top 12 units by act count:"
jq -r '.unitIds[]?' "$OUT/2024.ndjson" | sort | uniq -c | sort -rn | head -12

hr "C. 2024 MONEY: Β.2.2 payments summed, top beneficiaries"
jq -r 'select(.decisionTypeId=="Β.2.2") | .extraFieldValues.sponsor[]?
       | [(.expenseAmount.amount//0|tostring), (.sponsorAFMName.afm//"-"), (.sponsorAFMName.name//"-")]
       | @tsv' "$OUT/2024.ndjson" > "$OUT/pay2024.tsv"
echo "payment rows: $(wc -l < "$OUT/pay2024.tsv")"
awk -F'\t' '{s+=$1} END{printf "TOTAL 2024 Β.2.2 = %.2f EUR\n", s}' "$OUT/pay2024.tsv"
echo "--- top 15 beneficiaries:"
awk -F'\t' '{s[$2"\t"$3]+=$1} END{for(k in s) printf "%.2f\t%s\n", s[k], k}' "$OUT/pay2024.tsv" \
  | sort -rn | head -15 | column -t -s$'\t'
echo "--- rows with MISSING afm:"
awk -F'\t' '$2=="-"||$2==""{c++} END{print c+0}' "$OUT/pay2024.tsv"

hr "D. WHERE ARE THE DIRECT AWARDS? 2024 H1 counts by type"
for t in "Δ.1" "Δ.2.1" "Δ.2.2" "2.4.4" "2.4.2" "2.4.7.1"; do
  printf '%-10s %s\n' "$t" "$(tot "$API/search.json?org=$D&type=$(printf %s "$t"|jq -sRr @uri)&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=1")"
done
echo "--- sample 2.4.4 subjects:"
get "$API/search.json?org=$D&type=$(printf %s '2.4.4'|jq -sRr @uri)&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=5" \
  | jq -r '.decisions[]? | .ada + "  " + (.subject[0:95])'

hr "E. ENTITY ACTIVE WINDOWS (acts per year, both halves summed)"
printf '%-11s' "uid"; for y in $(seq 2011 2026); do printf '%6s' "$y"; done; echo
for u in $ENTS; do
  printf '%-11s' "$u"
  for y in $(seq 2011 2026); do
    a=$(tot "$API/search.json?org=$u&from_issue_date=$y-01-01&to_issue_date=$y-06-30&size=1")
    b=$(tot "$API/search.json?org=$u&from_issue_date=$y-07-01&to_issue_date=$y-12-31&size=1")
    printf '%6s' "$((a+b))"
  done
  echo
done

hr "F. REVOKED ACTS - status=all vs default, per year"
for y in 2016 2020 2024; do
  d=$(tot "$API/search.json?org=$D&from_issue_date=$y-01-01&to_issue_date=$y-06-30&size=1")
  a=$(tot "$API/search.json?org=$D&from_issue_date=$y-01-01&to_issue_date=$y-06-30&status=all&size=1")
  printf '%s  published=%-6s all=%-6s diff=%s\n' "$y" "$d" "$a" "$((a-d))"
done

hr "G. TYPE DETAILS ENDPOINT - raw shape"
get "$API/types/$(printf %s 'Β.2.2'|jq -sRr @uri)/details.json" > "$OUT/type_b22.json"
head -c 1500 "$OUT/type_b22.json"; echo

hr DONE
