import { useMemo } from 'react';
import { marked } from 'marked';
import MermaidDiagram from './MermaidDiagram';

interface Props {
  content: string;
}

// Configure marked for safe rendering
marked.setOptions({ breaks: true, gfm: true });

// Sections that should be collapsible — matched by heading text
const COLLAPSIBLE_HEADINGS = [
  'assumptions', 'assumption', 'value drivers contributing',
  'methodology', 'sources', 'references',
];

function wrapCollapsibleSections(html: string): string {
  // Find h3 headings that match collapsible patterns and wrap their content
  // in <details><summary> until the next heading of equal or higher level
  return html.replace(
    /(<h[23][^>]*>)(.*?)(<\/h[23]>)([\s\S]*?)(?=<h[1-3]|$)/gi,
    (_match, openTag, headingText, closeTag, content) => {
      const text = headingText.replace(/<[^>]*>/g, '').trim().toLowerCase();
      if (COLLAPSIBLE_HEADINGS.some(h => text.includes(h)) && content.trim().length > 50) {
        return `<details class="collapsible-section"><summary class="collapsible-summary">${headingText}</summary><div class="collapsible-body">${content}</div></details>`;
      }
      return `${openTag}${headingText}${closeTag}${content}`;
    }
  );
}

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
            dangerouslySetInnerHTML={{ __html: wrapCollapsibleSections(marked.parse(part.value) as string) }}
          />
        )
      )}
    </>
  );
}
