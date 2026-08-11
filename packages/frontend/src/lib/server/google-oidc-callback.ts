import {
  googleOidcStateMatches,
  parseGoogleOidcTransaction,
  type GoogleOidcTransaction,
} from './google-oidc-transaction';

const GOOGLE_CALLBACK_ISSUER = 'https://accounts.google.com';

export type GoogleOidcCallbackFailureReason =
  'ISSUER' | 'MALFORMED_REDIRECT' | 'PROVIDER_ERROR' | 'TRANSACTION';

export class GoogleOidcCallbackError extends Error {
  readonly reason: GoogleOidcCallbackFailureReason;
  readonly clearCurrentTransaction: boolean;

  constructor(reason: GoogleOidcCallbackFailureReason, clearCurrentTransaction: boolean) {
    super('Google OIDC callback rejected');
    this.name = 'GoogleOidcCallbackError';
    this.reason = reason;
    this.clearCurrentTransaction = clearCurrentTransaction;
  }
}

export interface ValidatedGoogleOidcCallback {
  authorizationCode: string;
  transaction: GoogleOidcTransaction;
}

/**
 * Validate the route-ready Google callback envelope without retaining any
 * attacker-controlled query values in an error. Token exchange remains a
 * separate step and the resulting ID token still requires Core verification.
 */
export function validateGoogleOidcCallback(
  searchParams: URLSearchParams,
  transactionCookie: string | undefined,
): ValidatedGoogleOidcCallback {
  const codes = searchParams.getAll('code');
  const states = searchParams.getAll('state');
  const issuers = searchParams.getAll('iss');
  const transaction = parseGoogleOidcTransaction(transactionCookie);
  const callbackOwnsCurrentTransaction =
    transaction !== null &&
    states.length === 1 &&
    googleOidcStateMatches(transaction, states[0] ?? null);
  const clearCurrentTransaction = transaction === null || callbackOwnsCurrentTransaction;

  if (searchParams.has('error')) {
    throw new GoogleOidcCallbackError('PROVIDER_ERROR', clearCurrentTransaction);
  }
  if (codes.length !== 1 || states.length !== 1 || issuers.length !== 1) {
    throw new GoogleOidcCallbackError('MALFORMED_REDIRECT', clearCurrentTransaction);
  }
  if (issuers[0] !== GOOGLE_CALLBACK_ISSUER) {
    throw new GoogleOidcCallbackError('ISSUER', clearCurrentTransaction);
  }
  if (!transaction || !callbackOwnsCurrentTransaction) {
    throw new GoogleOidcCallbackError('TRANSACTION', clearCurrentTransaction);
  }
  return { authorizationCode: codes[0] ?? '', transaction };
}
