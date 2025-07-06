# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v2.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Methods.csv (defaulting missing players to Venmo),
# then produces peer-to-peer transactions using a “biggest loser 
# pays biggest winner” strategy, and outputs a CSV named 
# {date}_transactionsV2.csv in Transactions/.
# """

# import argparse
# import os
# import sys
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

#     # 2) Locate Payment Methods.csv under “Payment Type(s)”
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)            # .../Poker Ledger Payout System/Backend
#     project_root = os.path.dirname(ledger_dir)         # .../Poker Ledger Payout System

#     pm_path = None
#     for dirname in ("Payment Type", "Payment Types"):
#         candidate = os.path.join(project_root, dirname, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break

#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv. Tried:")
#         print(f"    {os.path.join(project_root, 'Payment Type',  'Payment Methods.csv')}")
#         print(f"    {os.path.join(project_root, 'Payment Types', 'Payment Methods.csv')}")
#         sys.exit(1)

#     pm_df = pd.read_csv(pm_path)
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         entry = str(row["Player Name"]).strip()
#         keys = [entry]
#         if "(" in entry and ")" in entry:
#             keys.append(entry.split("(",1)[0].strip())
#             keys.append(entry.split("(",1)[1].split(")",1)[0].strip())
#         for k in keys:
#             pm_map[k.lower()] = row

#     # 3) Warn about missing players
#     missing = []
#     for full in df["Player Name"].dropna().unique():
#         base = full.split("(",1)[0].strip().lower()
#         if base not in pm_map:
#             missing.append(base)
#             pm_map[base] = None
#     if missing:
#         print("⚠ Warning: no payment methods for these players; defaulting to Venmo:")
#         for name in missing:
#             print(f"  • {name}")

#     # 4) Classify debtors & creditors
#     debtors   = []
#     creditors = []

#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         key        = str(name).split("(",1)[0].strip().lower()
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])

#         if not credit_yes:
#             # non-ledgered: if end_stack>0 they won → creditor
#             if end_stack > 0 and sent > 0:
#                 creditors.append([name, sent])
#         else:
#             # ledgered: losses → debtor; wins → creditor
#             if pl < 0 and abs(send_out) > 0:
#                 debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 creditors.append([name, sent])

#     # 5) Sort descending
#     debtors.sort(key=lambda x: x[1], reverse=True)
#     creditors.sort(key=lambda x: x[1], reverse=True)

#     # 6) Greedy match
#     transactions = []
#     i = j = 0
#     while i < len(debtors) and j < len(creditors):
#         dn, da = debtors[i]
#         cn, ca = creditors[j]
#         x = round(min(da, ca), 2)

#         transactions.append({"From": dn, "To": cn, "Amount": x})
#         debtors[i][1]   -= x
#         creditors[j][1] -= x

#         if abs(debtors[i][1])   < 1e-6: i += 1
#         if abs(creditors[j][1]) < 1e-6: j += 1

#     # 7) Leftovers → bank
#     for k in range(j, len(creditors)):
#         name, amt = creditors[k]
#         if amt > 1e-6:
#             transactions.append({"From": bank_name, "To": name, "Amount": round(amt,2)})

#     for k in range(i, len(debtors)):
#         name, amt = debtors[k]
#         if amt > 1e-6:
#             transactions.append({"From": name, "To": bank_name, "Amount": round(amt,2)})

#     # 8) Build Method column
#     for tx in transactions:
#         to_base = str(tx["To"]).split("(",1)[0].strip().lower()
#         row     = pm_map.get(to_base)
#         plat    = "Venmo"
#         handle  = ""
#         if row is not None:
#             for col in ("Venmo","Cashapp","Zelle","ApplePay"):
#                 val = row.get(col,"")
#                 if pd.notnull(val) and str(val).strip():
#                     plat   = col
#                     handle = str(val).strip()
#                     break

#         amt_str = f"${tx['Amount']:.2f}"
#         tx["Method"] = f"Pay user {amt_str} on {plat}: {handle}"

#     # 9) Write CSV to Transactions/{base}_transactionsV2.csv
#     out_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactionsV2.csv")
#     print(f"[DEBUG] Writing output to: {out_path}")
#     pd.DataFrame(transactions).to_csv(out_path, index=False)
#     print(f"[✓] Wrote {len(transactions)} transactions to: {out_path}")

# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System V2"
#     )
#     p.add_argument(
#         "--csv", required=True,
#         help="Path to ledger CSV (e.g. 'Ledger Data/6_30_25.csv')"
#     )
#     p.add_argument(
#         "--bank-name", default="BANK",
#         help="Label for host/bank in leftover settlements"
#     )
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name
#     )

# if __name__ == "__main__":
#     main()









# NEW VERSION THAT WILL HAVE BANK PAY OUT THE BIGGEST WINNER WHO PAID BANK FIRST






# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v2.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Methods.csv (defaulting missing players to Venmo),
# then produces peer-to-peer transactions using a “bank pays winners first,
# then biggest loser covers any remaining” strategy, and outputs
# {date}_transactionsV2.csv in Transactions/.
# """

# import argparse
# import os
# import sys
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

#     # 2) Locate Payment Methods.csv under “Payment Type(s)”
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)

#     pm_path = None
#     for dirname in ("Payment Type", "Payment Types"):
#         candidate = os.path.join(project_root, dirname, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break

#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv. Tried:")
#         print(f"    {os.path.join(project_root, 'Payment Type',  'Payment Methods.csv')}")
#         print(f"    {os.path.join(project_root, 'Payment Types', 'Payment Methods.csv')}")
#         sys.exit(1)

#     pm_df = pd.read_csv(pm_path)
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         entry = str(row["Player Name"]).strip()
#         keys = [entry]
#         if "(" in entry and ")" in entry:
#             keys.append(entry.split("(",1)[0].strip())
#             keys.append(entry.split("(",1)[1].split(")",1)[0].strip())
#         for k in keys:
#             pm_map[k.lower()] = row

#     # 3) Warn about missing players
#     missing = []
#     for full in df["Player Name"].dropna().unique():
#         base = full.split("(",1)[0].strip().lower()
#         if base not in pm_map:
#             missing.append(base)
#             pm_map[base] = None
#     if missing:
#         print("⚠ Warning: no payment methods for these players; defaulting to Venmo:")
#         for name in missing:
#             print(f"  • {name}")

#     # 4) Compute bank funds (all non-ledgered losers)
#     bank_funds = 0.0
#     for _, row in df.iterrows():
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         if not credit_yes and end_stack == 0:
#             bank_funds += parse_currency(row["$ Received"])

#     # 5) Build full list of creditors & debtors
#     creditors = []  # [ [name, amount_due], ... ]
#     debtors   = []  # [ [name, amount_owed], ... ]

#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])

#         if not credit_yes:
#             # non-ledgered winner → must be paid profit
#             if end_stack > 0 and sent > 0:
#                 creditors.append([name, sent])
#         else:
#             # ledgered
#             if pl > 0 and sent > 0:
#                 creditors.append([name, sent])
#             elif pl < 0 and abs(send_out) > 0:
#                 debtors.append([name, abs(send_out)])

#     # 6) Sort descending
#     creditors.sort(key=lambda x: x[1], reverse=True)
#     debtors.sort(key=lambda x: x[1], reverse=True)

#     transactions = []

#     # 7) Phase A: bank pays down as many creditors as possible
#     remaining_creditors = []
#     for name, amt in creditors:
#         if bank_funds > 0:
#             pay = round(min(bank_funds, amt), 2)
#             transactions.append({"From": bank_name, "To": name, "Amount": pay})
#             bank_funds -= pay
#             residual = round(amt - pay, 2)
#             if residual > 1e-6:
#                 remaining_creditors.append([name, residual])
#         else:
#             remaining_creditors.append([name, amt])
#     creditors = remaining_creditors

#     # 8) Phase B: biggest-loser pays biggest-winner for any leftovers
#     i = j = 0
#     while i < len(debtors) and j < len(creditors):
#         dn, da = debtors[i]
#         cn, ca = creditors[j]
#         x = round(min(da, ca), 2)

#         transactions.append({"From": dn, "To": cn, "Amount": x})
#         debtors[i][1]   -= x
#         creditors[j][1] -= x

#         if abs(debtors[i][1])   < 1e-6:
#             i += 1
#         if abs(creditors[j][1]) < 1e-6:
#             j += 1

#     # 9) Phase C: any leftover debtor-owed goes back to bank
#     for k in range(i, len(debtors)):
#         name, amt = debtors[k]
#         if amt > 1e-6:
#             transactions.append({"From": name, "To": bank_name, "Amount": round(amt, 2)})

#     # 10) Build Method column
#     for tx in transactions:
#         to_base = str(tx["To"]).split("(",1)[0].strip().lower()
#         row     = pm_map.get(to_base)
#         plat    = "Venmo"
#         handle  = ""
#         if row is not None:
#             for col in ("Venmo","Cashapp","Zelle","ApplePay"):
#                 val = row.get(col, "")
#                 if pd.notnull(val) and str(val).strip():
#                     plat   = col
#                     handle = str(val).strip()
#                     break

#         amt_str = f"${tx['Amount']:.2f}"
#         tx["Method"] = f"Pay user {amt_str} on {plat}: {handle}"

#     # 11) Write CSV to Transactions/{base}_transactionsV2.csv
#     out_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactionsV2.csv")
#     pd.DataFrame(transactions).to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(transactions)} transactions to: {out_path}")

# def main():
#     p = argparse.ArgumentParser(description="Poker Ledger Payout System V2")
#     p.add_argument(
#         "--csv", required=True,
#         help="Path to ledger CSV (e.g. 'Ledger Data/6_30_25.csv')"
#     )
#     p.add_argument(
#         "--bank-name", default="BANK",
#         help="Label for host/bank in leftover settlements"
#     )
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name
#     )

# if __name__ == "__main__":
#     main()


















#!/usr/bin/env python3
"""
Backend/payoutSystem_v2.py

Reads a Poker Ledger CSV and Payment Methods.csv,
then pays out in three phases:

  1) Bank pays all non-ledgered winners (their "$ Sent" amount) until funds run out,
     then pays remaining ledgered winners in descending order.
     Any unpaid slice becomes a “remaining creditor.”

  2) Ledgered losers pay off all remaining creditors (largest owed first).

  3) Any leftover loser balances get sent back to the bank.

Outputs Transactions/{date}_transactionsV2.csv with “Pay user $X on PLATFORM: @handle.”
"""

import argparse
import os
import sys
import pandas as pd

def parse_currency(val):
    if pd.isnull(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('$','').replace(',','').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def settle_transactions(csv_path, bank_name="BANK"):
    # ── 1) Load ledger CSV
    df = pd.read_csv(csv_path)

    # ── 2) Locate Payment Methods.csv under Payment Type(s)/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
    pm_path = None
    for d in ("Payment Type","Payment Types"):
        cand = os.path.join(project_root, d, "Payment Methods.csv")
        if os.path.isfile(cand):
            pm_path = cand
            break
    if pm_path is None:
        print("✗ Error: cannot find Payment Methods.csv under Payment Type(s)/")
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

    # Warn about missing payment methods
    missing = []
    for full in df["Player Name"].dropna().unique():
        base = full.split("(",1)[0].strip().lower()
        if base not in pm_map:
            missing.append(base)
            pm_map[base] = None
    if missing:
        print("⚠ Warning: missing methods, defaulting to Venmo for:")
        for m in missing:
            print(f"  • {m}")

    # ── 3) Compute bank_funds: sum of all "$ Received" for non-ledgered players
    non_ledgered = df.loc[df["Credit?"].str.strip().str.lower() == "no", "$ Received"]
    bank_funds = non_ledgered.apply(parse_currency).sum()

    # ── 4) Build pools per the 4 core cases
    non_led_winners = []   # Case 2: non-ledgered & end_stack>0
    ledgered_winners = []  # Case 4: ledgered & P/L Player >0
    debtors = []           # Case 3: ledgered & P/L Player <0

    for _, row in df.iterrows():
        name       = row["Player Name"]
        credit_yes = str(row["Credit?"]).strip().lower() == "yes"
        end_stack  = parse_currency(row["Ending Stack"])
        pl         = parse_currency(row["P/L Player"])
        send_out   = parse_currency(row["Send Out"])
        sent_amt   = parse_currency(row["$ Sent"])

        if not credit_yes:
            # non-ledgered
            if end_stack > 0 and sent_amt > 0:
                non_led_winners.append([name, sent_amt])
        else:
            # ledgered
            if pl > 0 and sent_amt > 0:
                ledgered_winners.append([name, sent_amt])
            elif pl < 0 and abs(send_out) > 0:
                debtors.append([name, abs(send_out)])

    # sort descending by amount
    non_led_winners.sort(key=lambda x: x[1], reverse=True)
    ledgered_winners.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    transactions = []

    # ── 5) Phase A: bank pays non-ledgered winners, then ledgered winners
    remaining_creditors = []

    # 5a) non-ledgered winners
    for name, amt in non_led_winners:
        pay = round(min(bank_funds, amt), 2)
        transactions.append({"From": bank_name, "To": name, "Amount": pay})
        bank_funds -= pay
        rem = round(amt - pay, 2)
        if rem > 1e-6:
            remaining_creditors.append([name, rem])

    # 5b) ledgered winners if funds remain
    for name, amt in ledgered_winners:
        if bank_funds <= 0:
            remaining_creditors.append([name, amt])
        else:
            pay = round(min(bank_funds, amt), 2)
            transactions.append({"From": bank_name, "To": name, "Amount": pay})
            bank_funds -= pay
            rem = round(amt - pay, 2)
            if rem > 1e-6:
                remaining_creditors.append([name, rem])

    # merge and sort remaining creditors
    remaining_creditors.sort(key=lambda x: x[1], reverse=True)

    # ── 6) Phase B: ledgered losers pay remaining creditors
    i = j = 0
    while i < len(debtors) and j < len(remaining_creditors):
        dn, da = debtors[i]
        cn, ca = remaining_creditors[j]
        x = round(min(da, ca), 2)
        transactions.append({"From": dn, "To": cn, "Amount": x})
        debtors[i][1]           -= x
        remaining_creditors[j][1] -= x
        if abs(debtors[i][1]) < 1e-6:
            i += 1
        if abs(remaining_creditors[j][1]) < 1e-6:
            j += 1

    # ── 7) Phase C: any leftover debtor balances go back to bank
    for k in range(i, len(debtors)):
        name, amt = debtors[k]
        if amt > 1e-6:
            transactions.append({"From": name, "To": bank_name, "Amount": round(amt, 2)})

    # ── 8) Attach Method (platform + handle)
    for tx in transactions:
        to_base = str(tx["To"]).split("(",1)[0].strip().lower()
        row     = pm_map.get(to_base)
        plat, handle = "Venmo", ""
        if row is not None:
            for col in ("Venmo","Cashapp","Zelle","ApplePay"):
                val = row.get(col, "")
                if pd.notnull(val) and str(val).strip():
                    plat   = col
                    handle = str(val).strip()
                    break
        amt_str = f"${tx['Amount']:.2f}"
        tx["Method"] = f"Pay user {amt_str} on {plat}: {handle}"

    # ── 9) Write out CSV
    out_dir  = os.path.join(project_root, "Transactions")
    os.makedirs(out_dir, exist_ok=True)
    base     = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(out_dir, f"{base}_transactionsV2.csv")
    pd.DataFrame(transactions).to_csv(out_path, index=False)

    print(f"[✓] Wrote {len(transactions)} transactions to: {out_path}")

def main():
    p = argparse.ArgumentParser(description="Poker Ledger Payout System V2")
    p.add_argument("--csv",      required=True, help="Path to ledger CSV")
    p.add_argument("--bank-name", default="BANK", help="Label for host/bank")
    args = p.parse_args()
    settle_transactions(args.csv, bank_name=args.bank_name)

if __name__ == "__main__":
    main()
