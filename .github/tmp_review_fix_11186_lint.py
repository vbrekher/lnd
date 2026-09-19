from pathlib import Path

fee = Path("sweep/fee_bumper.go")
text = fee.read_text()
old = '''\t\t\t\tlog.Debugf(
\t\t\t\t\t"Detected mempool spend of input=%v "+
\t\t\t\t\t\t"in tx=%v", op, spendingTx.TxHash(),
\t\t\t\t)
'''
new = '''\t\t\t\tspendingTxID := spendingTx.TxHash()
\t\t\t\tlog.Debugf(
\t\t\t\t\t"Detected mempool spend of input=%v "+
\t\t\t\t\t\t"in tx=%v", op, spendingTxID,
\t\t\t\t)
'''
if text.count(old) != 1:
    raise SystemExit("expected mempool log block exactly once")
fee.write_text(text.replace(old, new, 1))
