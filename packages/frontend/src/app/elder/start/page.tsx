import { ElderStartView } from './ElderStartView';

export const dynamic = 'force-dynamic';

/** See family/join/page.tsx for why this server/client split exists. */
export default function ElderStartPage() {
  const nativeEnabled = process.env.KINSUN_NATIVE_AUTH_ENABLED?.trim().toLowerCase() === 'true';
  const showGoogle = process.env.GOOGLE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';
  const showLine = process.env.LINE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';

  return <ElderStartView nativeEnabled={nativeEnabled} showGoogle={showGoogle} showLine={showLine} />;
}
