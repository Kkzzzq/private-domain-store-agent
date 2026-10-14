import re
import unicodedata

from app.rag.chunker import chunk_text


def structured_chunks(text):
    text = unicodedata.normalize("NFKC", re.sub(r"<!--.*?-->", "", text, flags=re.S))
    seen = set()
    headings = []
    body = []
    chunks = []

    def flush():
        content = "\n".join(body).strip()
        if content:
            for part in chunk_text(content):
                chunks.append({"content": part, "heading_path": " > ".join(headings) or "正文"})
        body.clear()

    for paragraph in re.split(r"\n\s*\n", text.strip()):
        for line in paragraph.splitlines():
            heading = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
            if heading:
                flush()
                depth = len(heading.group(1))
                headings[:] = headings[:depth - 1] + [heading.group(2).strip()]
            else:
                normalized = line.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    body.append(normalized)
        if body:
            body.append("")
    flush()
    return chunks
