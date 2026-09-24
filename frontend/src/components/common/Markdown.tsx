// Safe Markdown rendering: raw HTML is never rendered, links open in a new tab
// without referrer, and only http(s)/mailto links are clickable.
import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  a: ({ href, children }) => {
    const safe = href && /^(https?:|mailto:)/i.test(href);
    return safe ? (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    );
  },
  img: ({ alt }) => <span className="text-muted">[image: {alt}]</span>,
};

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-nexus text-[0.93rem]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} skipHtml>
        {text}
      </ReactMarkdown>
    </div>
  );
});
