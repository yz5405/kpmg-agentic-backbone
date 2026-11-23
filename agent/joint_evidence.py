"""Validate reported revenue inputs and isolate quarter-only narrative support."""

import re
from datetime import date, datetime

_AMOUNT = re.compile(r"\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_PERIOD = re.compile(r"\b(three|six|nine|twelve) months ended ([A-Za-z]+ \d{1,2}, \d{4})", re.I)
_PERIOD_HEADING = re.compile(r"(?im)^(Three|Six|Nine|Twelve) Months Ended (.+?)(?: Compared with .+)?$")
_UNITS = re.compile(r"\((?:dollars )?in millions(?:, [^)]+)?\)", re.I)
_APPLE_CONTEXT = re.compile(
    r"disaggregated net sales[^\n]*?for the three- and nine-month periods ended "
    r"([A-Za-z]+ \d{1,2}, \d{4}) and ([A-Za-z]+ \d{1,2}, \d{4}) \(in millions\):\s*\n"
    r"(\| [A-Za-z]+ \d{1,2},)", re.I,
)


def _as_date(text):
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _fact_row(lines, label, scope):
    active = False
    for line in lines:
        row = _cells(line)
        if len(row) < 3:
            continue
        if not any(row[1:]):
            active = row[0].lower() == scope
        if row[0].lower() == label and (active or scope is None):
            return row
    return None


def _quarter_cells(row, current, prior, metadata, scope):
    if not row or not current or not prior or current != metadata.get("reporting_period_end"):
        return None
    current_date, prior_date = date.fromisoformat(current), date.fromisoformat(prior)
    if not 350 <= (current_date - prior_date).days <= 380:
        return None
    cells = row[1:3]
    if not all(_AMOUNT.fullmatch(cell) for cell in cells) or not cells[0].startswith("$"):
        return None
    return {"metric": "revenue", "scope": scope, "unit": "USD millions", "duration_months": 3,
            "period_end": current, "comparative_period_end": prior,
            "as_reported": cells[0], "comparative_as_reported": cells[1]}


def _revenue_fact(row, peers, scope="consolidated"):
    m, text = row["metadata"], row["text"]
    if (m.get("ticker") not in {"MSFT", "AAPL"} or m.get("form") != "10-Q"
            or m.get("fiscal_period") not in {"Q1", "Q2", "Q3"}
            or not m.get("fiscal_year") or not m.get("is_table")):
        return None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        header = _cells(line)
        if len(header) < 3:
            continue
        periods = [_PERIOD.fullmatch(cell) for cell in header[1:3]]
        if all(p and p[1].lower() == "three" for p in periods) and _UNITS.search("\n".join(lines[:index])):
            table = []
            for candidate in lines[index + 1:]:
                if not candidate.lstrip().startswith("|"):
                    break
                table.append(candidate)
            if scope == "intelligent_cloud":
                fact = _fact_row(table, "revenue", "intelligent cloud")
            else:
                fact = _fact_row(table, "total revenue", None) or _fact_row(table, "revenue", "total")
                if not fact and re.search(r"(?im)^SUMMARY RESULTS OF OPERATIONS\s*$", "\n".join(lines[:index])):
                    fact = _fact_row(table, "revenue", None)
            return _quarter_cells(fact, *[_as_date(p[2]) for p in periods], m, scope)
    # Apple's disaggregated revenue table is split from its SEC caption. Require
    # the matching section, rounded unit, exact two quarterly dates and table lead.
    if m["ticker"] == "AAPL" and scope == "consolidated" and m.get("section_id") and len(lines) > 2:
        fact = _fact_row(lines[2:], "total net sales", None)
        for peer in peers:
            pm = peer["metadata"]
            if pm.get("ticker") != "AAPL" or any(
                pm.get(k) != m.get(k) for k in ("accession_number", "section_id", "reporting_period_end")
            ):
                continue
            for match in _APPLE_CONTEXT.finditer(peer["text"]):
                current, prior, lead = match.groups()
                day, year = current.rsplit(" ", 1)
                if lines[0].strip() == lead and _cells(lines[1]) == ["", year, prior, current, prior]:
                    verified = _quarter_cells(fact, _as_date(current), _as_date(prior), m, scope)
                    if verified:
                        return {**verified, "caption_chunk_id": pm["chunk_id"]}
    return None


def financial_inputs(rows, question, period_ends):
    if not re.search(r"\brevenue\b", question, re.I):
        return []
    accepted = []
    for row in rows:
        fact = _revenue_fact(row, rows)
        if fact and (not period_ends or fact["period_end"] in period_ends):
            accepted.append({**row, "metadata": {**row["metadata"], "verified_financial_input": fact}})
    return accepted


def is_quarter_cloud_drivers(question):
    return all(re.search(pattern, question, re.I) for pattern in (
        r"\bintelligent cloud\b", r"\brevenue\b", r"\bquarter\b", r"\b(?:drove|drivers?|why)\b",
    ))


def quarter_cloud_evidence(rows, period_ends):
    """Return only quarter-scoped drivers and projected quarterly amounts."""
    if len(period_ends) != 1:
        return []
    primary, corroborating = [], []
    for row in rows:
        m, text = row["metadata"], row["text"]
        if m.get("ticker") != "MSFT" or m.get("form") != "10-Q" or m.get("reporting_period_end") != period_ends[0]:
            continue
        safe = {key: m[key] for key in (
            "ticker", "form", "accession_number", "chunk_id", "section_id", "section", "section_title",
            "source_url", "reporting_period_end", "fiscal_year", "fiscal_period",
        ) if key in m}
        if m.get("is_table"):
            fact = _revenue_fact(row, rows, "intelligent_cloud")
            if fact:
                corroborating.append({"metadata": {**safe, "answer_evidence_role": "quarter_amount"}, "text":
                    f"Intelligent Cloud revenue (USD millions, three months ended {fact['period_end']}): "
                    f"{fact['as_reported']}; comparative three months ended {fact['comparative_period_end']}: "
                    f"{fact['comparative_as_reported']}."})
            continue
        if "management" not in (m.get("section_title") or "").lower():
            continue
        segment = re.search(r"(?im)^Intelligent Cloud\s*\n\s*Revenue increased\b.*?(?=\n\s*Operating income|\Z)", text, re.S)
        if not segment or not re.search(r"\bdriven by\b", segment[0], re.I):
            continue
        parent = m.get("parent_text") or ""
        location = parent.find(segment[0])
        if location < 0 or parent.find(segment[0], location + 1) >= 0:
            continue
        headings = list(_PERIOD_HEADING.finditer(parent, 0, location))
        if headings and headings[-1][1].lower() == "three" and _as_date(headings[-1][2]) == period_ends[0]:
            primary.append({
                "metadata": {**safe, "answer_evidence_role": "quarter_driver"},
                "text": f"Three months ended {period_ends[0]}\n\n{segment[0].strip()}",
            })
    return primary + corroborating if primary else []
