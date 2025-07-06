# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v2.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Methods.csv (defaulting missing players to Venmo),
# then produces peer-to-peer transactions using a “biggest loser pays biggest winner”
# strategy, caps each player’s outgoing payments at 4 by aggregating their smallest debts
# through the bank, and outputs a transactions CSV named {date}_transactionsV2.csv.
# """

# import argparse
# import os
# import sys
# from collections import defaultdict

# import pandas as pd

# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0

# def settle_transactions(csv_path, bank_name="BANK"):
#     # 1) Load ledger CSV
#     df = pd.read_csv(csv_path)

#     # 2) Locate Payment Methods.csv
#     project_root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
#     pm_path = None
#     for d in ("Payment Type", "Payment Types"):
#         candidate = os.path.join(project_root, d, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break
#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv")
#         sys.exit(1)

#     pm_df = pd.read_csv(pm_path)
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         entry = str(row["Player Name"]).strip()
#         keys = [entry]
#         if "(" in entry and ")" in entry:
#             keys += [
#                 entry.split("(",1)[0].strip(),
#                 entry.split("(",1)[1].split(")",1)[0].strip()
#             ]
#         for k in keys:
#             pm_map[k.lower()] = row

#     # Warn about missing players
#     missing = []
#     for full in df["Player Name"].dropna().unique():
#         base = full.split("(",1)[0].strip().lower()
#         if base not in pm_map:
#             missing.append(base)
#             pm_map[base] = None
#     if missing:
#         print("⚠ Warning: missing payment methods, defaulting to Venmo for:")
#         for name in missing:
#             print(f"  • {name}")

#     # 3) Classify debtors & creditors per the 4 core cases
#     bank_funds = 0.0
#     debtors    = []  # [ [name, amount_owed], ... ]
#     creditors  = []  # [ [name, amount_due], ... ]

#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])
#         received   = parse_currency(row["$ Received"])

#         if not credit_yes:
#             # Cases 1 & 2: non-ledgered
#             bank_funds += received
#             if end_stack > 0 and sent > 0:
#                 creditors.append([name, sent])
#         else:
#             # Cases 3 & 4: ledgered
#             if pl < 0 and abs(send_out) > 0:
#                 debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 creditors.append([name, sent])

#     # 4) Sort descending
#     debtors.sort(key=lambda x: x[1], reverse=True)
#     creditors.sort(key=lambda x: x[1], reverse=True)

#     # 5) Greedy match
#     transactions = []
#     i = j = 0
#     # Phase A: bank fronts non-ledgered winners first (already in creditors list)
#     # Phase B: bank fronts ledgered winners as long as funds remain
#     while i < len(creditors):
#         cname, camt = creditors[i]
#         pay = round(min(bank_funds, camt), 2)
#         if pay > 0:
#             transactions.append({"From": bank_name, "To": cname, "Amount": pay})
#             bank_funds -= pay
#             rem = round(camt - pay, 2)
#             creditors[i][1] = rem
#         i += 1

#     # Now creditors list holds any unpaid slices
#     # Greedy debtor → remaining creditor
#     i = j = 0
#     while i < len(debtors) and j < len(creditors):
#         dname, damt = debtors[i]
#         cname, camt = creditors[j]
#         if camt <= 1e-6:
#             j += 1
#             continue
#         x = round(min(damt, camt), 2)
#         transactions.append({"From": dname, "To": cname, "Amount": x})
#         debtors[i][1]   -= x
#         creditors[j][1] -= x
#         if abs(debtors[i][1]) < 1e-6:
#             i += 1
#         if abs(creditors[j][1]) < 1e-6:
#             j += 1

#     # Phase C: any leftover debtor balances → bank
#     for k in range(i, len(debtors)):
#         dname, damt = debtors[k]
#         if damt > 1e-6:
#             transactions.append({"From": dname, "To": bank_name, "Amount": round(damt, 2)})

#     # 6) Attach payment handle ("Method" column)
#     for tx in transactions:
#         to_key = str(tx["To"]).split("(",1)[0].strip().lower()
#         row    = pm_map.get(to_key)
#         platform, handle = "Venmo", ""
#         if row is not None:
#             for col in ("Venmo","Cashapp","Zelle","ApplePay"):
#                 val = row.get(col, "")
#                 if pd.notnull(val) and str(val).strip():
#                     platform, handle = col, str(val).strip()
#                     break
#         amt_str = f"${tx['Amount']:.2f}"
#         tx["Method"] = f"Pay user {amt_str} on {platform}: {handle}"

#     # 7) Cap each player at 4 outgoing transactions by aggregating smallest debts
#     MAX_TXNS = 4
#     bank = bank_name
#     bank_moves = [tx for tx in transactions if tx["From"] == bank]
#     user_moves = [tx for tx in transactions if tx["From"] != bank]

#     grouped = defaultdict(list)
#     for tx in user_moves:
#         grouped[tx["From"]].append(tx)

#     capped_txns = []
#     for debtor, outs in grouped.items():
#         if len(outs) <= MAX_TXNS:
#             capped_txns.extend(outs)
#         else:
#             # sort by amount ascending
#             outs_sorted = sorted(outs, key=lambda x: x["Amount"])
#             # keep largest (MAX_TXNS-1) direct payments
#             keep = outs_sorted[-(MAX_TXNS-1):]
#             bundle = outs_sorted[:len(outs_sorted)-(MAX_TXNS-1)]
#             # sum the small ones
#             s = round(sum(x["Amount"] for x in bundle), 2)
#             # rebuild bundle → bank transaction
#             # determine bank's platform & handle
#             bank_row = pm_map.get(bank.lower())
#             platform, handle = "Venmo", ""
#             if bank_row is not None:
#                 for col in ("Venmo","Cashapp","Zelle","ApplePay"):
#                     val = bank_row.get(col, "")
#                     if pd.notnull(val) and str(val).strip():
#                         platform, handle = col, str(val).strip()
#                         break
#             method = f"Pay user ${s:.2f} on {platform}: {handle}"
#             bundled_tx = {"From": debtor, "To": bank, "Amount": s, "Method": method}

#             capped_txns.extend(keep)
#             capped_txns.append(bundled_tx)

#     # reassemble final transaction list
#     transactions = capped_txns + bank_moves

#     # 8) Write out CSV
#     out_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactionsV2.csv")
#     pd.DataFrame(transactions).to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(transactions)} transactions to: {out_path}")

# def main():
#     parser = argparse.ArgumentParser(
#         description="Poker Ledger Payout System V2 (capped at 4 txns per player)"
#     )
#     parser.add_argument(
#         "--csv", required=True,
#         help="Path to ledger CSV (e.g. 'Ledger Data/6_30_25.csv')"
#     )
#     parser.add_argument(
#         "--bank-name", default="BANK",
#         help="Label for host/bank on settlements"
#     )
#     args = parser.parse_args()

#     settle_transactions(args.csv, bank_name=args.bank_name)

# if __name__ == "__main__":
#     main()







#!/usr/bin/env python3
"""
Backend/payoutSystem_v2.py

Reads a Poker Ledger CSV, validates every player against
Payment Methods.csv (defaulting missing players to Venmo),
then produces peer-to-peer transactions using a “biggest loser pays biggest winner”
strategy, caps each player’s outgoing payments at 4 by aggregating their smallest debts
through the bank, and outputs a transactions CSV named {date}_transactionsV2.csv.
"""

import argparse
import os
import sys
from collections import defaultdict

import pandas as pd


def parse_currency(val):
    if pd.isnull(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def settle_transactions(csv_path, bank_name="BANK"):
    # 1) Load ledger CSV
    df = pd.read_csv(csv_path)

    # 2) Locate Payment Methods.csv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
    pm_path = None
    for d in ("Payment Type", "Payment Types"):
        candidate = os.path.join(project_root, d, "Payment Methods.csv")
        if os.path.isfile(candidate):
            pm_path = candidate
            break
    if pm_path is None:
        print("✗ Error: cannot find Payment Methods.csv")
        sys.exit(1)

    pm_df = pd.read_csv(pm_path)
    pm_map = {}
    for _, row in pm_df.iterrows():
        entry = str(row["Player Name"]).strip()
        keys = [entry]
        if "(" in entry and ")" in entry:
            keys += [
                entry.split("(",1)[0].strip(),
                entry.split("(",1)[1].split(")",1)[0].strip()
            ]
        for k in keys:
            pm_map[k.lower()] = row

    # Warn about missing players
    missing = []
    for full in df["Player Name"].dropna().unique():
        base = full.split("(",1)[0].strip().lower()
        if base not in pm_map:
            missing.append(base)
            pm_map[base] = None
    if missing:
        print("⚠ Warning: missing payment methods, defaulting to Venmo for:")
        for name in missing:
            print(f"  • {name}")

    # 3) Classify debtors & creditors per the 4 core cases
    bank_funds = 0.0
    debtors    = []  # [ [name, amount_owed], ... ]
    creditors  = []  # [ [name, amount_due], ... ]

    for _, row in df.iterrows():
        name       = row["Player Name"]
        credit_yes = str(row["Credit?"]).strip().lower() == "yes"
        end_stack  = parse_currency(row["Ending Stack"])
        pl         = parse_currency(row["P/L Player"])
        send_out   = parse_currency(row["Send Out"])
        sent       = parse_currency(row["$ Sent"])
        received   = parse_currency(row["$ Received"])

        if not credit_yes:
            # Cases 1 & 2: non-ledgered
            bank_funds += received
            if end_stack > 0 and sent > 0:
                creditors.append([name, sent])
        else:
            # Cases 3 & 4: ledgered
            if pl < 0 and abs(send_out) > 0:
                debtors.append([name, abs(send_out)])
            elif pl > 0 and sent > 0:
                creditors.append([name, sent])

    # 4) Sort descending
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    # 5) Greedy match
    transactions = []
    i = j = 0
    # Phase A: bank fronts non-ledgered winners first (already in creditors list)
    # Phase B: bank fronts ledgered winners as long as funds remain
    while i < len(creditors):
        cname, camt = creditors[i]
        pay = round(min(bank_funds, camt), 2)
        if pay > 0:
            transactions.append({"From": bank_name, "To": cname, "Amount": pay})
            bank_funds -= pay
            rem = round(camt - pay, 2)
            creditors[i][1] = rem
        i += 1

    # Now creditors list holds any unpaid slices
    # Greedy debtor → remaining creditor
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        dname, damt = debtors[i]
        cname, camt = creditors[j]
        if camt <= 1e-6:
            j += 1
            continue
        x = round(min(damt, camt), 2)
        transactions.append({"From": dname, "To": cname, "Amount": x})
        debtors[i][1]   -= x
        creditors[j][1] -= x
        if abs(debtors[i][1]) < 1e-6:
            i += 1
        if abs(creditors[j][1]) < 1e-6:
            j += 1

    # Phase C: any leftover debtor balances → bank
    for k in range(i, len(debtors)):
        dname, damt = debtors[k]
        if damt > 1e-6:
            transactions.append({"From": dname, "To": bank_name, "Amount": round(damt, 2)})

    # 6) Attach payment handle ("Method" column) with all possible options
    for tx in transactions:
        to_key = str(tx["To"]).split("(",1)[0].strip().lower()
        row    = pm_map.get(to_key)
        options = []
        if row is not None:
            for col in ("Cashapp","Venmo","Zelle","ApplePay"):
                val = row.get(col, "")
                if pd.notnull(val) and str(val).strip():
                    options.append(f"({col}: {str(val).strip()})")
        else:
            # default to Venmo if missing
            options.append("(Venmo: )")
        if not options:
            options.append("(Venmo: )")
        options_str = ", ".join(options)
        amt_str = f"${tx['Amount']:.2f}"
        tx["Method"] = f"Pay user {amt_str} on {options_str}"

    # 7) Cap each player at 4 outgoing transactions by aggregating smallest debts
    MAX_TXNS = 4
    bank = bank_name
    bank_moves = [tx for tx in transactions if tx["From"] == bank]
    user_moves = [tx for tx in transactions if tx["From"] != bank]

    grouped = defaultdict(list)
    for tx in user_moves:
        grouped[tx["From"]].append(tx)

    capped_txns = []
    for debtor, outs in grouped.items():
        if len(outs) <= MAX_TXNS:
            capped_txns.extend(outs)
        else:
            # sort by amount ascending
            outs_sorted = sorted(outs, key=lambda x: x["Amount"])
            # keep largest (MAX_TXNS-1) direct payments
            keep = outs_sorted[-(MAX_TXNS-1):]
            bundle = outs_sorted[:len(outs_sorted)-(MAX_TXNS-1)]
            # sum the small ones
            s = round(sum(x["Amount"] for x in bundle), 2)
            # rebuild bundle → bank transaction
            bank_row = pm_map.get(bank.lower())
            options = []
            if bank_row is not None:
                for col in ("Cashapp","Venmo","Zelle","ApplePay"):
                    val = bank_row.get(col, "")
                    if pd.notnull(val) and str(val).strip():
                        options.append(f"({col}: {str(val).strip()})")
            else:
                options.append("(Venmo: )")
            if not options:
                options.append("(Venmo: )")
            options_str = ", ".join(options)
            method = f"Pay user ${s:.2f} on {options_str}"
            bundled_tx = {"From": debtor, "To": bank, "Amount": s, "Method": method}

            capped_txns.extend(keep)
            capped_txns.append(bundled_tx)

    # reassemble final transaction list
    transactions = capped_txns + bank_moves

    # 8) Write out CSV
    out_dir = os.path.join(project_root, "Transactions")
    os.makedirs(out_dir, exist_ok=True)
    base     = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(out_dir, f"{base}_transactionsV2.csv")
    pd.DataFrame(transactions).to_csv(out_path, index=False)

    print(f"[✓] Wrote {len(transactions)} transactions to: {out_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Poker Ledger Payout System V2 (capped at 4 txns per player)"
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to ledger CSV (e.g. 'Ledger Data/6_30_25.csv')"
    )
    parser.add_argument(
        "--bank-name", default="BANK",
        help="Label for host/bank on settlements"
    )
    args = parser.parse_args()

    settle_transactions(args.csv, bank_name=args.bank_name)

if __name__ == "__main__":
    main()
