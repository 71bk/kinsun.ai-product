import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '智慧長照 AI 陪伴系統 - 長者介面',
  description: '語音互動陪伴',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  );
}
