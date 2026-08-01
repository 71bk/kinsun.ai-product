'use client';

export interface MicPermissionGuideProps {
  onRetry: () => void;
}

/** Plain-language mic-permission guidance shown when the browser denies/hasn't granted access (A01.3). */
export function MicPermissionGuide({ onRetry }: MicPermissionGuideProps) {
  return (
    <div
      role="alert"
      style={{
        maxWidth: 420,
        margin: '24px auto',
        padding: 20,
        borderRadius: 12,
        background: '#fff7ed',
        border: '1px solid #f6ad55',
        textAlign: 'center',
        fontSize: 18,
        lineHeight: 1.6,
      }}
    >
      <p>需要允許使用麥克風，才能跟您說話喔。</p>
      <p>請在瀏覽器上方的提示，點選「允許」使用麥克風。</p>
      <button
        type="button"
        onClick={onRetry}
        style={{
          marginTop: 12,
          padding: '10px 24px',
          fontSize: 18,
          borderRadius: 8,
          border: 'none',
          background: '#2b6cb0',
          color: '#fff',
          cursor: 'pointer',
        }}
      >
        再試一次
      </button>
    </div>
  );
}
