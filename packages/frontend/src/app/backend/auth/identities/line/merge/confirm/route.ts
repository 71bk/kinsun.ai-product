import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
  normalizeAppSession,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import {
  lineAccountMergeCookieName,
  lineAccountMergeCookieOptions,
  parsePendingLineAccountMerge,
} from '@/lib/server/line-account-merge';
import { confirmLineAccountMergeWithCore } from '@/lib/server/line-account-link-core';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function redirect(location: string): NextResponse {
  return new NextResponse(null, {
    status: 303,
    headers: {
      'Cache-Control': 'no-store',
      Location: location,
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) return new Response(null, { status: 403 });
  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  const pending = parsePendingLineAccountMerge(
    request.cookies.get(lineAccountMergeCookieName())?.value,
  );
  if (!appSession || !pending) {
    return redirect('/account/sign-in-methods?error=merge_expired');
  }
  try {
    const result = await confirmLineAccountMergeWithCore(appSession, pending.mergeToken);
    if (result.status === 'MANUAL_REVIEW_REQUIRED') {
      return redirect('/account/sign-in-methods?error=manual_review_required');
    }
    const response = redirect('/account/sign-in-methods?status=merged');
    response.cookies.set(
      appSessionCookieName(),
      result.sessionToken,
      appSessionCookieOptions(appSessionMaxAge(result.idleExpiresAt, result.absoluteExpiresAt)),
    );
    response.cookies.set(lineAccountMergeCookieName(), '', {
      ...lineAccountMergeCookieOptions(),
      expires: new Date(0),
      maxAge: 0,
    });
    return response;
  } catch {
    return redirect('/account/sign-in-methods?error=merge_failed');
  }
}
