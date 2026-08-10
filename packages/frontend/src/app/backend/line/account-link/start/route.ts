import { type NextRequest, NextResponse } from 'next/server';
import {
  lineLinkCookieName,
  lineLinkCookieOptions,
  normalizeLineLinkToken,
} from '@/lib/server/line-account-link';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function redirect(location: string): NextResponse {
  return new NextResponse(null, {
    status: 303,
    headers: {
      'Cache-Control': 'no-store',
      Location: location,
      'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

function clearLineLinkCookie(response: NextResponse): NextResponse {
  response.cookies.set(lineLinkCookieName(), '', {
    ...lineLinkCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

export function GET(request: NextRequest): Response {
  const keys = [...request.nextUrl.searchParams.keys()];
  const values = request.nextUrl.searchParams.getAll('linkToken');
  const token = values.length === 1 ? normalizeLineLinkToken(values[0]) : null;
  if (keys.length !== 1 || keys[0] !== 'linkToken' || !token) {
    return clearLineLinkCookie(redirect('/line/account-link?error=invalid_link'));
  }

  const response = redirect('/line/account-link');
  response.cookies.set(lineLinkCookieName(), token, lineLinkCookieOptions());
  return response;
}
