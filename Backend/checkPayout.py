#!/usr/bin/env python3
"""
check_payout.py   –   Stand-alone validator

• Load one or more raw ledger CSVs (the same format you feed
  to payoutSystem_v6.py).
• Ignore rows whose Done? == "Yes".
• Collapse duplicate names (part before '(') into a single net balance.
• Load the payout CSV that payoutSystem_v6.py produced.
• Make sure every player (and BANK) balances to $0.

Run:

    python -m Backend.check_payout \
           --ledgers "Ledger Data/T1.csv" "Ledger Data/T2.csv" \
           --payout  "Transactions/T1_transactions_v6.csv"
"""

import argparse, re, sys
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
import pandas as pd

NAME_RE = re.compile(r"^\s*([^()]+)")

def canon(n: str) -> str:
    m = NAME_RE.match(str(n))
    return m.group(1).strip().lower() if m else str(n).strip().lower()

def d(x) -> Decimal:
    return Decimal(str(x).replace("$","").replace(",","") or "0")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers", nargs="+", required=True, help="One or more raw ledger CSVs")
    ap.add_argument("--payout",  required=True, help="CSV produced by payoutSystem_v6")
    args = ap.parse_args()

    # --- build expected net balances ----------------------------------------
    net = defaultdict(Decimal)
    for fp in map(Path, args.ledgers):
        if not fp.exists(): sys.exit(f"ledger not found: {fp}")
        df = pd.read_csv(fp)
        for _, row in df.iterrows():
            if str(row.get("Done?", "")).strip().lower() == "yes":
                continue
            key = canon(row["Player Name"])
            if str(row.get("Credit?","")).strip().lower() != "yes":   # NOT ledgered
                net["BANK"] -= d(row["$ Received"])
                if d(row["Ending Stack"]) > 0:
                    net[key] += d(row["$ Sent"])
            else:                                                     # ledgered
                pl = d(row["P/L Player"])
                if pl > 0:
                    net[key] += d(row["$ Sent"])
                elif pl < 0:
                    net[key] -= d(row["Send Out"])

    # --- build actual net flows from payout CSV -----------------------------
    io = defaultdict(Decimal)
    pay = Path(args.payout)
    if not pay.exists(): sys.exit(f"payout file not found: {pay}")
    df = pd.read_csv(pay)
    for _, r in df.iterrows():
        io[canon(r["From"])] -= d(r["Amount"])
        io[canon(r["To"])]   += d(r["Amount"])

    # --- compare ------------------------------------------------------------
    bad = []
    for k in set(net) | set(io):
        diff = net[k] + io[k]
        if diff:          # non-zero
            bad.append((k, net[k], io[k], diff))

    if bad:
        print("⚠️  mismatches:\n")
        for name, exp, act, diff in sorted(bad):
            print(f"{name:<20}  expected {exp:+}   payout net {act:+}   → diff {diff:+}")
        sys.exit(1)
    print("✅  every player (and BANK) is fully settled.")

if __name__ == "__main__":
    main()
