#!/usr/bin/env bash
set -uo pipefail
API="https://diavgeia.gov.gr/opendata"
UA="tinos-transparency/0.1 (+https://github.com/alexacker-10/tinos-transparency)"
OUT="probe-out"; D="6296"; N="$OUT/2024.ndjson"; mkdir -p "$OUT"
get(){ curl -sS -A "$UA" -H 'Accept: application/json' "$1"; sleep 0.35; }
hr(){ echo; echo "===== $1 ====="; }

hr "A. THE ACTUAL BUDGET — Β.1.1 acts for Δήμος Τήνου itself"
jq -r 'select(.decisionTypeId=="Β.1.1")
  | [.ada, (.extraFieldValues.isBudgetApprovalForOrg|tostring), (.subject[0:95])]|@tsv' $N \
  | column -t -s$'\t'

hr "B. Β.3 ΙΣΟΛΟΓΙΣΜΟΣ/ΑΠΟΛΟΓΙΣΜΟΣ acts (61 in 2024)"
jq -r 'select(.decisionTypeId=="Β.3") | [.ada,(.subject[0:100])]|@tsv' $N | head -20 | column -t -s$'\t'

hr "C. PULL THE BUDGET PDF — find the grand total"
BADA=$(jq -r 'select(.decisionTypeId=="Β.1.1")
  | select(.subject|test("Δήμου Τήνου|ΔΗΜΟΥ ΤΗΝΟΥ"))
  | select(.subject|test("ροϋπολογισμ")) | .ada' $N | head -1)
echo "chosen ADA: ${BADA:-NONE}"
if [ -n "${BADA:-}" ]; then
  curl -sS -A "$UA" -L "https://diavgeia.gov.gr/doc/$BADA" -o "$OUT/budget.pdf"
  pdftotext -layout "$OUT/budget.pdf" "$OUT/budget.txt" 2>/dev/null
  echo "--- lines containing ΣΥΝΟΛΟ / ΓΕΝΙΚΟ:"
  grep -E "ΣΥΝΟΛ|ΓΕΝΙΚΟ|ΑΝΑΚΕΦΑΛΑΙΩΣΗ" "$OUT/budget.txt" | head -25
  echo "--- biggest numbers in the document:"
  grep -oE '[0-9]{1,3}(\.[0-9]{3})+,[0-9]{2}' "$OUT/budget.txt" \
    | tr -d '.' | tr ',' '.' | sort -rn | head -8
fi

hr "D. DOES giverAFM SEARCH WORK? (all payments to ΜΕΣΟΓΕΙΟΣ ΑΕ nationwide)"
for term in "giverAFM" "afm" "sponsorAFM"; do
  printf '%-12s ' "$term"
  get "$API/search.json?$term=099361052&from_issue_date=2024-01-01&to_issue_date=2024-06-30&size=1" \
    | jq -r '"total="+(.info.total|tostring)+"  q="+(.info.query[0:120])'
done

hr "E. FULL FIELD SCHEMA of every spending type (searchTerms = queryable surface)"
for t in "Β.1.3" "Β.2.1" "Β.2.2" "Δ.1" "Δ.2.2"; do
  echo "--- $t"
  get "$API/types/$(printf %s "$t"|jq -sRr @uri)/details.json" \
    | jq -r '[.extraFields[]? | {u:.uid,s:(.searchTerm//"-"),t:.type,r:.required}
              , (.extraFields[]?.nestedFields[]? | {u:("  ."+.uid),s:(.searchTerm//"-"),t:.type,r:.required})]
             | .[] | [.u,.s,.t,(.r|tostring)] | @tsv' 2>/dev/null \
    | column -t -s$'\t'
done

hr "F. KIMDIS — does the open data API answer?"
for u in "https://cerpp.eprocurement.gov.gr/kimds-opendata/api/searchContracts" \
         "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help" \
         "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/"; do
  printf '%-70s ' "${u: -60}"
  curl -sS -A "$UA" -o /dev/null -w 'http=%{http_code} type=%{content_type}\n' -L --max-time 20 "$u" || echo FAIL
done

hr "G. KIMDIS via data.gov.gr catalogue"
curl -sS -A "$UA" --max-time 25 \
  'https://data.gov.gr/api/3/action/package_search?q=%CE%9A%CE%97%CE%9C%CE%94%CE%97%CE%A3&rows=5' \
  | jq -r '.result.results[]? | [.name, .title] | @tsv' 2>/dev/null | column -t -s$'\t' \
  || echo "(CKAN search failed or needs token)"

hr "H. MUNICIPALITY SITE — is wp-json open?"
for p in "wp-json/" "wp-json/wp/v2/posts?per_page=1" "wp-json/wp/v2/types" "wp-json/wp/v2/media?per_page=1"; do
  printf '%-42s ' "$p"
  curl -sS -A "$UA" -o /dev/null -w 'http=%{http_code} type=%{content_type}\n' \
    --max-time 20 "https://dimostinou.gr/$p" || echo FAIL
done
echo "--- post types available:"
curl -sS -A "$UA" --max-time 20 'https://dimostinou.gr/wp-json/wp/v2/types' \
  | jq -r 'to_entries[]? | [.key, .value.name] | @tsv' 2>/dev/null | column -t -s$'\t' | head -20

hr "I. YOUTUBE presence"
curl -sS -A "$UA" --max-time 20 'https://dimostinou.gr/wp-json/wp/v2/search?search=youtube&per_page=5' \
  | jq -r '.[]? | [.id,.title]|@tsv' 2>/dev/null | column -t -s$'\t' || echo "(search endpoint n/a)"

hr DONE
