import type { ReactNode } from "react";

const KEYWORD = /\b(STOP|HELP)\b/g;

function boldKeywords(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(KEYWORD)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push(text.slice(lastIndex, index));
    }
    parts.push(<strong key={`${match[1]}-${index}`}>{match[1]}</strong>);
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

interface TermsBodyProps {
  body: string;
}

export function TermsBody({ body }: TermsBodyProps) {
  return (
    <>
      {body.split("\n\n").map((paragraph) => (
        <p
          key={paragraph.slice(0, 48)}
          className="mb-4 text-slate-800 leading-relaxed"
        >
          {boldKeywords(paragraph)}
        </p>
      ))}
    </>
  );
}
