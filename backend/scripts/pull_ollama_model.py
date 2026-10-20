import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class PublicRegistryRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        parsed = urlparse(target)
        allowed = parsed.hostname == "registry.ollama.ai" or (parsed.hostname or "").endswith(".r2.cloudflarestorage.com")
        if parsed.scheme != "https" or not allowed:
            raise ValueError("模型下载仅允许官方HTTPS注册表及其CDN")
        for address in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(address[4][0]).is_global:
                raise ValueError("CDN解析结果不是公网地址，请修复DNS配置")
        return super().redirect_request(request, response, code, message, headers, target)


def digest_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def download_segment(opener, url, path, start, size, name):
    for attempt in range(6):
        try:
            completed = path.stat().st_size if path.exists() else 0
            if completed == size:
                return path
            if completed > size:
                path.unlink()
                completed = 0
            request = Request(url, headers={"Range": f"bytes={start + completed}-{start + size - 1}", "Accept-Encoding": "identity"})
            with opener.open(request, timeout=60) as response:
                expected_range = f"bytes {start + completed}-"
                if response.status != 206 or not response.headers.get("Content-Range", "").startswith(expected_range):
                    raise ValueError("官方CDN未按请求返回分段数据")
                with path.open("ab") as stream:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            if path.stat().st_size != size:
                raise ValueError("下载分段不完整")
            print(f"{name}: segment {path.suffix} verified size", flush=True)
            return path
        except Exception:
            if attempt == 5:
                raise RuntimeError("模型分段下载失败") from None
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--root", default="/root/.ollama/models")
    parser.add_argument("--proxy")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not re.fullmatch(r"(?:[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*(?::[a-zA-Z0-9._-]+)?", args.model):
        parser.error("仅支持注册表模型命名空间、模型名及tag")
    name, _, tag = args.model.partition(":")
    tag = tag or "latest"
    handlers = [PublicRegistryRedirect()]
    if args.proxy:
        handlers.append(ProxyHandler({"https": args.proxy}))
    opener = build_opener(*handlers)
    repository = name if "/" in name else "library/" + name
    base = "https://registry.ollama.ai/v2/" + repository
    with opener.open(Request(base + "/manifests/" + tag, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"}), timeout=30) as response:
        manifest_bytes = response.read()
    manifest = json.loads(manifest_bytes)
    root = Path(args.root)
    blobs = root / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    for descriptor in [manifest["config"], *manifest["layers"]]:
        digest = descriptor["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("不支持的模型校验格式")
        expected_size = descriptor["size"]
        target = blobs / digest.replace(":", "-")
        if target.exists() and target.stat().st_size == expected_size and digest_file(target) == digest[7:]:
            continue
        temporary = target.with_suffix(".download")
        if expected_size > 16 * 1024 * 1024:
            workers = max(1, min(args.workers, 16))
            segment_size = (expected_size + workers - 1) // workers
            if temporary.exists():
                with temporary.open("rb") as existing:
                    for index in range(workers):
                        segment = target.with_suffix(f".segment{index}")
                        start = index * segment_size
                        available = min(segment_size, temporary.stat().st_size - start)
                        if available > 0 and not segment.exists():
                            existing.seek(start)
                            with segment.open("wb") as output:
                                while available > 0:
                                    chunk = existing.read(min(1024 * 1024, available))
                                    if not chunk:
                                        break
                                    output.write(chunk)
                                    available -= len(chunk)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                tasks = [pool.submit(download_segment, opener, base + "/blobs/" + digest,
                                     target.with_suffix(f".segment{index}"), index * segment_size,
                                     min(segment_size, expected_size - index * segment_size), name)
                         for index in range(workers) if index * segment_size < expected_size]
                segments = [task.result() for task in tasks]
            with temporary.open("wb") as output:
                for segment in segments:
                    with segment.open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
            if digest_file(temporary) != digest[7:]:
                raise RuntimeError("模型整体SHA256不匹配，不发布")
            temporary.replace(target)
            for segment in segments:
                segment.unlink()
            continue
        for attempt in range(6):
            try:
                offset = temporary.stat().st_size if temporary.exists() else 0
                if offset >= expected_size:
                    if offset == expected_size and digest_file(temporary) == digest[7:]:
                        temporary.replace(target)
                        break
                    temporary.unlink()
                    offset = 0
                request = Request(base + "/blobs/" + digest, headers={"Range": f"bytes={offset}-"} if offset else {})
                with opener.open(request, timeout=60) as response:
                    if offset and response.status != 206:
                        offset = 0
                    with temporary.open("ab" if offset else "wb") as stream:
                        received = offset
                        next_progress = received + 32 * 1024 * 1024
                        while chunk := response.read(1024 * 1024):
                            stream.write(chunk)
                            received += len(chunk)
                            if received >= next_progress:
                                print(f"{name}: {received // 1048576}/{expected_size // 1048576} MiB", flush=True)
                                next_progress = received + 32 * 1024 * 1024
                if temporary.stat().st_size != expected_size or digest_file(temporary) != digest[7:]:
                    raise ValueError("模型大小或SHA256校验失败，不写入模型清单")
                temporary.replace(target)
                break
            except Exception as exc:
                print(f"{name}: attempt {attempt + 1}: {type(exc).__name__}", flush=True)
                if attempt == 5:
                    raise RuntimeError("官方模型下载失败，请检查网络") from None
                time.sleep(2)
    destination = root / "manifests" / "registry.ollama.ai" / repository / tag
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(manifest_bytes)
    print(f"{name}:{tag}: all blobs verified", flush=True)


if __name__ == "__main__":
    main()
