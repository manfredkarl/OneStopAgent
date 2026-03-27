import ReactMarkdown from 'react-markdown';
import MermaidDiagram from './MermaidDiagram';

interface Props {
  content: string;
}

export default function MessageContent({ content }: Props) {
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

  // Detect unfenced mermaid (raw flowchart code as entire message)
  if (
    parts.length === 1 &&
    parts[0].type === 'text' &&
    /^\s*(flowchart|graph)\s+(TD|TB|BT|RL|LR)\b/.test(parts[0].value) &&
    parts[0].value.includes('-->')
  ) {
    return <MermaidDiagram mermaidCode={parts[0].value} />;
  }

  return (
    <>
      {parts.map((part, i) =>
        part.type === 'mermaid' ? (
          <MermaidDiagram key={i} mermaidCode={part.value} />
        ) : (
          <div key={i} className="prose-content">
            <ReactMarkdown>{part.value}</ReactMarkdown>
          </div>
        )
      )}
    </>
  );
}
