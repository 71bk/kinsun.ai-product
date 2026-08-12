import {
  lineOidcStateMatches,
  parseLineOidcTransaction,
  type LineOidcTransaction,
} from './line-oidc-transaction';

export type LineOidcCallbackFailureReason = 'MALFORMED_REDIRECT' | 'PROVIDER_ERROR' | 'TRANSACTION';

export class LineOidcCallbackError extends Error {
  constructor(
    readonly reason: LineOidcCallbackFailureReason,
    readonly clearCurrentTransaction: boolean,
  ) {
    super('LINE OIDC callback rejected');
    this.name = 'LineOidcCallbackError';
  }
}

export interface ValidatedLineOidcCallback {
  authorizationCode: string;
  transaction: LineOidcTransaction;
}

export function validateLineOidcCallback(
  searchParams: URLSearchParams,
  transactionCookie: string | undefined,
): ValidatedLineOidcCallback {
  const codes = searchParams.getAll('code');
  const states = searchParams.getAll('state');
  const transaction = parseLineOidcTransaction(transactionCookie);
  const callbackOwnsCurrentTransaction =
    transaction !== null &&
    states.length === 1 &&
    lineOidcStateMatches(transaction, states[0] ?? null);
  const clearCurrentTransaction = transaction === null || callbackOwnsCurrentTransaction;

  if (searchParams.has('error')) {
    throw new LineOidcCallbackError('PROVIDER_ERROR', clearCurrentTransaction);
  }
  if (codes.length !== 1 || states.length !== 1) {
    throw new LineOidcCallbackError('MALFORMED_REDIRECT', clearCurrentTransaction);
  }
  if (!transaction || !callbackOwnsCurrentTransaction) {
    throw new LineOidcCallbackError('TRANSACTION', clearCurrentTransaction);
  }
  return { authorizationCode: codes[0] ?? '', transaction };
}
