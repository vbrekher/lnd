from pathlib import Path

server = Path("server.go")
text = server.read_text()
marker = "//nolint:funlen\nfunc newServer"
helper = '''// classifyInputUtxoLookup maps the blocking UTXO lookup result into the
// missing-input classifier used by the transaction publisher.
func classifyInputUtxoLookup(err error) (bool, error) {
\tswitch {
\tcase err == nil:
\t\treturn true, nil

\tcase errors.Is(err, btcwallet.ErrOutputSpent),
\t\terrors.Is(err, btcwallet.ErrOutputNotFound):

\t\treturn false, nil

\tdefault:
\t\treturn false, err
\t}
}

'''
if text.count(marker) != 1:
    raise SystemExit("expected newServer marker exactly once")
text = text.replace(marker, helper + marker, 1)

old = '''\t\tIsInputUnspent: func(inp input.Input) (bool, error) {
\t\t\top := inp.OutPoint()
\t\t\t_, err := cc.ChainIO.GetUtxo(
\t\t\t\t&op, inp.SignDesc().Output.PkScript,
\t\t\t\tinp.HeightHint(), s.quit,
\t\t\t)

\t\t\tswitch {
\t\t\tcase err == nil:
\t\t\t\treturn true, nil

\t\t\tcase errors.Is(err, btcwallet.ErrOutputSpent),
\t\t\t\terrors.Is(err, btcwallet.ErrOutputNotFound):

\t\t\t\treturn false, nil

\t\t\tdefault:
\t\t\t\treturn false, err
\t\t\t}
\t\t},
'''
new = '''\t\tIsInputUnspent: func(inp input.Input) (bool, error) {
\t\t\top := inp.OutPoint()
\t\t\t_, err := cc.ChainIO.GetUtxo(
\t\t\t\t&op, inp.SignDesc().Output.PkScript,
\t\t\t\tinp.HeightHint(), s.quit,
\t\t\t)

\t\t\treturn classifyInputUtxoLookup(err)
\t\t},
'''
if text.count(old) != 1:
    raise SystemExit("expected IsInputUnspent closure exactly once")
server.write_text(text.replace(old, new, 1))

Path("server_input_lookup_test.go").write_text(r'''package lnd

import (
	"errors"
	"testing"

	"github.com/lightningnetwork/lnd/lnwallet/btcwallet"
	"github.com/stretchr/testify/require"
)

// TestClassifyInputUtxoLookup verifies the production error mapping used by
// the missing-input fallback.
func TestClassifyInputUtxoLookup(t *testing.T) {
	t.Parallel()

	lookupErr := errors.New("lookup failed")
	tests := []struct {
		name        string
		err         error
		wantUnspent bool
		wantErr     error
	}{
		{
			name:        "unspent",
			wantUnspent: true,
		},
		{
			name:    "spent",
			err:     btcwallet.ErrOutputSpent,
			wantErr: nil,
		},
		{
			name:    "not found",
			err:     btcwallet.ErrOutputNotFound,
			wantErr: nil,
		},
		{
			name:    "backend error",
			err:     lookupErr,
			wantErr: lookupErr,
		},
	}

	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			unspent, err := classifyInputUtxoLookup(testCase.err)
			require.Equal(t, testCase.wantUnspent, unspent)
			if testCase.wantErr == nil {
				require.NoError(t, err)
				return
			}

			require.ErrorIs(t, err, testCase.wantErr)
		})
	}
}
''')

test = Path("sweep/fee_bumper_missing_inputs_test.go")
text = test.read_text()
text += r'''

// TestHandleInitialTxErrorMissingInput verifies the initial error path routes
// ErrInputMissing through the missing-input classifier.
func TestHandleInitialTxErrorMissingInput(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	record, feeFunc := missingInputTestRecord(&inp)
	defer feeFunc.AssertExpectations(t)

	publisher := NewTxPublisher(TxPublisherConfig{
		Notifier: emptySpendNotifier(t, 1),
		IsInputUnspent: func(input.Input) (bool, error) {
			return true, nil
		},
	})
	resultChan := make(chan *BumpResult, 1)
	publisher.subscriberChans.Store(record.requestID, resultChan)

	publisher.handleInitialTxError(record, ErrInputMissing)

	result := <-resultChan
	require.Equal(t, TxFailed, result.Event)
	require.ErrorIs(t, result.Err, ErrInputMissing)
}

// TestHandleReplacementTxErrorMissingInput verifies the replacement path also
// routes ErrInputMissing through the missing-input classifier.
func TestHandleReplacementTxErrorMissingInput(t *testing.T) {
	t.Parallel()

	inp := createTestInput(10_000, input.WitnessKeyHash)
	record, feeFunc := missingInputTestRecord(&inp)
	defer feeFunc.AssertExpectations(t)

	publisher := NewTxPublisher(TxPublisherConfig{
		Notifier: emptySpendNotifier(t, 1),
		IsInputUnspent: func(input.Input) (bool, error) {
			return true, nil
		},
	})

	resultOpt := publisher.handleReplacementTxError(
		record, wire.NewMsgTx(2), ErrInputMissing,
	)
	result, err := resultOpt.UnwrapOrErr(errors.New("missing bump result"))

	require.NoError(t, err)
	require.Equal(t, TxFailed, result.Event)
	require.ErrorIs(t, result.Err, ErrInputMissing)
}
'''
test.write_text(text)
