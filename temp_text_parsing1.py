import re
import json
from pprint import pprint

# Paste your entire message text into this variable (multiline string)
raw_text = """<YOUR FULL INPUT TEXT HERE>"""

# Helper function to extract clean lines with a key and values for all tranches
def extract_multi_field(raw_text, label):
    pattern = rf"{label}\s+(.*?)\n(.*?)\n(.*?)\n"
    match = re.search(pattern, raw_text)
    if match:
        return [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
    return [None, None, None]

def parse_global_fields(text):
    return {
        "Issuer": re.search(r"Issuer/Ticker\s+(.*?)\(", text).group(1).strip(),
        "Ticker": "HSBC",
        "Ratings": {
            "Moody's": re.search(r"Moody'?s:\s*(.*?)\n", text).group(1).strip(),
            "S&P": re.search(r"S&P:\s*(.*?)\n", text).group(1).strip(),
            "Fitch": re.search(r"Fitch:\s*(.*?)\n", text).group(1).strip()
        },
        "Settlement": re.search(r"Settlement\s+(.*?)\(", text).group(1).strip(),
        "Bookrunner": "HSBC (B&D)",
        "Listing": "Application will be made to list the Notes on the NYSE in accordance with its rules",
        "Governing Law": "New York",
        "Denominations": "USD 200,000 x 1,000",
        "Timing": "Today's Business – Pricing in NY hours",
        "Sale into Canada": "Yes – Exemption",
        "Risk Disclosure": "Investors should read the Risk Factors in the Preliminary Prospectus Supplements"
    }

def parse_tranches(text):
    tenors = ["4NC3", "6NC5", "11NC10"]
    labels = ["TLAC", "TLAC", "TIER 2"]
    
    expected_ratings = [
        {"Moody's": "A3", "S&P": "A-", "Fitch": "A+"},
        {"Moody's": "A3", "S&P": "A-", "Fitch": "A+"},
        {"Moody's": "Baa1", "S&P": "BBB", "Fitch": "A-"},
    ]
    
    tranche_fields = {
        "Format": extract_multi_field(text, "Format"),
        "Ranking": extract_multi_field(text, "Ranking"),
        "Size": extract_multi_field(text, "Size"),
        "Coupon Type": extract_multi_field(text, "Coupon Type"),
        "Coupon": extract_multi_field(text, "Coupon"),
        "SOFR Convention": extract_multi_field(text, "SOFR Convention"),
        "IPT": extract_multi_field(text, "IPTs"),
        "Benchmark Treasury": extract_multi_field(text, "Benchmark Treasury"),
        "ISIN": extract_multi_field(text, "ISIN"),
        "CUSIP": extract_multi_field(text, "CUSIP"),
        "Par Redemption Date": extract_multi_field(text, "Par Redemption Date"),
        "Maturity Date": extract_multi_field(text, "Maturity Date"),
        "Next Interest Payment Date": extract_multi_field(text, "Next Interest Payment Date"),
        "Optional Redemption by Holder": extract_multi_field(text, "Optional Redemption by Holder"),
        "Use of Proceeds": extract_multi_field(text, "Use of Proceeds"),
    }

    redemption_by_issuer = [
        [
            "Optional Redemption Dates (1 year par call prior to maturity)",
            "Certain tax events (any time)",
            "Loss Absorption Disqualification Event",
            "Make Whole Call 6 month from issue date to 1 year prior to maturity"
        ],
        [
            "Optional Redemption Dates (1 year par call prior to maturity)",
            "Certain tax events (any time)",
            "Loss Absorption Disqualification Event",
            "Make Whole Call 6 month from issue date to 1 year prior to maturity"
        ],
        [
            "Optional Redemption Dates (1 year par call prior to maturity)",
            "Certain tax events (any time)",
            "Capital Disqualification Event"
        ]
    ]

    tranches = []
    for i in range(3):
        tranche = {
            "Tenor": tenors[i],
            "Label": labels[i],
            "Expected Ratings": expected_ratings[i],
            "Format": tranche_fields["Format"][i],
            "Ranking": tranche_fields["Ranking"][i],
            "Size": tranche_fields["Size"][i],
            "Coupon Type": tranche_fields["Coupon Type"][i],
            "Coupon": tranche_fields["Coupon"][i],
            "SOFR Convention": tranche_fields["SOFR Convention"][i],
            "IPT": tranche_fields["IPT"][i],
            "Benchmark Treasury": tranche_fields["Benchmark Treasury"][i],
            "ISIN": tranche_fields["ISIN"][i],
            "CUSIP": tranche_fields["CUSIP"][i],
            "Par Redemption Date": tranche_fields["Par Redemption Date"][i],
            "Maturity Date": tranche_fields["Maturity Date"][i],
            "Next Interest Payment Date": tranche_fields["Next Interest Payment Date"][i],
            "Optional Redemption by Holder": tranche_fields["Optional Redemption by Holder"][i],
            "Optional Redemption by Issuer": redemption_by_issuer[i],
            "Use of Proceeds": tranche_fields["Use of Proceeds"][i]
        }
        tranches.append(tranche)
    
    return tranches

# Final Assembly
data = parse_global_fields(raw_text)
data["Tranches"] = parse_tranches(raw_text)

# Output the result
print(json.dumps(data, indent=2))

import re
import json

def extract_tenors(text):
    tenor_match = re.search(r"Tenor\s+(.+?)\n", text)
    return tenor_match.group(1).strip().split() if tenor_match else []

def extract_field_group(text, field_name, count):
    # Matches multiple rows after a label like "Format"
    pattern = rf"{field_name}\s+([^\n]+(?:\n[^\n]+){{0,{count-1}}})"
    match = re.search(pattern, text)
    if match:
        values = [line.strip() for line in match.group(1).splitlines()]
        while len(values) < count:
            values.append(None)
        return values[:count]
    return [None] * count

def build_tranches(text, tenors):
    count = len(tenors)
    
    tranche_fields = {
        "Label": ["TLAC"] * count,  # Optional: adjust with better logic if available
        "Expected Ratings": extract_field_group(text, "Expected Issue Ratings*", count),
        "Format": extract_field_group(text, "Format", count),
        "Ranking": extract_field_group(text, "Ranking", count),
        "Size": extract_field_group(text, "Size", count),
        "Coupon Type": extract_field_group(text, "Coupon Type", count),
        "Coupon": extract_field_group(text, "Coupon", count),
        "SOFR Convention": extract_field_group(text, "SOFR Convention", count),
        "IPT": extract_field_group(text, "IPTs", count),
        "Benchmark Treasury": extract_field_group(text, "Benchmark Treasury", count),
        "ISIN": extract_field_group(text, "ISIN", count),
        "CUSIP": extract_field_group(text, "CUSIP", count),
        "Par Redemption Date": extract_field_group(text, "Par Redemption Date", count),
        "Maturity Date": extract_field_group(text, "Maturity Date", count),
        "Next Interest Payment Date": extract_field_group(text, "Next Interest Payment Date", count),
        "Optional Redemption by Holder": extract_field_group(text, "Optional Redemption by Holder", count),
        "Use of Proceeds": extract_field_group(text, "Use of Proceeds", count)
    }

    # Optional Redemption by Issuer is often more complex; use static or advanced parsing here
    optional_redemptions = [
        ["Optional Redemption Dates (1 year par call prior to maturity)", "Certain tax events (any time)", "Loss Absorption Disqualification Event", "Make Whole Call 6 month from issue date to 1 year prior to maturity"]
        if "TLAC" in tranche_fields["Label"][i]
        else ["Optional Redemption Dates (1 year par call prior to maturity)", "Certain tax events (any time)", "Capital Disqualification Event"]
        for i in range(count)
    ]

    tranches = []
    for i in range(count):
        tranche = {
            "Tenor": tenors[i],
            "Label": tranche_fields["Label"][i],
            "Expected Ratings": {},  # Optional: add actual mapping if available
            "Format": tranche_fields["Format"][i],
            "Ranking": tranche_fields["Ranking"][i],
            "Size": tranche_fields["Size"][i],
            "Coupon Type": tranche_fields["Coupon Type"][i],
            "Coupon": tranche_fields["Coupon"][i],
            "SOFR Convention": tranche_fields["SOFR Convention"][i],
            "IPT": tranche_fields["IPT"][i],
            "Benchmark Treasury": tranche_fields["Benchmark Treasury"][i],
            "ISIN": tranche_fields["ISIN"][i],
            "CUSIP": tranche_fields["CUSIP"][i],
            "Par Redemption Date": tranche_fields["Par Redemption Date"][i],
            "Maturity Date": tranche_fields["Maturity Date"][i],
            "Next Interest Payment Date": tranche_fields["Next Interest Payment Date"][i],
            "Optional Redemption by Holder": tranche_fields["Optional Redemption by Holder"][i],
            "Optional Redemption by Issuer": optional_redemptions[i],
            "Use of Proceeds": tranche_fields["Use of Proceeds"][i]
        }
        tranches.append(tranche)

    return tranches