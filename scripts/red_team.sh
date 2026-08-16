#!/usr/bin/env bash
# red_team.sh — hostile-input validation for TallyQL.
# Design: rc 0=ok, 1=usage(broken), 2=config, 3=input|pipeline, 4=internal; expect 0/2/3, never 1/4.
set -u
PY="python3 -m tallyql"
TMP=$(mktemp -d)
PASS=0; FAIL=0

check() {
    local label="$1"; local want_rc="$2"; shift 2
    out=$($PY "$@" </dev/null 2>&1)
    rc=$?
    case ",$want_rc," in
        *",$rc,"*) echo "PASS [$label] rc=$rc"; PASS=$((PASS+1));;
        *) echo "FAIL [$label] want_rc=($want_rc) got=$rc"; echo "  output: $(echo "$out" | head -c 200)"; FAIL=$((FAIL+1));;
    esac
}

# Good baseline
printf '{"a":1,"b":"x"}\n{"a":2,"b":"y"}\n{"a":1,"b":"x"}\n' > "$TMP/good.jsonl"
check "group baseline" 0 group "$TMP/good.jsonl" .b --agg count
check "count baseline" 0 count "$TMP/good.jsonl"
check "count with filter" 0 count "$TMP/good.jsonl" -f '.b eq "x"'
check "group topk" 0 group "$TMP/good.jsonl" .b --agg "topk(.a,2) as t"
check "multi-file + stdin" 0 count "$TMP/good.jsonl" -

# 1. Path traversal
check "path traversal" 3 count "$TMP/../etc/hosts"
# 2. Directory input
check "directory input" 3 count "$TMP"
# 3. Missing file
check "missing file" 3 count "$TMP/nope.jsonl"
# 4. Symlink to dir
ln -s /tmp "$TMP/symdir"
check "symlink-to-dir" 3 count "$TMP/symdir"
# 5. Symlink traversal to outside
ln -s /etc/hostname "$TMP/symout"
check "symlink-traversal" 3 count "$TMP/symout"
# 6. Binary input — all lines malformed → pipeline error (rc 3), never crash (rc 1)
printf '\x00\x01\x02\xff\xfe' > "$TMP/bin.jsonl"
check "binary input" 3 count "$TMP/bin.jsonl" --max-bad 100
# 7. Very long corrupt line → rc 3 (malformed exceeds limit / no usable rows)
python3 -c "print('x'*100000)" > "$TMP/long.jsonl"
check "long corrupt line" 3 count "$TMP/long.jsonl" --max-bad 1000
# 8. Zero --max-bad with a bad line → rc 3 (pipeline error)
printf 'NOT_JSON\n' > "$TMP/bad1.jsonl"
check "bad line exceeds limit" 3 count "$TMP/bad1.jsonl" --max-bad 0
# 9. Empty file
: > "$TMP/empty.jsonl"
check "empty input" 3 count "$TMP/empty.jsonl"
# 10. Bad filter syntax
check "bad filter" 2 count "$TMP/good.jsonl" -f '.b eq'
# 11. Bad agg syntax
check "bad agg" 2 group "$TMP/good.jsonl" .b --agg "no_such_func(.b)"
# 12. Absolute output path → rejected as input/path error (rc 3)
check "abs output" 3 count "$TMP/good.jsonl" -o /tmp/out.json
# 13. Missing group path after dot
check "dot without path" 2 group "$TMP/good.jsonl" . --agg count
# 14. count with agg (forbidden)
check "count+agg forbidden" 2 count "$TMP/good.jsonl" --agg count
# 15. No command
check "no args" 2
# 16. Bad command
check "bad command" 2 foo "$TMP/good.jsonl"
# 17. Broken symlink
ln -s "$TMP/vanished" "$TMP/symdead"
check "broken symlink" 3 count "$TMP/symdead"

rm -rf "$TMP"
echo "--- red_team: $PASS passed, $FAIL failed"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
