#!/usr/bin/env bash
set -uo pipefail
API="https://diavgeia.gov.gr/opendata"
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; D="6296"; mkdir -p "$OUT"
get(){ curl -sS -A "$UA" -H 'Accept: application/json' "$1"; sleep 0.4; }
hr(){ echo; echo "===== $1 ====="; }
q(){ jq -r '.info.query' ; }

hr "A. CONFIRM THE CLAMP - requested vs executed"
for span in "2011-01-01 2011-01-31" "2011-01-01 2011-06-30" "2011-01-01 2011-07-31" "2011-01-01 2012-12-31"; do
  set -- $span
  echo "--- requested $1 .. $2"
  get "$API/search.json?org=$D&from_issue_date=$1&to_issue_date=$2&size=1" \
    | jq -r '"    executed: " + (.info.query|capture("issueDate:\\[DT\\((?<a>[^)]*)\\) TO DT\\((?<b>[^)]*)\\)\\]")|.a[0:10]+" .. "+.b[0:10]) + "   total=" + (.info.total|tostring)'
done

hr "B. MAX PAGE SIZE"
for s in 100 500 1000; do
  printf 'size=%-5s -> actualSize=%s\n' "$s" \
    "$(get "$API/search.json?org=$D&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=$s" | jq -r '.info.actualSize')"
done

hr "C. INCREMENTAL: does submissionTimestamp filtering work?"
for p in "from_date=2026-09-01&to_date=2026-09-20" "from_submission_date=2026-09-01&to_submission_date=2026-09-20"; do
  echo "--- $p"; get "$API/search.json?org=$D&$p&size=1" | jq -r '"    "+.info.query+"  total="+(.info.total|tostring)'
done

hr "D. CAN WE SEE REVOKED / NON-PUBLISHED ACTS?"
for p in "status=all" "status=ΑΝΑΚΛΗΜΕΝΗ" "status=REVOKED"; do
  echo "--- $p"; get "$API/search.json?org=$D&from_issue_date=2024-01-01&to_issue_date=2024-06-30&$p&size=1" | jq -r '"    "+.info.query+"  total="+(.info.total|tostring)'
done

hr "E. PER-ENTITY, FULL FAMILY, 2024 H1 + 2024 H2"
for u in 6296 50256 52103 53404 53752 53952 54500 55049 100011442 100011650 100032995; do
  a=$(get "$API/search.json?org=$u&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=1"|jq -r '.info.total')
  b=$(get "$API/search.json?org=$u&from_issue_date=2024-07-01&to_issue_date=2024-12-31&size=1"|jq -r '.info.total')
  printf '%-10s H1=%-6s H2=%-6s\n' "$u" "$a" "$b"
done

hr "F. WHERE IS THE MONEY? sample one act of each spending type"
for t in "Β.1.3" "Β.2.1" "Β.2.2" "Δ.1" "Δ.2.2" "Β.1.1"; do
  echo "--- type $t"
  get "$API/search.json?org=$D&type=$(printf %s "$t"|jq -sRr @uri)&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=1" \
    > "$OUT/t_$t.json"
  jq -r '"    total=" + (.info.total|tostring)' "$OUT/t_$t.json"
  jq '.decisions[0] | {ada, decisionTypeId, subject: (.subject[0:90]), extraFieldValues}' "$OUT/t_$t.json"
done

hr "G. TYPE FIELD SCHEMAS (what fields each spending type declares)"
for t in "Β.2.1" "Β.2.2" "Δ.1"; do
  echo "--- $t"
  get "$API/types/$(printf %s "$t"|jq -sRr @uri)/details.json" \
    | jq -r '.. | objects | select(has("name")) | [.name, (.mandatory//"-"|tostring), (.type//"-")] | @tsv' 2>/dev/null \
    | sort -u | column -t -s$'\t' | head -30
done

hr "H. ORG UNITS + SIGNERS (department / official attribution)"
get "$API/organizations/$D/units.json" > "$OUT/units.json"
echo "units: $(jq '[..|objects|select(has("uid"))]|length' "$OUT/units.json")"
jq -r '..|objects|select(has("uid") and has("label"))|[.uid,.label]|@tsv' "$OUT/units.json" | head -15 | column -t -s$'\t'
get "$API/organizations/$D/signers.json" > "$OUT/signers.json"
echo "signers: $(jq '[..|objects|select(has("uid"))]|length' "$OUT/signers.json")"
jq -r '..|objects|select(has("uid") and (has("firstName") or has("label")))|[.uid,(.firstName//""),(.lastName//""),(.label//"")]|@tsv' "$OUT/signers.json" | head -10 | column -t -s$'\t'

hr "I. SCANNED-vs-TEXT ACROSS YEARS"
for y in 2011 2014 2018 2022 2025; do
  ada=$(get "$API/search.json?org=$D&from_issue_date=$y-03-01&to_issue_date=$y-03-31&size=1"|jq -r '.decisions[0].ada // empty')
  [ -z "$ada" ] && { echo "$y: no acts"; continue; }
  curl -sS -A "$UA" -L "https://diavgeia.gov.gr/doc/$ada" -o "$OUT/y$y.pdf" 2>/dev/null
  chars=$(pdftotext "$OUT/y$y.pdf" - 2>/dev/null | tr -d '[:space:]' | wc -c)
  pages=$(pdfinfo "$OUT/y$y.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
  printf '%s  %-14s pages=%-4s chars=%-7s %s\n' "$y" "$ada" "${pages:-?}" "$chars" \
    "$([ "${chars:-0}" -lt 200 ] && echo SCANNED || echo TEXT)"
  sleep 0.4
done

hr "J. VERSION LOG (retroactive edits)"
get "https://diavgeia.gov.gr/opendata/decisions/Ρ8ΗΒΩΗ6-ΟΙΗ/versionlog.json" | jq '.' | head -40

hr DONE
