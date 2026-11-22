"""Attach the Agent API client to the team's Financial Explorer v2 source."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("prototype", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
source = args.prototype.read_text(encoding="utf-8")
marker = "</body>"
if source.count(marker) != 1 or 'id="chat"' not in source or 'id="form"' not in source:
    parser.error("Expected the Financial Explorer v2 HTML prototype")
source = source.replace("financial-explorer-chats-v1", "financial-explorer-live-chats-v1")
source = source.replace("Hello. I can help you explore the selected Microsoft financial statements. Ask a question below, or start with a suggested question.", "Ask a question about the SEC filing collection.")
client = (Path(__file__).resolve().parents[1] / "ui" / "financial_explorer_client.js").read_text()
args.output.write_text(source.replace(marker, f"<script>\n{client}\n</script>\n{marker}"), encoding="utf-8")
