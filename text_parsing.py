import re
from typing import List, Dict
from datetime import datetime
import pprint

# 🔍 Normalize field names for fuzzy matching
def normalize_field_name(name: str) -> str:
    name = name.lower().replace(":", "").strip()
    mapping = {
        "maturity": "Maturity Date",
        "maturity date": "Maturity Date",
        "coupontype": "Coupon Type",
        "coupon type": "Coupon Type",
        "benchmark": "Benchmark Treasury",
        "benchmark treasury": "Benchmark Treasury",
        "issue date": "Issue Date",
        "expected ratings": "Expected Ratings"
    }
    return mapping.get(name, name.title())

FIELD_LABELS = [
    "Label", "Tenor", "Format", "Ranking", "Size", "Coupon Type", "Coupon",
    "SOFR Convention", "IPT", "Benchmark Treasury", "ISIN", "CUSIP",
    "Par Redemption Date", "Maturity", "Maturity Date", "Issue Date",
    "Next Interest Payment Date", "Optional Redemption by Holder",
    "Optional Redemption by Issuer", "Use of Proceeds", "Expected Ratings"
]

def extract_block(text: str, field_name: str) -> List[str]:
    field_name = normalize_field_name(field_name)
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if normalize_field_name(line.strip()) == field_name:
            start = i + 1
            break
    if start is None:
        return []

    block = []
    for line in lines[start:]:
        if normalize_field_name(line.strip()) in FIELD_LABELS:
            break
        if line.strip():
            block.append(line.strip())
    return block

def extract_field_list(text: str, field_name: str) -> List[str]:
    return extract_block(text, field_name)

def extract_multiline_field(text: str, field_name: str, tranche_count: int) -> List[List[Dict[str, str]]]:
    lines = extract_block(text, field_name)
    grouped = [[] for _ in range(tranche_count)]
    for i, line in enumerate(lines):
        label = None
        if "(Reg S)" in line:
            label = "Reg S"
        elif "(144A)" in line:
            label = "144A"
        value = re.sub(r"\s*\(.*?\)", "", line).strip()
        tranche_index = i % tranche_count
        grouped[tranche_index].append({label or "Unknown": value})
    return grouped

# 📆 Infer tenor from Issue Date and Maturity Date
def infer_tenor(issue_date: str, maturity_date: str) -> str:
    try:
        start = datetime.strptime(issue_date, "%Y-%m-%d")
        end = datetime.strptime(maturity_date, "%Y-%m-%d")
        years = (end - start).days // 365
        return f"{years}Y"
    except:
        return None

def extract_tabular_field(text: str, field_name: str, tranche_count: int) -> List[str]:
    field_name_norm = normalize_field_name(field_name)
    lines = text.splitlines()
    for line in lines:
        if not line.strip():
            continue
        # split on tabs or runs of 2+ spaces (covers pasted tables without real tabs)
        parts = re.split(r'\t+|\s{2,}', line.strip())
        if not parts:
            continue
        header_norm = normalize_field_name(parts[0])
        if header_norm == field_name_norm:
            values = []
            for p in parts[1:]:
                # clean common formatting like surrounding asterisks, parentheses, etc.
                v = re.sub(r'^\*+|\*+$', '', p).strip()
                v = re.sub(r'\s*\(.*?\)\s*$', '', v).strip()
                values.append(v if v != "" else None)
            return values[:tranche_count] + [None] * max(0, tranche_count - len(values))
    return [None] * tranche_count

# 🏦 Extract Expected Ratings block
def extract_expected_ratings(text: str, tranche_count: int) -> List[Dict[str, str]]:
    pattern = r"Expected Ratings\s+([\s\S]+?)(?:\n[A-Z][a-zA-Z /]+:|\n\n|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return [{} for _ in range(tranche_count)]
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    grouped = [{} for _ in range(tranche_count)]
    for i, line in enumerate(lines):
        if ":" in line:
            agency, rating = map(str.strip, line.split(":", 1))
            tranche_index = i % tranche_count
            grouped[tranche_index][agency] = rating
    return grouped

# 🛡️ Safe list access with padding
def safe_get(field_dict, key, index, default=None, pad_to=None):
    # normalize the lookup key so callers can pass raw labels like "ISIN" or normalized ones
    key = normalize_field_name(key)
    values = field_dict.get(key, [])
    if pad_to and len(values) < pad_to:
        values += [default] * (pad_to - len(values))
    return values[index] if index < len(values) else default

def decode_tenor(tenor: str):
    """
    Decode tenor strings like "11NC10" or "11 NC 10" -> (maturity_years, non_call_years).
    Returns (None, None) if no NC pattern is found.
    """
    if not tenor:
        return None, None
    tenor = str(tenor).strip()
    m = re.search(r'(\d+)\s*NC\s*(\d+)', tenor, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None

# 🧩 Main parser
def build_tranches(text: str) -> List[Dict[str, any]]:
    # try to detect tranche count from a tabular "Tenor" row first (handles both tabs and spaced columns)
    detected_count = None
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = re.split(r'\t+|\s{2,}', line.strip())
        if parts and normalize_field_name(parts[0]) == normalize_field_name("Tenor") and len(parts) > 1:
            detected_count = len(parts) - 1
            break

    if not detected_count:
        # fallback to counting Tenor lines in the block
        tenor_block = extract_field_list(text, "Tenor")
        if tenor_block:
            detected_count = len(tenor_block)
        else:
            detected_count = 1  # safe default to avoid extra empty tranches

    tranche_count = detected_count

    raw_fields = [
        "Label", "Tenor", "Format", "Ranking", "Size", "Coupon Type", "Coupon",
        "SOFR Convention", "IPT", "Benchmark Treasury", "ISIN", "CUSIP",
        "Par Redemption Date", "Maturity", "Next Interest Payment Date",
        "Optional Redemption by Holder", "Optional Redemption by Issuer",
        "Use of Proceeds", "Issue Date"
    ]

    tranche_fields = {}
    # normalize tabular field names so comparisons match the keys we store in tranche_fields
    tabular_fields = [normalize_field_name(f) for f in [
        "Tenor", "ISIN", "CUSIP", "Format", "Ranking", "Size", "Coupon Type",
        "Coupon", "SOFR Convention", "IPT", "Benchmark Treasury",
        "Par Redemption Date", "Maturity Date", "Next Interest Payment Date",
        "Optional Redemption by Holder", "Use of Proceeds"
    ]]

    for raw_field in raw_fields:
        norm_field = normalize_field_name(raw_field)
        if norm_field in tabular_fields:
            tranche_fields[norm_field] = extract_tabular_field(text, raw_field, tranche_count)
        else:
            tranche_fields[norm_field] = extract_field_list(text, raw_field)

    # for raw_field in raw_fields:
    #     norm_field = normalize_field_name(raw_field)
    #     mode = "multiline" if raw_field in ["ISIN", "CUSIP"] else "singleline"
    #     if mode == "multiline":
    #         tranche_fields[norm_field] = extract_multiline_field(text, raw_field, tranche_count)
    #     else:
    #         tranche_fields[norm_field] = extract_field_list(text, raw_field)

    expected_ratings = extract_expected_ratings(text, tranche_count)

    tranches = []
    for i in range(tranche_count):
        issue_date = safe_get(tranche_fields, "Issue Date", i, default=None, pad_to=tranche_count)
        maturity_date = safe_get(tranche_fields, "Maturity Date", i, default=None, pad_to=tranche_count)
        tenor = safe_get(tranche_fields, "Tenor", i, default=None, pad_to=tranche_count) or infer_tenor(issue_date, maturity_date)

        # decode NC-style tenor (e.g. "11NC10" -> maturity_years=11, non_call_years=10)
        maturity_years, non_call_years = decode_tenor(tenor) if isinstance(tenor, str) else (None, None)

        tranche = {
            "Tranche": f"Tranche {i+1}",
            "Tenor": tenor,
            "Tenor Maturity Years": maturity_years,
            "Tenor Non-Call Years": non_call_years,
            "Label": safe_get(tranche_fields, "Label", i, pad_to=tranche_count),
            "Expected Ratings": expected_ratings[i] if i < len(expected_ratings) else {},
            "Format": safe_get(tranche_fields, "Format", i, pad_to=tranche_count),
            "Ranking": safe_get(tranche_fields, "Ranking", i, pad_to=tranche_count),
            "Size": safe_get(tranche_fields, "Size", i, pad_to=tranche_count),
            "Coupon Type": safe_get(tranche_fields, "Coupon Type", i, pad_to=tranche_count),
            "Coupon": safe_get(tranche_fields, "Coupon", i, pad_to=tranche_count),
            "SOFR Convention": safe_get(tranche_fields, "SOFR Convention", i, pad_to=tranche_count),
            "IPT": safe_get(tranche_fields, "IPT", i, pad_to=tranche_count),
            "Benchmark Treasury": safe_get(tranche_fields, "Benchmark Treasury", i, pad_to=tranche_count),
            "ISIN": safe_get(tranche_fields, "ISIN", i, default=[], pad_to=tranche_count),
            "CUSIP": safe_get(tranche_fields, "CUSIP", i, default=[], pad_to=tranche_count),
            "Par Redemption Date": safe_get(tranche_fields, "Par Redemption Date", i, pad_to=tranche_count),
            "Maturity Date": maturity_date,
            "Next Interest Payment Date": safe_get(tranche_fields, "Next Interest Payment Date", i, pad_to=tranche_count),
            "Optional Redemption by Holder": safe_get(tranche_fields, "Optional Redemption by Holder", i, pad_to=tranche_count),
            "Optional Redemption by Issuer": safe_get(tranche_fields, "Optional Redemption by Issuer", i, pad_to=tranche_count),
            "Use of Proceeds": safe_get(tranche_fields, "Use of Proceeds", i, pad_to=tranche_count)
        }
        tranches.append(tranche)

    return tranches

sample_text = """
$$ New Deal: Republic of Xanadu (Republic) | $ 5Y & 10Y Senior Unsecured $$
			
Issuer/Ticker	Republic of Xanadu (“Republic”)
Issuer Ratings*	Moody's: Baa1 (Stable)
S&P: BBB (Stable)
Fitch: A- (Stable)
Tenor	5Y	10Y
Expected Issue Ratings*	Moody's (Exp): Baa1
S&P (Exp): BBB
Fitch (Exp): A-	Moody's (Exp): Baa1
S&P (Exp): BBB
Fitch (Exp): A-
Format	Reg S / 144A	Reg S / 144A
Ranking 	Senior Unsecured	Senior Unsecured
Size	USD Benchmark	USD Benchmark
Coupon Type	Fixed Rate	Fixed Rate
IPTs	T+[125bps] area	T+[160bps] area
Benchmark Treasury	T 3 7/8 07/31/28	T 4 1/4 08/15/33
ISIN 	**XD9013T5X8A1**	**XD9013T5X8B9**
CUSIP	**78912C853**	**78912C861**
Maturity Date	**August 4, 2030**	**August 4, 2035**
Settlement	**September 5, 2025** (T+5)
Bookrunner	Active: [Syndicate Bank 1], [Syndicate Bank 2]
Listing	Luxembourg Stock Exchange
Governing Law	New York
Use of Proceeds	Budgetary Financing
Risk Factors	See Preliminary Prospectus Supplement
Denominations	USD 200,000 x 1,000
Timing	Today's Business – Pricing in NY hours

"""

# Call the parser
tranches = build_tranches(sample_text)

# Print the output
import pprint
pprint.pprint(tranches)
