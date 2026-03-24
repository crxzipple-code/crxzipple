import MarkdownIt from "markdown-it";

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: false,
});

const defaultLinkOpen =
  markdown.renderer.rules.link_open ??
  ((tokens: any, idx: number, options: any, _env: any, self: any) =>
    self.renderToken(tokens, idx, options));

markdown.renderer.rules.link_open = (
  tokens: any,
  idx: number,
  options: any,
  env: any,
  self: any,
) => {
  const token = tokens[idx];

  token.attrSet("target", "_blank");
  token.attrSet("rel", "noreferrer noopener");

  return defaultLinkOpen(tokens, idx, options, env, self);
};

export function renderMarkdown(source: string): string {
  return markdown.render(source);
}
