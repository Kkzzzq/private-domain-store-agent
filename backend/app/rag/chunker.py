def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if overlap >= size:
        raise ValueError("overlap 必须小于 size")
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = end - overlap
    return chunks
