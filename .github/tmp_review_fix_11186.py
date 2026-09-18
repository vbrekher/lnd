from pathlib import Path

fee = Path("sweep/fee_bumper.go")
text = fee.read_text()

old = """\t// MissingInputs are inputs that a blocking UTXO lookup confirmed no
\t// longer exist. Unlike SpentInputs, the spending transaction may not be
\t// known.
\tMissingInputs map[wire.OutPoint]struct{}
"""
new = """\t// MissingInputs are inputs that the blocking fallback could not locate
\t// as current UTXOs or as outputs of wallet-known parents. Unlike
\t// SpentInputs, the spending transaction may not be known.
\tMissingInputs map[wire.OutPoint]struct{}
"""
assert text.count(old) == 1, "MissingInputs comment"
text = text.replace(old, new, 1)

old = """\t// Notifier is used to monitor the confirmation status of the tx.
\tNotifier chainntnfs.ChainNotifier

\t// IsInputUnspent performs a blocking chain lookup for an input. It is
"""
new = """\t// Notifier is used to monitor the confirmation status of the tx.
\tNotifier chainntnfs.ChainNotifier

\t// Mempool is used as a synchronous fallback when a spend notification
\t// has not reached the notifier yet.
\tMempool chainntnfs.MempoolWatcher

\t// IsInputUnspent performs a blocking chain lookup for an input. It is
"""
assert text.count(old) == 1, "TxPublisherConfig notifier block"
text = text.replace(old, new, 1)

old = """// findMissingInputs uses a blocking chain lookup to identify which inputs no
// longer exist. This is used only after testmempoolaccept has already returned
// a missing-input error.
func (t *TxPublisher) findMissingInputs(
\tinputs []input.Input) (map[wire.OutPoint]struct{}, error) {

\tmissing := make(map[wire.OutPoint]struct{})
\tfor _, inp := range inputs {
\t\tunspent, err := t.cfg.IsInputUnspent(inp)
\t\tif err != nil {
\t\t\treturn nil, err
\t\t}

\t\tif !unspent {
\t\t\tmissing[inp.OutPoint()] = struct{}{}
\t\t}
\t}

\treturn missing, nil
}
"""
new = """// findMissingInputs uses blocking fallbacks to identify inputs that can no
// longer be located. This only runs after testmempoolaccept reports missing
// inputs and the asynchronous spend subscriptions have not identified a
// spender, so the synchronous lookups are kept off the normal publish path.
func (t *TxPublisher) findMissingInputs(
\tinputs []input.Input) (map[wire.OutPoint]struct{}, error) {

\tmissing := make(map[wire.OutPoint]struct{})
\tfor _, inp := range inputs {
\t\tunspent, err := t.cfg.IsInputUnspent(inp)
\t\tif err != nil {
\t\t\treturn nil, err
\t\t}
\t\tif unspent {
\t\t\tcontinue
\t\t}

\t\top := inp.OutPoint()

\t\t// A chain lookup can report an output as absent while its parent is
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

\t\tmissing[op] = struct{}{}
\t}

\treturn missing, nil
}
"""
assert text.count(old) == 1, "findMissingInputs"
text = text.replace(old, new, 1)

old = """\t\t// Do a non-blocking read to see if the output has been spent.
\t\tselect {
\t\tcase spend, ok := <-spendEvent.Spend:
\t\t\tif !ok {
\t\t\t\tlog.Debugf(\"Spend ntfn for %v canceled\", op)

\t\t\t\tcontinue
\t\t\t}

\t\t\tspendingTx := spend.SpendingTx

\t\t\tlog.Debugf(\"Detected spent of input=%v in tx=%v\", op,
\t\t\t\tspendingTx.TxHash())

\t\t\tspentInputs[op] = spendingTx

\t\t// Move to the next input.
\t\tdefault:
\t\t\tlog.Tracef(\"Input %v not spent yet\", op)
\t\t}
"""
new = """\t\t// Do a non-blocking read to see if the output has been spent.
\t\tselect {
\t\tcase spend, ok := <-spendEvent.Spend:
\t\t\tif !ok {
\t\t\t\tlog.Debugf(\"Spend ntfn for %v canceled\", op)

\t\t\t\tcontinue
\t\t\t}

\t\t\tspendingTx := spend.SpendingTx

\t\t\tlog.Debugf(\"Detected spent of input=%v in tx=%v\", op,
\t\t\t\tspendingTx.TxHash())

\t\t\tspentInputs[op] = spendingTx

\t\t// Move to the next input.
\t\tdefault:
\t\t\t// The historical notifier can lag behind the mempool. Query
\t\t\t// the watcher before falling back to UTXO classification so
\t\t\t// an in-mempool spender is handled as an unknown spend.
\t\t\tif t.cfg.Mempool == nil {
\t\t\t\tlog.Tracef(\"Input %v not spent yet\", op)
\t\t\t\tcontinue
\t\t\t}

\t\t\tt.cfg.Mempool.LookupInputMempoolSpend(op).WhenSome(
\t\t\t\tfunc(spendingTx wire.MsgTx) {
\t\t\t\t\ttx := spendingTx
\t\t\t\t\tspentInputs[op] = &tx
\t\t\t\t},
\t\t\t)
\t\t\tif spendingTx, ok := spentInputs[op]; ok {
\t\t\t\tlog.Debugf(\"Detected mempool spend of input=%v in tx=%v\",
\t\t\t\t\top, spendingTx.TxHash())
\t\t\t\tcontinue
\t\t\t}

\t\t\tlog.Tracef(\"Input %v not spent yet\", op)
\t\t}
"""
assert text.count(old) == 1, "getSpentInputs select"
text = text.replace(old, new, 1)
fee.write_text(text)

server = Path("server.go")
text = server.read_text()
old = """\ts.txPublisher = sweep.NewTxPublisher(sweep.TxPublisherConfig{
\t\tSigner:    cc.Wallet.Cfg.Signer,
\t\tWallet:    cc.Wallet,
\t\tEstimator: cc.FeeEstimator,
\t\tNotifier:  cc.ChainNotifier,
\t\tIsInputUnspent: func(inp input.Input) (bool, error) {
"""
new = """\ts.txPublisher = sweep.NewTxPublisher(sweep.TxPublisherConfig{
\t\tSigner:    cc.Wallet.Cfg.Signer,
\t\tWallet:    cc.Wallet,
\t\tEstimator: cc.FeeEstimator,
\t\tNotifier:  cc.ChainNotifier,
\t\tMempool:   cc.MempoolNotifier,
\t\tIsInputUnspent: func(inp input.Input) (bool, error) {
"""
assert text.count(old) == 1, "server publisher config"
server.write_text(text.replace(old, new, 1))

test = Path("sweep/fee_bumper_missing_inputs_test.go")
test.write_text(r'''package sweep

import (
	"errors"
	"testing"

	"github.com/btcsuite/btcd/wire/v2"
	"github.com/lightningnetwork/lnd/chainntnfs"
	"github.com/lightningnetwork/lnd/fn/v2"
	"github.com/lightningnetwork/lnd/input"
	"github.com/lightningnetwork/lnd/lnwallet/chainfee"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

func missingInputTestRecord(inputs ...input.Input) (*monitorRecord,
	*MockFeeFunction) {

	feeRate := chainfee.SatPerKWeight(1_000)
	feeFunc := &MockFeeFunction{}
	feeFunc.On("FeeRate").Return(feeRate).Once()
	feeFunc.On("Increment").Return(true, nil).Once()

	return &monitorRecord{
		requestID: 1,
		tx:        &wire.MsgTx{},
		req: &BumpRequest{
			Inputs: inputs,
		},
		feeFunction: feeFunc,
	}, feeFunc
}

func emptySpendNotifier(t *testing.T, calls int) *chainntnfs.MockChainNotifier {
	t.Helper()

	notifier := &chainntnfs.MockChainNotifier{}
	notifier.On(
		"RegisterSpendNtfn", mock.Anything, mock.Anything, uint32(1),
	).Return(chainntnfs.NewSpendEvent(func() {}), nil).Times(calls)

	t.Cleanup(func() {
		notifier.AssertExpectations(t)
	})

	return notifier
}

// TestHandleMissingInputsRetryBranches verifies that ambiguous lookup outcomes
// remain retryable instead of turning the whole batch fatal.
func TestHandleMissingInputsRetryBranches(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		lookup   func(input.Input) (bool, error)
		expected error
	}{
		{
			name: "all inputs remain unspent",
			lookup: func(input.Input) (bool, error) {
				return true, nil
			},
			expected: ErrInputMissing,
		},
		{
			name: "blocking lookup fails",
			lookup: func(input.Input) (bool, error) {
				return false, errDummy
			},
			expected: errDummy,
		},
	}

	for _, testCase := range tests {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			inp := createTestInput(10_000, input.WitnessKeyHash)
			record, feeFunc := missingInputTestRecord(&inp)
			defer feeFunc.AssertExpectations(t)

			publisher := NewTxPublisher(TxPublisherConfig{
				Notifier:       emptySpendNotifier(t, 1),
				IsInputUnspent: testCase.lookup,
			})

			result := publisher.handleMissingInputs(record)

			require.Equal(t, TxFailed, result.Event)
			require.ErrorIs(t, result.Err, testCase.expected)
			require.Empty(t, result.MissingInputs)
		})
	}
}

// TestHandleMissingInputsNilLookup preserves the compatibility fallback for
// callers that do not provide the blocking lookup callback.
func TestHandleMissingInputsNilLookup(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	publisher := NewTxPublisher(TxPublisherConfig{
		Notifier: emptySpendNotifier(t, 1),
	})
	record := &monitorRecord{
		requestID: 1,
		tx:        &wire.MsgTx{},
		req: &BumpRequest{
			Inputs: []input.Input{&inp},
		},
	}

	result := publisher.handleMissingInputs(record)

	require.Equal(t, TxFatal, result.Event)
	require.ErrorIs(t, result.Err, ErrInputMissing)
}

// TestHandleMissingInputsWalletParent verifies that a parent transaction known
// to the wallet keeps an unconfirmed output retryable even when the chain UTXO
// lookup excludes mempool outputs.
func TestHandleMissingInputsWalletParent(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	op := inp.OutPoint()
	parent := wire.NewMsgTx(2)
	parent.AddTxOut(&wire.TxOut{Value: 10_000})

	wallet := &MockWallet{}
	wallet.On("FetchTx", op.Hash).Return(parent, nil).Once()
	defer wallet.AssertExpectations(t)

	record, feeFunc := missingInputTestRecord(&inp)
	defer feeFunc.AssertExpectations(t)

	publisher := NewTxPublisher(TxPublisherConfig{
		Wallet:   wallet,
		Notifier: emptySpendNotifier(t, 1),
		IsInputUnspent: func(input.Input) (bool, error) {
			return false, nil
		},
	})

	result := publisher.handleMissingInputs(record)

	require.Equal(t, TxFailed, result.Event)
	require.ErrorIs(t, result.Err, ErrInputMissing)
	require.Empty(t, result.MissingInputs)
}

// TestHandleMissingInputsMempoolSpend verifies that a spender already visible
// in the mempool is treated as an unknown spend even if the notifier has not
// delivered its historical spend notification yet.
func TestHandleMissingInputsMempoolSpend(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	op := inp.OutPoint()
	spendingTx := wire.MsgTx{Version: 2}

	mempool := &chainntnfs.MockMempoolWatcher{}
	mempool.On("LookupInputMempoolSpend", op).
		Return(fn.Some(spendingTx)).Once()
	defer mempool.AssertExpectations(t)

	record, feeFunc := missingInputTestRecord(&inp)
	defer feeFunc.AssertExpectations(t)

	publisher := NewTxPublisher(TxPublisherConfig{
		Notifier: emptySpendNotifier(t, 1),
		Mempool:  mempool,
	})

	result := publisher.handleMissingInputs(record)

	require.Equal(t, TxUnknownSpend, result.Event)
	require.ErrorIs(t, result.Err, ErrUnknownSpent)
	require.Contains(t, result.SpentInputs, op)
	require.Equal(t, spendingTx.TxHash(), result.SpentInputs[op].TxHash())
}

// TestFindMissingInputsWalletLookupError verifies that a wallet fallback error
// is surfaced so the caller can retry rather than classifying an input.
func TestFindMissingInputsWalletLookupError(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	op := inp.OutPoint()

	wallet := &MockWallet{}
	wallet.On("FetchTx", op.Hash).Return(nil, errDummy).Once()
	defer wallet.AssertExpectations(t)

	publisher := NewTxPublisher(TxPublisherConfig{
		Wallet: wallet,
		IsInputUnspent: func(input.Input) (bool, error) {
			return false, nil
		},
	})

	missing, err := publisher.findMissingInputs([]input.Input{&inp})

	require.Nil(t, missing)
	require.True(t, errors.Is(err, errDummy))
}
''')
