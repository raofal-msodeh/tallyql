import re
from pathlib import Path

FILES = ["CHANGELOG.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"]
BASE = Path("/home/ubuntu/tallyql")

for name in FILES:
    p = BASE / name
    if not p.exists():
        print("missing", name)
        continue
    text = p.read_text()
    text = text.replace("CommitGrep", "TallyQL").replace("commitgrep", "tallyql")
    # CommitGrep → TallyQL; commitgrep CLI references become tallyql CLI
    p.write_text(text)
    print("personalized", name)

# CHANGELOG: rewrite entries for TallyQL
cl = BASE / "CHANGELOG.md"
text = cl.read_text()
text = text.replace(
    "- Initial release of the `commitgrep` CLI for searching Git history.",
    "- Initial release of the `tallyql` CLI for stream-querying JSONL files.",
)
cl.write_text(text)
print("changelog rewritten")
