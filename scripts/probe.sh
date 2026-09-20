#!/usr/bin/env bash
# Diavgeia reconnaissance for the Tinos entity family.
set -uo pipefail

API="https://diavgeia.gov.gr/opendata"
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
ORGS="/tmp/orgs.json"
OUT="probe-out"
DIMOS="6296"
mkdir -p "$OUT"

get() { curl -sS -A "$UA" -H 'Accept: application/json' "$1"; sleep 0.4; }
hr()  { echo; echo "===== $1 ====="; }

[ -s "$ORGS" ] || curl -sS -A "$UA" "$API/organizations.json" -o "$ORGS"

# ---------------------------------------------------------------- entities
hr "1. DIMOS TINOU record"
jq '.organizations[] | select(.uid=="6296")' "$ORGS"

hr "2. DIRECT CHILDREN of 6296"
jq -r '.organizations[] | select(.supervisorId=="6296")
       | [.uid,.status,.vatNumber//"-",.category//"-",.label] | @tsv' "$ORGS" \
  | column -t -s$'\t'

hr "3. CHILDREN of each Tinos-named body (2nd level)"
for u in 52103 50256 53404 53752 53952 54500 100011650; do
  n=$(jq -r --arg u "$u" '.organizations[]|select(.supervisorId==$u)|.uid' "$ORGS" | wc -l)
  [ "$n" -gt 0 ] && { echo "--- parent $u:"; \
    jq -r --arg u "$u" '.organizations[]|select(.supervisorId==$u)
      |[.uid,.status,.vatNumber//"-",.label]|@tsv' "$ORGS" | column -t -s$'\t'; }
done
echo "(no output above = no grandchildren)"

hr "4. NAME SWEEP (bodies not labelled 'Tinos')"
jq -r '.organizations[] | select(.label|test("ΤΣΟΚΛΗ|ΧΑΛΕΠΑΣ|ΕΞΩΜΒΟΥΡΓΟΥ|ΠΑΝΟΡΜΟΥ|ΚΥΚΛΑΔΩΝ"))
       | [.uid,.status,.supervisorLabel//"-",.label] | @tsv' "$ORGS" \
  | column -t -s$'\t' | head -40

hr "5. INACTIVE / non-active statuses anywhere matching Tinos"
jq -r '.organizations[] | select(.label|test("ΤΗΝΟΥ|ΤΗΝΟΣ")) | select(.status!="active")
       | [.uid,.status,.label] | @tsv' "$ORGS" | column -t -s$'\t'
echo "(empty = all active)"

hr "6. DISTINCT status / category values in the whole file"
jq -r '[.organizations[].status]|unique|join(", ")' "$ORGS"
jq -r '[.organizations[].category]|unique|join(", ")' "$ORGS"

# ---------------------------------------------------------------- API shape
hr "7. DECISION TYPES (full list)"
get "$API/types.json" > "$OUT/types.json"
jq -r '.. | objects | select(has("uid") and has("label")) | [.uid,.label] | @tsv' \
   "$OUT/types.json" 2>/dev/null | sort -u | column -t -s$'\t' | head -60
echo "--- raw top-level keys:"; jq 'keys' "$OUT/types.json"

hr "8. DOES org= FILTER ACTUALLY APPLY?  (watch the echoed query)"
get "$API/search.json?org=$DIMOS&from_issue_date=2011-01-01&to_issue_date=2026-12-31&size=1" \
  > "$OUT/probe_org.json"
jq '.info' "$OUT/probe_org.json"

hr "9. TOTAL ACTS 2011-01-01..today, PER ENTITY"
for u in 6296 50256 52103 53404 53752 53952 54500 100011650; do
  lbl=$(jq -r --arg u "$u" '.organizations[]|select(.uid==$u)|.label' "$ORGS")
  t=$(get "$API/search.json?org=$u&from_issue_date=2011-01-01&to_issue_date=2026-12-31&size=1" \
       | jq -r '.info.total // "ERR"')
  printf '%-10s %-8s %s\n' "$u" "$t" "$lbl"
done

hr "10. DIMOS TINOU acts PER YEAR"
for y in $(seq 2010 2026); do
  t=$(get "$API/search.json?org=$DIMOS&from_issue_date=$y-01-01&to_issue_date=$y-12-31&size=1" \
       | jq -r '.info.total // "ERR"')
  printf '%s  %s\n' "$y" "$t"
done

hr "11. SAMPLE DECISION - full field shape"
get "$API/search.json?org=$DIMOS&from_issue_date=2025-01-01&to_issue_date=2025-12-31&size=3" \
  > "$OUT/sample.json"
jq '.decisions[0]' "$OUT/sample.json"
echo "--- all keys present across 3 samples:"
jq -r '[.decisions[]|keys]|flatten|unique|join(", ")' "$OUT/sample.json"
echo "--- extraFieldValues of sample 0:"
jq '.decisions[0].extraFieldValues // "NONE"' "$OUT/sample.json"

hr "12. FETCH ONE DOCUMENT + is it a scan?"
ADA=$(jq -r '.decisions[0].ada' "$OUT/sample.json")
echo "ADA: $ADA"
curl -sS -A "$UA" -L "https://diavgeia.gov.gr/doc/$ADA" -o "$OUT/sample.pdf" -w 'http=%{http_code} type=%{content_type} bytes=%{size_download}\n'
file "$OUT/sample.pdf"
pdftotext "$OUT/sample.pdf" - 2>/dev/null | wc -c | xargs echo "extractable text chars:"
pdftotext "$OUT/sample.pdf" - 2>/dev/null | head -25

hr "13. RATE-LIMIT / HEADERS sanity"
curl -sS -A "$UA" -o /dev/null -D - \
  "$API/search.json?org=$DIMOS&size=1" | head -20

hr "DONE"
