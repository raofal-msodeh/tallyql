#!/usr/bin/env bash
# TallyQL demo — same result with jq vs tallyql.
set -u
cd "$(mktemp -d)"

# Build sample DNS log
cat > dns.jsonl << 'EOF'
{"machine":"m1","domain":"evil.com","ts":100}
{"machine":"m1","domain":"evil.com","ts":101}
{"machine":"m1","domain":"soevil.com","ts":102}
{"machine":"m2","domain":"bad.com","ts":103}
{"machine":"m3","domain":"soevil.com","ts":104}
EOF

echo "== jq group_by (requires pre-sort, single file, hardcoded keys) =="
jq -s 'group_by(.machine) | map({machine: .[0].machine, n: length}) | sort_by(.machine)[] | "\(.machine) \(.n)"' -r dns.jsonl

echo "== tallyql (streaming, any number of files) =="
tallyql group dns.jsonl .machine --agg count

echo "== tallyql count with filter =="
tallyql count dns.jsonl -f '.domain eq "evil.com"'

rm -rf "$(pwd)"
