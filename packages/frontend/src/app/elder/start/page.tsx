import { ElderAuthView } from './ElderAuthView';

export const dynamic = 'force-dynamic';

export default function ElderStartPage() {
  const nativeEnabled = process.env.KINSUN_NATIVE_AUTH_ENABLED?.trim().toLowerCase() === 'true';
  const showGoogle = process.env.GOOGLE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';
  const showLine = process.env.LINE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';

  return (
    <ElderAuthView nativeEnabled={nativeEnabled} showGoogle={showGoogle} showLine={showLine} />
  );
}
