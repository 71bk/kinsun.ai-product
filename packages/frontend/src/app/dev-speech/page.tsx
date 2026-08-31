import { notFound } from 'next/navigation';
import { DevSpeechView } from './DevSpeechView';

/**
 * Local speech check page — development only.
 *
 * This page opens the microphone. Outside development it must not exist, or it
 * becomes a way to capture an elder's voice that bypasses the consent and
 * ticket path the product UI goes through (AGENTS.md §4).
 *
 * The gate lives here, in a server component, rather than inside the view:
 * a client component decides what to render only after it is already running
 * in the browser, so it can withhold markup but not the decision. `notFound()`
 * on the server means the route answers 404 before the view is ever reached.
 *
 * The view's compiled chunk is still emitted under /_next/static -- verified,
 * not assumed. That is dead weight, not an opening: no route loads it, and the
 * page it belongs to returns 404, so there is no way to reach a live recorder.
 *
 * Fail closed: only the exact string `development` opens it. An unset or
 * unexpected NODE_ENV yields 404, which is the safe direction for a page whose
 * failure mode is recording someone.
 */
export default function DevSpeechPage() {
  if (process.env.NODE_ENV !== 'development') {
    notFound();
  }

  return <DevSpeechView />;
}
