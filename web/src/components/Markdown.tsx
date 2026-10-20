import ReactMarkdown from "react-markdown";

/** Renders model-written markdown. react-markdown escapes raw HTML by default. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown text-sm leading-relaxed">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
