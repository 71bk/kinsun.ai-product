'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CheckCircle,
  CircleDashed,
  FirstAidKit,
  LockKey,
  ShieldCheck,
  User,
  UsersThree,
} from '@phosphor-icons/react';
import styles from './Landing.module.css';

const VOICE_STEPS = [
  {
    title: '一句日常對話，先保留原始語境。',
    body: '小暖先聽懂，再整理。這時還沒有任何「正式事實」。',
  },
  {
    title: '原始語音不消失，AI 的整理也不遮住來源。',
    body: '轉寫與來源並排保留，照護資訊隨時能回到原始對話核對。',
  },
  {
    title: 'AI 可以提出候選，但不能跳過確認。',
    body: '候選事件保留證據與未確認狀態，交由照服員覆核後才進入正式流程。',
  },
] as const;

const MEMORY_STEPS = [
  {
    title: 'AI 可以理解一句話，但不代表它有資格把它記成事實。',
    body: '這是 Kinsun.ai 最重要的信任邊界。',
  },
  {
    title: '重要的記憶，由人按下確認才成立。',
    body: '確認不是一個小流程，而是小暖與長者建立信任的方式。',
  },
] as const;

const ROLE_STEPS = [
  {
    title: '一句對話，最後成為有來源、可覆核的照護資訊。',
    body: '照服員看到的是證據與下一步，而不是神祕的 AI 分數。',
  },
  {
    title: '同一件事情，不同角色看見不同內容。',
    body: '家屬端只看到被授權、已發布的生活近況。',
  },
] as const;

function useScrollStage(stageCount: number) {
  const sectionRef = useRef<HTMLElement>(null);
  const [stage, setStage] = useState(0);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const compactViewport = window.matchMedia('(max-width: 767px)');
    if (reducedMotion.matches || compactViewport.matches) return;

    let animationFrame = 0;
    const update = () => {
      animationFrame = 0;
      const section = sectionRef.current;
      if (!section) return;

      const rect = section.getBoundingClientRect();
      const scrollable = Math.max(section.offsetHeight - window.innerHeight, 1);
      const nextProgress = Math.min(Math.max(-rect.top / scrollable, 0), 1);
      const nextStage = Math.min(Math.floor(nextProgress * stageCount), stageCount - 1);
      setProgress(nextProgress);
      setStage(nextStage);
    };
    const scheduleUpdate = () => {
      if (animationFrame) return;
      animationFrame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    return () => {
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
    };
  }, [stageCount]);

  return { sectionRef, stage, progress };
}

function Brand() {
  return (
    <Link href="/" className={styles.brand} aria-label="Kinsun.ai 首頁">
      <span className={styles.brandDot} aria-hidden="true" />
      <span>kinsun.ai</span>
    </Link>
  );
}

function CinematicHeader() {
  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        <Brand />
        <nav className={styles.desktopNav} aria-label="主要導覽">
          <a href="#product">產品介紹</a>
          <a href="#how-it-works">如何運作</a>
          <a href="#trust">資料與隱私</a>
          <a href="#institutions">給機構</a>
        </nav>
        <div className={styles.headerActions}>
          <Link href="/sign-in" className={styles.headerLogin}>
            登入
          </Link>
          <Link href="/sign-in" className={styles.headerPrimary}>
            開始使用
          </Link>
        </div>
      </div>
    </header>
  );
}

function MascotHalo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`${styles.mascotHalo} ${compact ? styles.mascotHaloCompact : ''}`}>
      <span className={styles.haloOuter} aria-hidden="true" />
      <span className={styles.haloMiddle} aria-hidden="true" />
      <span className={styles.haloInner} aria-hidden="true" />
      <img src="/mascot.png" alt="小暖語音陪伴角色" className={styles.mascot} />
    </div>
  );
}

function VoicePanel({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`${styles.voicePanel} ${compact ? styles.voicePanelCompact : ''}`}>
      <p className={styles.voicePrompt}>今天想跟小暖聊什麼呢？</p>
      <div className={styles.voiceQuote}>「昨暗一直睏袂去。」</div>
      <div className={styles.micControl} aria-hidden="true">
        <span />
      </div>
      <p className={styles.voiceHint}>說完了，按一下</p>
    </div>
  );
}

function Hero() {
  return (
    <section id="product" className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.heroCopy}>
        <p className={styles.eyebrow}>Voice-first eldercare intelligence</p>
        <h1 id="hero-title">陪長輩聊生活，也讓關心的人更安心。</h1>
        <p className={styles.heroBody}>
          小暖用自然語音陪伴日常，幫忙整理重要事情。該不該記住，由人決定，不由 AI
          決定。
        </p>
        <div className={styles.heroActions}>
          <Link href="/sign-in" className={styles.primaryAction}>
            開始使用
          </Link>
          <a href="#how-it-works" className={styles.secondaryAction}>
            看看怎麼運作 <span aria-hidden="true">→</span>
          </a>
        </div>
        <p className={styles.heroTrust}>重要記憶確認後才保存 · 分享範圍由本人決定</p>
      </div>

      <div className={styles.heroVisual}>
        <MascotHalo />
        <VoicePanel compact />
      </div>
    </section>
  );
}

function StoryAnnotation({ label, progress }: { label: string; progress: number }) {
  return (
    <div className={styles.storyAnnotation}>
      <span>{label}</span>
      <progress max={1} value={progress} aria-label={`${label} 捲動進度`} />
    </div>
  );
}

function VoiceStory() {
  const { sectionRef, stage, progress } = useScrollStage(VOICE_STEPS.length);

  return (
    <section ref={sectionRef} id="how-it-works" className={styles.scrollStory}>
      <div className={styles.storySticky} aria-hidden="true">
        <StoryAnnotation label="一句話，如何成為可覆核資訊" progress={progress} />
        <div className={styles.storyCopyStack}>
          {VOICE_STEPS.map((step, index) => (
            <div key={step.title} className={styles.storyCopy} data-active={stage === index}>
              <h2>{step.title}</h2>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
        <div className={styles.storyVisualStack}>
          <div className={styles.storyVisual} data-active={stage === 0}>
            <div className={styles.voiceStageMascot}>
              <MascotHalo compact />
            </div>
            <VoicePanel />
          </div>
          <div className={styles.storyVisual} data-active={stage === 1}>
            <EvidenceFlow />
          </div>
          <div className={styles.storyVisual} data-active={stage === 2}>
            <CandidateEvent />
          </div>
        </div>
      </div>
      <div className={styles.srOnly}>
        <h2>一句話，如何成為可覆核資訊</h2>
        <ol>
          {VOICE_STEPS.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong> {step.body}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function EvidenceFlow() {
  return (
    <div className={styles.evidenceFlow}>
      <div className={styles.evidenceCard}>
        <span className={styles.statusPill}>長者原始語音</span>
        <strong>「昨暗一直睏袂去。」</strong>
      </div>
      <div className={styles.evidenceCard}>
        <span className={styles.statusPill}>ASR 轉寫</span>
        <strong>昨晚一直睡不著。</strong>
        <small>來源：今日 09:42 小暖對話</small>
      </div>
      <span className={styles.flowArrow} aria-hidden="true">
        ↓
      </span>
      <div className={styles.nextStep}>下一步：整理成 AI 候選事件</div>
    </div>
  );
}

function CandidateEvent() {
  return (
    <article className={styles.candidateCard}>
      <span className={styles.candidatePill}>AI 候選事件</span>
      <h3>睡眠相關事件</h3>
      <p>昨晚表示沒有睡好。</p>
      <div className={styles.sourceBlock}>
        <strong>來源證據</strong>
        <span>「昨暗一直睏袂去。」</span>
        <small>今日 09:42 · 原始對話</small>
      </div>
      <p className={styles.pendingState}>
        <CircleDashed size={20} weight="bold" aria-hidden="true" />
        尚未成為正式照護紀錄
      </p>
      <span className={styles.demoAction}>交給照服員覆核</span>
    </article>
  );
}

function MemoryStory() {
  const { sectionRef, stage, progress } = useScrollStage(MEMORY_STEPS.length);

  return (
    <section ref={sectionRef} className={`${styles.scrollStory} ${styles.darkStory}`}>
      <div className={styles.storySticky} aria-hidden="true">
        <StoryAnnotation label="重要記憶的確認邊界" progress={progress} />
        <div className={styles.storyCopyStack}>
          {MEMORY_STEPS.map((step, index) => (
            <div key={step.title} className={styles.storyCopy} data-active={stage === index}>
              <h2>{step.title}</h2>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
        <div className={styles.storyVisualStack}>
          <div className={styles.storyVisual} data-active={stage === 0}>
            <div className={styles.memoryCandidate}>
              <span className={styles.candidatePill}>尚未確認</span>
              <strong>星期日可能會等女兒小美打電話</strong>
              <small>候選記憶</small>
            </div>
          </div>
          <div className={styles.storyVisual} data-active={stage === 1}>
            <MemoryConfirmation />
          </div>
        </div>
      </div>
      <div className={styles.srOnly}>
        <h2>重要記憶的確認邊界</h2>
        <ol>
          {MEMORY_STEPS.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong> {step.body}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function MemoryConfirmation() {
  return (
    <div className={styles.memoryConfirmation}>
      <article className={styles.confirmationDialog}>
        <h3>要讓我記住這件事嗎？</h3>
        <p>「星期日可能會等女兒小美打電話。」</p>
        <small>記住後，下次聊天時，小暖可以更自然地延續這件事。</small>
        <div className={styles.confirmationActions}>
          <span className={styles.demoAction}>記住</span>
          <span className={styles.demoSecondary}>不要記</span>
        </div>
      </article>
      <div className={styles.confirmedBanner}>
        <CheckCircle size={38} weight="fill" aria-hidden="true" />
        <span>
          <strong>已由林阿嬤確認</strong>
          <small>Confirmed Memory · 示意資料</small>
        </span>
      </div>
    </div>
  );
}

function RoleStory() {
  const { sectionRef, stage, progress } = useScrollStage(ROLE_STEPS.length);

  return (
    <section ref={sectionRef} id="institutions" className={`${styles.scrollStory} ${styles.roleStory}`}>
      <div className={styles.storySticky} aria-hidden="true">
        <StoryAnnotation label="照服員與家屬看到什麼" progress={progress} />
        <div className={styles.storyCopyStack}>
          {ROLE_STEPS.map((step, index) => (
            <div key={step.title} className={styles.storyCopy} data-active={stage === index}>
              <h2>{step.title}</h2>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
        <div className={styles.storyVisualStack}>
          <div className={styles.storyVisual} data-active={stage === 0}>
            <CareDashboard />
          </div>
          <div className={styles.storyVisual} data-active={stage === 1}>
            <FamilySurface />
          </div>
        </div>
      </div>
      <div className={styles.srOnly}>
        <h2>照服員與家屬看到什麼</h2>
        <ol>
          {ROLE_STEPS.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong> {step.body}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CareDashboard() {
  return (
    <div className={styles.careReveal}>
      <div className={styles.browserMockup}>
        <div className={styles.browserBar}>
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <small>kinsun.ai · Care · 示意資料</small>
        </div>
        <aside className={styles.careSidebar}>
          <strong>kinsun.ai</strong>
          <span data-active="true">總覽</span>
          <span>長者</span>
          <span>待覆核</span>
          <span>關懷待辦</span>
        </aside>
        <div className={styles.dashboardBody}>
          <h3>幸福日照中心</h3>
          <p>今天需要處理的事情</p>
          <div className={styles.metrics}>
            <span><strong>12</strong><small>今日長者</small></span>
            <span><strong>38</strong><small>AI 互動</small></span>
            <span><strong>5</strong><small>待覆核</small></span>
          </div>
          <div className={styles.elderRows}>
            <span><i />林阿嬤 <small>4 次互動</small><b>查看詳情 →</b></span>
            <span><i />張阿姨 <small>2 次互動</small><b>查看詳情 →</b></span>
            <span><i />陳伯伯 <small>尚無</small><b>查看詳情 →</b></span>
          </div>
        </div>
        <aside className={styles.attentionPanel}>
          <strong>需要處理</strong>
          <span>林阿嬤<br />2 筆待覆核</span>
          <b>開始覆核 →</b>
          <span>張阿姨<br />1 項待辦</span>
        </aside>
      </div>
      <div className={styles.boundaryBanner}>
        <strong>AI 候選 ≠ 正式紀錄</strong>
        <span>確認、修正或排除後，才進入正式照護流程。</span>
      </div>
    </div>
  );
}

function FamilySurface() {
  return (
    <div className={styles.familyReveal}>
      <div className={styles.phoneMockup}>
        <strong className={styles.phoneBrand}>kinsun.ai</strong>
        <h3>林阿嬤的近況</h3>
        <small>最後更新：今天 10:05 · 示意資料</small>
        <div className={styles.summaryCard}>
          <strong>今日摘要</strong>
          <span><b>飲食</b>早餐有記錄吃粥。</span>
          <span><b>睡眠</b>昨晚有提到沒有睡好。</span>
          <span><b>社交</b>今天有提到家人聯繫。</span>
        </div>
        <div className={styles.weekCard}>
          <strong>本週概覽</strong>
          <span>本週有 5 天互動紀錄、2 次活動紀錄。</span>
        </div>
        <b className={styles.reportLink}>查看完整報表 →</b>
      </div>
      <aside className={styles.hiddenDataCard}>
        <strong>不顯示</strong>
        <span>— 原始逐字稿</span>
        <span>— 語音辨識信心分數</span>
        <span>— 未覆核事件</span>
        <span>— 內部照護筆記</span>
      </aside>
    </div>
  );
}

function MobileNarrative() {
  return (
    <div className={styles.mobileNarrative}>
      <section className={styles.mobileChapter} aria-labelledby="mobile-voice-title">
        <span className={styles.statusPill}>1 · 說話</span>
        <h2 id="mobile-voice-title">「昨暗一直睏袂去。」</h2>
        <div className={styles.mobileEvidenceCard}>
          <strong>ASR 轉寫</strong>
          <span>昨晚一直睡不著。</span>
          <small>來源保留，可回頭核對</small>
        </div>
        <span className={styles.mobileArrow} aria-hidden="true">↓</span>
        <CandidateEvent />
      </section>

      <section className={`${styles.mobileChapter} ${styles.mobileDark}`} aria-labelledby="mobile-memory-title">
        <h2 id="mobile-memory-title">AI 可以理解一句話，但不能自己把它記成事實。</h2>
        <MemoryConfirmation />
      </section>

      <section className={styles.mobileChapter} aria-labelledby="mobile-family-title">
        <h2 id="mobile-family-title">不同角色，看見不同資訊。</h2>
        <FamilySurface />
        <p className={styles.mobileBoundary}>只顯示已授權、已發布內容</p>
      </section>
    </div>
  );
}

const TRUST_ITEMS = [
  {
    icon: CheckCircle,
    title: '確認後才記住',
    body: '重要記憶不由 AI 自動決定。',
  },
  {
    icon: LockKey,
    title: '分享需要授權',
    body: '家屬只看到被允許的內容。',
  },
  {
    icon: CircleDashed,
    title: 'AI 候選 ≠ 事實',
    body: '不確定內容需要人工覆核。',
  },
  {
    icon: ShieldCheck,
    title: '隨時可以撤回',
    body: '記憶與分享設定都能被管理。',
  },
] as const;

function TrustSection() {
  return (
    <section id="trust" className={styles.trustSection} aria-labelledby="trust-title">
      <div className={styles.sectionIntro}>
        <h2 id="trust-title">資料掌握在人手上</h2>
        <p>不是更多監控，而是更清楚的確認、授權與撤回。</p>
      </div>
      <div className={styles.trustGrid}>
        {TRUST_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <article key={item.title}>
              <Icon size={28} weight="bold" aria-hidden="true" />
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function RoleLinks() {
  return (
    <div className={styles.roleLinks} aria-label="依身分開始">
      <Link href="/elder/start">
        <User size={22} weight="fill" aria-hidden="true" />
        長者開始使用
      </Link>
      <Link href="/family/join">
        <UsersThree size={22} weight="fill" aria-hidden="true" />
        家屬登入／加入
      </Link>
      <Link href="/staff/sign-in">
        <FirstAidKit size={22} weight="fill" aria-hidden="true" />
        照服員登入
      </Link>
    </div>
  );
}

function FinalCta() {
  return (
    <section className={styles.finalCta} aria-labelledby="final-cta-title">
      <div className={styles.finalCopy}>
        <h2 id="final-cta-title">每一天的對話，都可以成為更好的陪伴。</h2>
        <p>從今天開始，讓小暖陪長輩說話，也讓重要資訊被更安心地理解。</p>
        <div className={styles.finalActions}>
          <Link href="/sign-in" className={styles.primaryAction}>開始使用</Link>
          <Link href="/sign-in" className={styles.darkSecondary}>登入</Link>
        </div>
        <p className={styles.finalTagline}>Voice-first · Confirmed Memory · Human Review</p>
      </div>
      <MascotHalo />
      <RoleLinks />
    </section>
  );
}

function CinematicFooter() {
  return (
    <footer className={styles.footer}>
      <Brand />
      <nav aria-label="法遵與其他連結">
        <Link href="/privacy">隱私權政策</Link>
        <Link href="/terms">服務條款</Link>
        <Link href="/data-rights">資料權利</Link>
        <Link href="/accessibility">無障礙聲明</Link>
      </nav>
      <small>本頁產品畫面皆為示意資料，不包含真實長者個人資料。</small>
    </footer>
  );
}

export function Landing() {
  return (
    <div className={styles.landing}>
      <CinematicHeader />
      <Hero />
      <div className={styles.desktopNarrative}>
        <VoiceStory />
        <MemoryStory />
        <RoleStory />
      </div>
      <MobileNarrative />
      <TrustSection />
      <FinalCta />
      <CinematicFooter />
    </div>
  );
}
