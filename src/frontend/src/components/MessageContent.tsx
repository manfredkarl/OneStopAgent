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

  if (parts.length === 1 && parts[0].type === 'text' && parts[0].value.trimStart().startsWith('flowchart')) {
    return <MermaidDiagram mermaidCode={parts[0].value} />;
  }

  return (
    <>
      {parts.map((part, i) =>
        part.type === 'mermaid' ? (
          <MermaidDiagram key={i} mermaidCode={part.value} />
        ) : (
          <ReactMarkdown
            key={i}
            components={{
              h1: (props) => <h1 className="text-xl font-bold mt-3 mb-2" {...props} />,
              h2: (props) => <h2 className="text-lg font-semibold mt-3 mb-1" {...props} />,
              h3: (props) => <h3 className="text-base font-semibold mt-2 mb-1" {...props} />,
              ul: (props) => <ul className="list-disc ml-5 mb-2 space-y-1" {...props} />,
              ol: (props) => <ol className="list-decimal ml-5 mb-2 space-y-1" {...props} />,
              li: (props) => <li className="text-sm" {...props} />,
              p: (props) => <p className="mb-2 text-sm leading-relaxed" {...props} />,
              strong: (props) => <strong className="font-semibold" {...props} />,
              a: (props) => <a className="text-[var(--accent)] underline" target="_blank" {...props} />,
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                return isInline ? (
                  <code className="bg-[var(--bg-secondary)] px-1.5 py-0.5 rounded text-xs font-mono" {...props}>{children}</code>
                ) : (
                  <pre className="bg-[var(--bg-secondary)] p-3 rounded-lg overflow-x-auto mb-2">
                    <code className="text-xs font-mono" {...props}>{children}</code>
                  </pre>
                );
              },
              table: (props) => (
                <div className="overflow-x-auto mb-2 rounded-lg border border-[var(--border)]">
                  <table className="w-full text-sm" {...props} />
                </div>
              ),
              th: (props) => <th className="bg-[var(--bg-secondary)] px-3 py-2 text-left font-semibold border-b border-[var(--border)]" {...props} />,
              td: (props) => <td className="px-3 py-2 border-b border-[var(--border)]" {...props} />,
            }}
          >
            {part.value}
          </ReactMarkdown>
        )
      )}
    </>
  );
}
