export function escapeMarkdown(value: string): string {
  return value.replace(/[\\`*_{}[\]()#+\-.!|]/g, "\\$&");
}

export function codeBlock(content?: string | null, language = ""): string {
  const body =
    content && content.length > 0 ? content : "No content available.";
  const fence = "~".repeat(
    Math.max(
      3,
      ...Array.from(body.matchAll(/~+/g), (match) => match[0].length + 1),
    ),
  );
  return fence + language + "\n" + body.replace(/\n?$/, "\n") + fence;
}

export function fieldLine(
  label: string,
  value?: string | number | null,
): string | null {
  if (value === undefined || value === null || value === "") return null;
  return `**${escapeMarkdown(label)}:** ${escapeMarkdown(String(value))}`;
}

export function bulletList(
  rows: [string, string | number | null | undefined][],
): string {
  const lines = rows
    .map(([label, value]) => fieldLine(label, value))
    .filter((line): line is string => Boolean(line))
    .map((line) => `- ${line}`);
  return lines.length > 0 ? lines.join("\n") : "_No values available._";
}
