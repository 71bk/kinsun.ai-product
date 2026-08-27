export interface ReplyCitation {
  label: string;
  href: string;
}

export interface PresentedReply {
  body: string;
  citations: ReplyCitation[];
}

const CITATION_MARKER = '\n\n引用來源：\n';
const MARKDOWN_CITATION = /^-\s+\[([^\]]+)]\((https?:\/\/[^\s)]+)\)$/;

function normalizeNewlines(message: string): string {
  return message.replace(/\r\n?/g, '\n');
}

export function presentCompanionReply(message: string): PresentedReply {
  const normalized = normalizeNewlines(message);
  const markerIndex = normalized.lastIndexOf(CITATION_MARKER);
  if (markerIndex < 0) {
    return { body: normalized, citations: [] };
  }

  const body = normalized.slice(0, markerIndex).trim();
  const citationLines = normalized
    .slice(markerIndex + CITATION_MARKER.length)
    .split('\n')
    .filter((line) => line.trim().length > 0);
  if (!body || citationLines.length === 0) {
    return { body: normalized, citations: [] };
  }

  const citations: ReplyCitation[] = [];
  for (const line of citationLines) {
    const match = line.match(MARKDOWN_CITATION);
    if (!match) {
      // Fail visibly: never hide source text that no longer matches the wire contract.
      return { body: normalized, citations: [] };
    }
    citations.push({ label: match[1], href: match[2] });
  }

  return { body, citations };
}

export function companionReplyForSpeech(message: string): string {
  const normalized = normalizeNewlines(message);
  const markerIndex = normalized.lastIndexOf(CITATION_MARKER);
  if (markerIndex < 0) return normalized.trim();

  const body = normalized.slice(0, markerIndex).trim();
  return body || normalized.trim();
}
