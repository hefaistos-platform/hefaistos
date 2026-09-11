// Utility to sanitize AI-generated code blocks (Sigma/Pseudo)
// Strips Markdown code fences and lone backticks; trims whitespace.
export function sanitizeCodeFences(input: string | null | undefined): string {
  if (!input) return '';
  let text = String(input);
  // Remove triple-fenced blocks ```lang ... ``` to just content
  text = text.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, (_m, p1) => p1);
  // Remove any remaining triple backticks without language
  text = text.replace(/```([\s\S]*?)```/g, (_m, p1) => p1);
  // Remove stray single backticks
  text = text.replace(/`([^`]*)`/g, '$1');
  // Normalize CRLF and trim
  text = text.replace(/\r\n/g, '\n').trim();
  return text;
}
