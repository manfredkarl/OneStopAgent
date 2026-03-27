import { useMemo } from 'react';
import { marked } from 'marked';
import MermaidDiagram from './MermaidDiagram';

interface Props {
  content: string;
}

// Configure marked for safe rendering
marked.setOptions({ breaks: true, gfm: true });

export default function MessageContent({ content }: Props) {
  const rendered = useMemo(() => {
    // Split out mermaid blocks before markdown processing
    const parts: Array<{ type: 'text' | 'mermaid'; value: string }> = [];
    const regex = /```mermaid\s*\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ type: 'text', value: content.slice(lastIndex, match.index) });
      }
      parts.push({ type: 'mermaid', value: match[1].trim() });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < content.length) {
      parts.push({ type: 'text', value: content.slice(lastIndex) });
    }

    // Detect unfenced mermaid
    if (
      parts.length === 1 &&
      parts[0].type === 'text' &&
      /^\s*(flowchart|graph)\s+(TD|TB|BT|RL|LR)\b/.test(parts[0].value) &&
      parts[0].value.includes('-->')
    ) {
      return [{ type: 'mermaid' as const, value: parts[0].value }];
    }

    return parts;
  }, [content]);

  return (
    <>
      {rendered.map((part, i) =>
        part.type === 'mermaid' ? (
          <MermaidDiagram key={i} mermaidCode={part.value} />
        ) : (
          <div
            key={i}
            className="prose-content"
            dangerouslySetInnerHTML={{ __html: marked.parse(part.value) as string }}
          />
        )
      )}
    </>
  );
}
