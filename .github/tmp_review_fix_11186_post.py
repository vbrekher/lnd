from pathlib import Path

fee = Path("sweep/fee_bumper.go")
text = fee.read_text()

old = """\t// MissingInputs are inputs that the blocking fallback could not locate
\t// as current UTXOs or as outputs of wallet-known parents. Unlike
\t// SpentInputs, the spending transaction may not be known.
"""
new = """\t// MissingInputs are inputs that the blocking fallback could not locate
\t// as current UTXOs or as outputs of wallet-known unconfirmed parents.
\t// Unlike SpentInputs, the spending transaction may not be known.
"""
assert text.count(old) == 1, "MissingInputs comment"
text = text.replace(old, new, 1)

old = """\t\t// A chain lookup can report an output as absent while its parent is
\t\t// still unconfirmed because the backend excludes mempool outputs.
\t\t// If the wallet knows the parent and the output index exists, keep
\t\t// the input retryable instead of declaring it missing.
\t\tif t.cfg.Wallet != nil {
\t\t\tparent, err := t.cfg.Wallet.FetchTx(op.Hash)
\t\t\tif err != nil {
\t\t\t\treturn nil, err
\t\t\t}
\t\t\tif parent != nil && int(op.Index) < len(parent.TxOut) {
\t\t\t\tcontinue
\t\t\t}
\t\t}
"""
new = """\t\t// A chain lookup can report an output as absent while its
\t\t// parent is still unconfirmed because the backend excludes
\t\t// mempool outputs. If the wallet knows the parent, verify that
\t\t// it is still unconfirmed before keeping the input retryable.
\t\tif t.cfg.Wallet != nil {
\t\t\tparent, err := t.cfg.Wallet.FetchTx(op.Hash)
\t\t\tif err != nil {
\t\t\t\treturn nil, err
\t\t\t}
\t\t\tif parent != nil && int(op.Index) < len(parent.TxOut) {
\t\t\t\twallet := t.cfg.Wallet
\t\t\t\tdetails, err := wallet.GetTransactionDetails(
\t\t\t\t\t&op.Hash,
\t\t\t\t)
\t\t\t\tif err != nil {
\t\t\t\t\treturn nil, err
\t\t\t\t}
\t\t\t\tif details != nil &&
\t\t\t\t\tdetails.NumConfirmations == 0 {

\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t}
\t\t}
"""
assert text.count(old) == 1, "wallet parent fallback"
text = text.replace(old, new, 1)

replacements = {
    "\t\t// blocking lookup callback. Production wiring always provides it.\n":
        "\t\t// blocking lookup callback. Production wiring always\n"
        "\t\t// provides it.\n",
    "\t\t// lookup disagree. Retry instead of permanently dropping the set.\n":
        "\t\t// lookup disagree. Retry instead of permanently dropping\n"
        "\t\t// the set.\n",
    "\t\t// missing inputs are removed and the remaining inputs are retried.\n":
        "\t\t// missing inputs are removed and the remaining inputs are\n"
        "\t\t// retried.\n",
    "\t\t\t// The historical notifier can lag behind the mempool. Query\n"
    "\t\t\t// the watcher before falling back to UTXO classification so\n":
        "\t\t\t// The historical notifier can lag behind the mempool.\n"
        "\t\t\t// Query the watcher before falling back to UTXO\n"
        "\t\t\t// classification so\n",
    "\t\t\t\tlog.Debugf(\"Detected mempool spend of input=%v in tx=%v\",\n"
    "\t\t\t\t\top, spendingTx.TxHash())\n":
        "\t\t\t\tlog.Debugf(\n"
        "\t\t\t\t\t\"Detected mempool spend of input=%v in tx=%v\",\n"
        "\t\t\t\t\top, spendingTx.TxHash(),\n"
        "\t\t\t\t)\n",
}
for old, new in replacements.items():
    assert old in text, f"missing expected fee_bumper fragment: {old!r}"
    text = text.replace(old, new, 1)
fee.write_text(text)

test = Path("sweep/fee_bumper_missing_inputs_test.go")
text = test.read_text()

old = "\tfor _, testCase := range tests {\n\t\ttestCase := testCase\n\t\tt.Run(testCase.name, func(t *testing.T) {\n"
new = "\tfor _, testCase := range tests {\n\t\tt.Run(testCase.name, func(t *testing.T) {\n"
assert old in text, "loop copy"
text = text.replace(old, new, 1)

old = "\t\"github.com/lightningnetwork/lnd/input\"\n\t\"github.com/lightningnetwork/lnd/lnwallet/chainfee\"\n"
new = "\t\"github.com/lightningnetwork/lnd/input\"\n\t\"github.com/lightningnetwork/lnd/lnwallet\"\n\t\"github.com/lightningnetwork/lnd/lnwallet/chainfee\"\n"
assert old in text, "lnwallet import"
text = text.replace(old, new, 1)

old = """\twallet := &MockWallet{}
\twallet.On("FetchTx", op.Hash).Return(parent, nil).Once()
\tdefer wallet.AssertExpectations(t)
"""
new = """\twallet := &MockWallet{}
\twallet.On("FetchTx", op.Hash).Return(parent, nil).Once()
\twallet.On("GetTransactionDetails", mock.Anything).Return(
\t\t&lnwallet.TransactionDetail{NumConfirmations: 0}, nil,
\t).Once()
\tdefer wallet.AssertExpectations(t)
"""
assert old in text, "unconfirmed parent test mock"
text = text.replace(old, new, 1)

marker = "// TestHandleMissingInputsMempoolSpend verifies that a spender already visible\n"
confirmed_test = """// TestFindMissingInputsConfirmedWalletParent verifies that a wallet-known
// parent alone does not keep a confirmed, spent output retryable.
func TestFindMissingInputsConfirmedWalletParent(t *testing.T) {
\tt.Parallel()

\tinp := createTestInput(10_000, input.WitnessKeyHash)
\top := inp.OutPoint()
\tparent := wire.NewMsgTx(2)
\tparent.AddTxOut(&wire.TxOut{Value: 10_000})

\twallet := &MockWallet{}
\twallet.On("FetchTx", op.Hash).Return(parent, nil).Once()
\twallet.On("GetTransactionDetails", mock.Anything).Return(
\t\t&lnwallet.TransactionDetail{NumConfirmations: 1}, nil,
\t).Once()
\tdefer wallet.AssertExpectations(t)

\tpublisher := NewTxPublisher(TxPublisherConfig{
\t\tWallet: wallet,
\t\tIsInputUnspent: func(input.Input) (bool, error) {
\t\t\treturn false, nil
\t\t},
\t})

\tmissing, err := publisher.findMissingInputs([]input.Input{&inp})

\trequire.NoError(t, err)
\trequire.Contains(t, missing, op)
}

"""
assert marker in text, "confirmed parent insertion point"
text = text.replace(marker, confirmed_test + marker, 1)
test.write_text(text)

# Keep the final generated source within lnd's custom 80-column and nlreturn
# rules. These replacements are deliberately narrow so any source drift fails
# validation instead of silently editing a different location.
text = fee.read_text()
old = "\t\t\treturn t.createMissingInputRetryResult(r, ErrInputMissing)\n"
new = (
    "\t\t\treturn t.createMissingInputRetryResult(\n"
    "\t\t\t\tr, ErrInputMissing,\n"
    "\t\t\t)\n"
)
assert text.count(old) == 1, "retry-result line"
text = text.replace(old, new, 1)

old = (
    "\t\t\t\tlog.Debugf(\n"
    "\t\t\t\t\t\"Detected mempool spend of input=%v in tx=%v\",\n"
    "\t\t\t\t\top, spendingTx.TxHash(),\n"
    "\t\t\t\t)\n"
    "\t\t\t\tcontinue\n"
)
new = (
    "\t\t\t\tlog.Debugf(\n"
    "\t\t\t\t\t\"Detected mempool spend of input=%v \"+\n"
    "\t\t\t\t\t\t\"in tx=%v\", op, spendingTx.TxHash(),\n"
    "\t\t\t\t)\n\n"
    "\t\t\t\tcontinue\n"
)
assert text.count(old) == 1, "mempool-spend log block"
fee.write_text(text.replace(old, new, 1))
