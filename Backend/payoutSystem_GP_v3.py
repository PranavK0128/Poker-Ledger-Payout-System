"""
Backend/payoutSystem_v6.py
──────────────────────────
• Skips rows whose Done? == "Yes".
• Combines duplicate players into one net balance.
• Greedy settlement with --soft / --hard caps (defaults 3 / 4).
• BANK pays residuals; 3-cycle cancellation after settlement.
• NEW alias logic:
    Payment Methods 'Player Name' can be "(alias1), (Alias2)" etc.
    ─ first token before '(' and every individual (…) are aliases.
    Ledger 'Player Name':
    ─ first token + every (…) alias.
    Case-insensitive, leading '.' or '@' ignored.
"""

from __future__ import annotations
import argparse, csv, sys, re
from pathlib import Path
from collections import defaultdict, deque
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple
import pandas as pd

getcontext().prec = 28
CENT = Decimal("0.01")

# ───────────────────────── alias helpers ────────────────────────────────────
PAR_RE = re.compile(r"\(([^)]+)\)")       # grab text inside every ( … )
TOK_RE = re.compile(r"^\s*([^\s(]+)")     # first token in ledger string

def clean(token: str) -> str:
    """lower-case and strip leading '.' or '@'."""
    return token.lstrip(".@").strip().lower()

def aliases_from_pm(raw: str) -> List[str]:
    """
    Payment Methods ‘Player Name’ field, e.g.
        "(frankie2119), (Frankie)"
        "(.joonga) (joonga)"
    """
    raw = str(raw).strip()
    aliases: List[str] = []

    # part before first '(' if any
    head = raw.split("(", 1)[0].strip(" ,")
    if head:
        alias = clean(head)
        if alias:
            aliases.append(alias)

    # every (…) group
    for grp in PAR_RE.findall(raw):
        alias = clean(grp)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases

def aliases_from_ledger(raw: str) -> List[str]:
    """
    Ledger ‘Player Name’ field, e.g. "CSizzle (siz)"
    returns ["csizzle", "siz"]
    """
    raw = str(raw).strip()
    aliases: List[str] = []

    # first token
    m = TOK_RE.match(raw)
    if m:
        alias = clean(m.group(1))
        if alias:
            aliases.append(alias)

    # aliases inside (...)
    for grp in PAR_RE.findall(raw):
        alias = clean(grp)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases

def parse_money(x) -> Decimal:
    if pd.isna(x):
        return Decimal("0")
    return Decimal(str(x).replace("$", "").replace(",", "").strip())

def money_str(x: Decimal) -> str:
    return f"{x.quantize(CENT)}"

# ───────────────── payment-method DB ────────────────────────────────────────
def load_payment_db(csv_path: Path) -> Dict[str, List[str]]:
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    db: Dict[str, List[str]] = {}

    for _, row in df.iterrows():
        raw_name = str(row["Player Name"]).strip()

        # gather handles
        handles: List[str] = []
        for col, val in row.items():
            if col == "Player Name":
                continue
            val = str(val).strip()
            if not val or val.lower() == "nan":
                continue
            lbl = col.strip()
            if lbl.lower() == "venmo"   and not val.startswith("@"): val = "@" + val
            if lbl.lower() == "cashapp" and not val.startswith("$"): val = "$" + val
            handles.append(f"{lbl}: {val}")

        for alias in aliases_from_pm(raw_name):
            db.setdefault(alias, [])
            for h in handles:
                if h not in db[alias]:
                    db[alias].append(h)
    return db

def method_string(name_display: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
    if name_display == "BANK":
        return f"Internal bank transfer of ${money_str(amt)}"
    for alias in aliases_from_ledger(name_display):
        if alias in db:
            handles = db[alias]
            break
    else:
        handles = ["Venmo: "]
    return f"Pay user ${money_str(amt)} on " + ", ".join(f"({h})" for h in handles)

# ────────────────── classify & aggregate rows ───────────────────────────────
def classify(df: pd.DataFrame):
    net, disp = defaultdict(Decimal), {}
    bank = Decimal("0")

    for _, row in df.iterrows():
        if str(row.get("Done?", "")).strip().lower() == "yes":
            continue
        name = str(row["Player Name"]).strip()
        key = aliases_from_ledger(name)[0]   # canonical
        disp.setdefault(key, name)

        credit_flag = str(row["Credit?"]).strip().lower()
        received = parse_money(row.get("$ Received", 0))
        ending = parse_money(row.get("Ending Stack", 0))
        pl = parse_money(row.get("P/L Player", 0))
        send_out = parse_money(row.get("Send Out", 0))
        sent_col = parse_money(row.get("$ Sent", 0))

        if credit_flag != "yes":
            bank += received
            if ending > 0:
                net[key] += sent_col
        else:
            if pl < 0: net[key] -= abs(send_out)
            elif pl > 0: net[key] += sent_col

    cred, debt = [], []
    for k, bal in net.items():
        if bal > 0: cred.append((disp[k], bal))
        elif bal < 0: debt.append((disp[k], abs(bal)))
    return cred, debt, bank

# ───────────────── settlement + cycles (unchanged) ──────────────────────────
Transfer = Tuple[str, str, Decimal]

def settle(creditors, debtors, soft, hard):
    creditors = deque(sorted(creditors, key=lambda x: x[1], reverse=True))
    debtors = sorted(debtors, key=lambda x: (x[0]=="BANK", -x[1]))
    outcnt, txs = defaultdict(int), []

    for debtor, owe in debtors:
        while owe>0:
            if outcnt[debtor] >= hard:
                raise RuntimeError(f"{debtor} exceeded hard cap {hard}")
            if outcnt[debtor] >= soft or not creditors:
                txs.append((debtor,"BANK",owe)); outcnt[debtor]+=1; break
            cred,need = creditors[0]
            pay=min(owe,need)
            txs.append((debtor,cred,pay)); outcnt[debtor]+=1
            owe-=pay; need-=pay
            if need==0: creditors.popleft()
            else: creditors[0]=(cred,need)
    for cred,need in creditors:
        if need>0: txs.append(("BANK",cred,need))
    return txs

def cancel_cycles(txs):
    g=defaultdict(Decimal)
    for fr,to,amt in txs:
        if fr!=to and amt: g[(fr,to)]+=amt
    changed=True
    while changed:
        changed=False
        for (a,b),ab in list(g.items()):
            if a=="BANK" or b=="BANK": continue
            for (b2,c),bc in list(g.items()):
                if b2!=b or c=="BANK": continue
                if (c,a) in g:
                    ca=g[(c,a)]; x=min(ab,bc,ca)
                    for e in [(a,b),(b,c),(c,a)]:
                        g[e]-=x
                        if g[e]==0: del g[e]
                    changed=True; break
            if changed: break
    return [(fr,to,amt) for (fr,to),amt in g.items()]

# ───────────────────────────── driver ───────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Ledger CSV")
    ap.add_argument("--soft", type=int, default=3)
    ap.add_argument("--hard", type=int, default=4)
    args = ap.parse_args()

    ledger = Path(args.csv).expanduser()
    if not ledger.exists(): sys.exit("Ledger not found")

    root = Path(__file__).resolve().parents[1]
    pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
    df = pd.read_csv(ledger)

    creditors, debtors, bank = classify(df)
    if bank>0:  debtors.append(("BANK", bank))
    elif bank<0: creditors.append(("BANK", -bank))

    transfers = cancel_cycles(settle(creditors, debtors, args.soft, args.hard))

    merged=defaultdict(Decimal)
    for fr,to,amt in transfers: merged[(fr,to)]+=amt
    transfers = sorted([(fr,to,amt) for (fr,to),amt in merged.items()], key=lambda x:(x[0],x[1]))

    out = root / "Transactions" / f"{ledger.stem}_transactions_v3.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w=csv.writer(f); w.writerow(["From","To","Amount","Method"])
        for fr,to,amt in transfers: w.writerow([fr,to,money_str(amt),method_string(to, amt, pay_db)])

    print(f"✅  Wrote {out} ({len(transfers)} transfers; soft={args.soft}, hard={args.hard})")

if __name__ == "__main__":
    main()
