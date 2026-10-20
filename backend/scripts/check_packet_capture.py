import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tshark", default="C:/Program Files/Wireshark/tshark.exe")
    parser.add_argument("--report", default="data/acceptance/wireshark-installation.json")
    parser.add_argument("--api-url")
    args = parser.parse_args()
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    capture = output.parent / ("loopback-probe-" + uuid.uuid4().hex + ".pcapng")
    report = {"scope": "real_loopback_http_installation_probe_not_business_or_model_acceptance", "passed": False}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = None
    server = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"status":"ok","probe":"capture-installation"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, format, *values):
            pass

    def run(arguments):
        return subprocess.run([args.tshark] + arguments, capture_output=True, text=True, timeout=20, creationflags=flags, check=True).stdout

    try:
        report["version"] = run(["--version"]).splitlines()[0]
        interfaces = run(["-D"])
        interface = next(line.split(". ", 1)[1].split(" (", 1)[0] for line in interfaces.splitlines() if "NPF_Loopback" in line)
        if args.api_url:
            target = urlparse(args.api_url)
            if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost") or not target.port or target.port < 18000 or target.path != "/api/v1/ready" or target.username or target.password or target.query or target.fragment:
                raise ValueError("仅支持独立回环端口的无认证ready探针")
            port = target.port
            path = target.path
            report["scope"] = "real_fastapi_readiness_loopback_capture_no_authentication_headers"
        else:
            server = HTTPServer(("127.0.0.1", 0), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            port = server.server_address[1]
            path = "/health"
        report.update({"interface": interface, "capture_filter": f"tcp port {port}", "capture": str(capture)})
        process = subprocess.Popen([args.tshark, "-i", interface, "-f", f"tcp port {port}", "-a", "duration:5", "-w", str(capture), "-q"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        time.sleep(1.5)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            report["probe_status"] = response.status
            response.read()
        finally:
            connection.close()
        process.communicate(timeout=15)
        if process.returncode:
            raise RuntimeError("capture_failed")
        frames = run(["-r", str(capture), "-T", "fields", "-e", "frame.number"])
        http_fields = run(["-r", str(capture), "-d", f"tcp.port=={port},http", "-Y", "http", "-T", "fields", "-e", "http.request.method", "-e", "http.response.code"])
        report["packet_count"] = len(frames.splitlines())
        report["http_get_observed"] = "GET" in http_fields
        report["http_200_observed"] = "200" in http_fields
        report["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
        report["passed"] = report["packet_count"] > 0 and report["http_get_observed"] and report["http_200_observed"] and report["probe_status"] == 200
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
        if server is not None:
            server.shutdown()
            server.server_close()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
