import html
import re

_CODE_BLOCK_RE = re.compile(r"```\w*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\w)\*([^*]+?)\*(?!\w)")
_HEADER_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

_OPEN_TAG_RE = re.compile(r"<(b|i|code|pre)>")
_CLOSE_TAG_RE = re.compile(r"</(b|i|code|pre)>")


def md_to_html(text: str) -> str:
    """Convert Markdown from LLM output to Telegram-compatible HTML."""
    # 1. Extract code blocks and inline code to protect them from escaping
    code_blocks: list[str] = []
    inline_codes: list[str] = []

    def _save_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    def _save_inline(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    text = _CODE_BLOCK_RE.sub(_save_block, text)
    text = _INLINE_CODE_RE.sub(_save_inline, text)

    # 2. Escape remaining HTML entities
    text = html.escape(text)

    # 3. Apply formatting conversions (on already-escaped text, no double-escape risk)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _HEADER_RE.sub(r"<b>\1</b>", text)

    # 4. Restore code blocks and inline code (content was already escaped before extraction — no,
    #    code content should be escaped independently)
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", f"<pre>{html.escape(block)}</pre>")

    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00INLINECODE{i}\x00", f"<code>{html.escape(code)}</code>")

    return text


def sanitize_html(text: str) -> str:
    """Close unclosed Telegram HTML tags in correct LIFO order."""
    stack: list[str] = []
    for m in re.finditer(r"<(/?)(b|i|code|pre)>", text):
        is_close = m.group(1) == "/"
        tag = m.group(2)
        if is_close:
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)

    # Close remaining open tags in reverse (LIFO) order
    for tag in reversed(stack):
        text += f"</{tag}>"

    return text
