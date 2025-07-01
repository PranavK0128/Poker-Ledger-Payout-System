# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, identifies who owes money and who is owed,
# then produces the minimal set of peer-to-peer transactions to settle
# everyone in as few transfers as possible.
# """

# import argparse
# import os
# import pandas as pd


# def parse_currency(val):
#     """
#     Turn strings like '-$1,234.56' or '$78.90' into floats.
#     NaN or unparsable → 0.0
#     """
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path):
#     # 1) Load ledger
#     df = pd.read_csv(csv_path)

#     debtors = []   # [(name, amount_owed), …]
#     creditors = [] # [(name, amount_due), …]

#     for _, row in df.iterrows():
#         name       = row['Player Name']
#         credit_yes = str(row['Credit?']).strip().lower() == 'yes'
#         end_stack  = parse_currency(row['Ending Stack'])
#         pl         = parse_currency(row['P/L Player'])
#         send_out   = parse_currency(row['Send Out'])
#         sent       = parse_currency(row['$ Sent'])

#         if not credit_yes:
#             # non-ledgered: if they end > 0, they profited → creditor
#             if end_stack > 0 and sent > 0:
#                 creditors.append([name, sent])
#         else:
#             # ledgered:
#             if pl < 0 and abs(send_out) > 0:
#                 # they lost on credit → debtor
#                 debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 # they won on credit → creditor (use $ Sent after tip)
#                 creditors.append([name, sent])

#     # 2) Sort biggest → smallest
#     debtors.sort(key=lambda x: x[1], reverse=True)
#     creditors.sort(key=lambda x: x[1], reverse=True)

#     # 3) Greedily match
#     transactions = []  # {'From':…, 'To':…, 'Amount':…}
#     i, j = 0, 0
#     while i < len(debtors) and j < len(creditors):
#         d_name, d_amt = debtors[i]
#         c_name, c_amt = creditors[j]
#         x = min(d_amt, c_amt)

#         transactions.append({
#             'From':   d_name,
#             'To':     c_name,
#             'Amount': round(x, 2)
#         })

#         debtors[i][1]   -= x
#         creditors[j][1] -= x

#         if abs(debtors[i][1]) < 1e-6:
#             i += 1
#         if abs(creditors[j][1]) < 1e-6:
#             j += 1

#     # 4) Dump to CSV in top-level Transactions/ folder
#     trans_df = pd.DataFrame(transactions)

#     abs_csv = os.path.abspath(csv_path)
#     ledger_dir = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)
#     out_dir = os.path.join(project_root, 'Transactions')
#     os.makedirs(out_dir, exist_ok=True)

#     base = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")

#     trans_df.to_csv(out_path, index=False)
#     print(f"[✓] Wrote {len(transactions)} transactions to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — settle all debts with minimal transfers"
#     )
#     p.add_argument(
#         '--csv',
#         required=True,
#         help="Path to your ledger CSV (e.g. \"Ledger Data/6_25_25.csv\")"
#     )
#     args = p.parse_args()
#     settle_transactions(args.csv)


# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
"""
Backend/payoutSystem.py

Reads a Poker Ledger CSV, identifies who owes money and who is owed,
then produces the minimal set of peer-to-peer transactions to settle
everyone in as few transfers as possible.  Any leftover credit
(i.e. winners who still haven’t gotten their full payout) is
shown as BANK → player.  Any leftover debt (unlikely) shows
player → BANK.
"""

import argparse
import os
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
    df = pd.read_csv(csv_path)

    debtors   = []  # [(name, amount_owed), …]
    creditors = []  # [(name, amount_due), …]

    # 1) build debtor & creditor lists
    for _, row in df.iterrows():
        name       = row['Player Name']
        credit_yes = str(row['Credit?']).strip().lower() == 'yes'
        end_stack  = parse_currency(row['Ending Stack'])
        pl         = parse_currency(row['P/L Player'])
        send_out   = parse_currency(row['Send Out'])
        sent       = parse_currency(row['$ Sent'])

        if not credit_yes:
            # non-ledgered: profit → we owe them (use post-tip $ Sent)
            if end_stack > 0 and sent > 0:
                creditors.append([name, sent])
        else:
            # ledgered:
            if pl < 0 and abs(send_out) > 0:
                # they lost → they owe us
                debtors.append([name, abs(send_out)])
            elif pl > 0 and sent > 0:
                # they won → we owe them (use post-tip $ Sent)
                creditors.append([name, sent])

    # 2) sort largest to smallest
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    # 3) match greedily
    transactions = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        d_name, d_amt = debtors[i]
        c_name, c_amt = creditors[j]
        x = min(d_amt, c_amt)

        transactions.append({
            'From':   d_name,
            'To':     c_name,
            'Amount': round(x, 2)
        })

        debtors[i][1]   -= x
        creditors[j][1] -= x

        if abs(debtors[i][1]) < 1e-6:
            i += 1
        if abs(creditors[j][1]) < 1e-6:
            j += 1

    # 4) any creditors left → BANK pays them
    while j < len(creditors):
        name, amt = creditors[j]
        if amt > 1e-6:
            transactions.append({
                'From':   bank_name,
                'To':     name,
                'Amount': round(amt, 2)
            })
        j += 1

    # 5) any debtors left → they pay BANK
    while i < len(debtors):
        name, amt = debtors[i]
        if amt > 1e-6:
            transactions.append({
                'From':   name,
                'To':     bank_name,
                'Amount': round(amt, 2)
            })
        i += 1

    # 6) write out CSV
    trans_df = pd.DataFrame(transactions)
    abs_csv    = os.path.abspath(csv_path)
    ledger_dir = os.path.dirname(abs_csv)
    project_root = os.path.dirname(ledger_dir)
    out_dir    = os.path.join(project_root, 'Transactions')
    os.makedirs(out_dir, exist_ok=True)

    base      = os.path.splitext(os.path.basename(csv_path))[0]
    out_path  = os.path.join(out_dir, f"{base}_transactions.csv")
    trans_df.to_csv(out_path, index=False)

    print(f"[✓] Wrote {len(transactions)} transactions to:\n    {out_path}")


def main():
    p = argparse.ArgumentParser(
        description="Poker Ledger Payout System — settle all debts with minimal transfers"
    )
    p.add_argument(
        '--csv', required=True,
        help="Path to your ledger CSV (e.g. \"Ledger Data/6_25_25.csv\")"
    )
    p.add_argument(
        '--bank-name', default="BANK",
        help="Name to use for the host/bank in any top-off transactions"
    )
    args = p.parse_args()
    settle_transactions(args.csv, bank_name=args.bank_name)


if __name__ == "__main__":
    main()
