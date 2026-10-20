import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pymysql
import redis


ROOT = Path(__file__).resolve().parents[1] / "data/acceptance/native"
STATE = ROOT / "processes.json"
MYSQL = ROOT / "mysql-runtime/mysql-8.4.11-winx64/bin/mysqld.exe"
REDIS = ROOT / "redis-runtime/Redis-8.10.2-Windows-x64-cygwin/redis-server.exe"


def process_info(pid):
    command = f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | Select-Object ExecutablePath,ParentProcessId,@{{Name='Started';Expression={{$_.CreationDate.ToUniversalTime().ToString('o')}}}} | ConvertTo-Json -Compress"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, encoding="utf-8", timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(completed.stdout) if completed.stdout.strip() else None


def owned_process(record, info):
    if not info or not info.get("ExecutablePath"):
        return False
    executable = Path(record["exe"]).resolve()
    return (executable.is_relative_to(ROOT.resolve()) and str(executable).casefold() == str(Path(info["ExecutablePath"]).resolve()).casefold()
            and record["started"] == info["Started"])


def available(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return False
    except OSError:
        return True


def listener_pid(port):
    command = f"Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    values = {int(value) for value in completed.stdout.split() if value.isdigit()}
    return values.pop() if len(values) == 1 else None


def owns_port(record, port):
    return listener_pid(port) == record["pid"]


def adopt_listener(name, port, state):
    record = state.get(name)
    if not record or not owned_process(record, process_info(record["pid"])):
        return
    pid = listener_pid(port)
    if pid is None or pid == record["pid"]:
        return
    info = process_info(pid)
    if not info or str(Path(info["ExecutablePath"]).resolve()).casefold() != str(Path(record["exe"]).resolve()).casefold():
        return
    ancestor = info
    for _ in range(8):
        if ancestor.get("ParentProcessId") == record["pid"]:
            state[name] = {"pid": pid, "exe": record["exe"], "started": info["Started"], "launcher": record}
            save(state)
            return
        ancestor = process_info(ancestor.get("ParentProcessId", 0))
        if not ancestor:
            return


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def launch(name, executable, arguments, directory, state):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "stdout.log").open("ab") as stdout, (directory / "stderr.log").open("ab") as stderr:
        process = subprocess.Popen([str(executable)] + arguments, cwd=directory, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    info = process_info(process.pid)
    if not info:
        raise RuntimeError(f"{name}进程未能启动，请检查独立日志")
    state[name] = {"pid": process.pid, "exe": str(executable), "started": info["Started"]}
    save(state)
    return process


def start(state):
    if not MYSQL.is_file() or not REDIS.is_file():
        raise RuntimeError("请先按手册下载并解压便携MySQL和Redis")
    if all(state.get(name) and owned_process(state[name], process_info(state[name]["pid"])) and owns_port(state[name], port) for name, port in (("mysql", 13306), ("redis", 16379))):
        return
    for name, port in (("mysql", 13306), ("redis", 16379)):
        if not available(port):
            raise RuntimeError(f"端口{port}已被占用，拒绝启动或接管其他服务；可先运行status")
    data = ROOT / "mysql-data"
    config = ROOT / "mysql.ini"
    config.write_text("[mysqld]\nbasedir=" + MYSQL.parents[1].as_posix() + "\ndatadir=" + data.as_posix()
                      + "\nbind-address=127.0.0.1\nport=13306\nmysqlx=0\nmax_connections=30\ninnodb_buffer_pool_size=64M\nperformance_schema=OFF\ncharacter-set-server=utf8mb4\n", encoding="utf-8")
    if not data.exists():
        initialized = subprocess.run([str(MYSQL), "--defaults-file=" + str(config), "--initialize-insecure"], capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        (ROOT / "mysql-initialize.log").write_bytes(initialized.stderr)
        if initialized.returncode:
            raise RuntimeError("MySQL独立数据目录初始化失败；不自动删除目录，请检查日志")
        state["mysql_bootstrapped"] = False
        save(state)
    process = launch("mysql", MYSQL, ["--defaults-file=" + str(config), "--console"], ROOT / "mysql-process", state)
    connection = None
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("MySQL进程退出，请检查mysql-process日志")
        try:
            connection = pymysql.connect(host="127.0.0.1", port=13306, user="root", password="acceptance-root-local-only" if state.get("mysql_bootstrapped") else "", autocommit=True)
            break
        except pymysql.MySQLError:
            time.sleep(1)
    if connection is None:
        raise RuntimeError("MySQL未就绪；保留进程与日志，不强制清空数据")
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE IF NOT EXISTS private_store_acceptance CHARACTER SET utf8mb4")
            cursor.execute("CREATE USER IF NOT EXISTS 'acceptance'@'127.0.0.1' IDENTIFIED BY 'acceptance-local-only'")
            cursor.execute("GRANT ALL ON private_store_acceptance.* TO 'acceptance'@'127.0.0.1'")
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY 'acceptance-root-local-only'")
    state["mysql_bootstrapped"] = True
    save(state)
    launch("redis", REDIS, ["--bind", "127.0.0.1", "--port", "16379", "--protected-mode", "yes", "--appendonly", "yes", "--dir", ".", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction"], ROOT / "redis-data", state)
    client = redis.Redis(host="127.0.0.1", port=16379, socket_timeout=2)
    for _ in range(30):
        try:
            if client.ping():
                return
        except redis.RedisError:
            time.sleep(1)
    raise RuntimeError("Redis未就绪，请检查redis-data日志")


def stop(state):
    for name in ("redis", "mysql"):
        record = state.get(name)
        if not record or not owned_process(record, process_info(record["pid"])) or not owns_port(record, 16379 if name == "redis" else 13306):
            continue
        if name == "redis":
            redis.Redis(host="127.0.0.1", port=16379, socket_timeout=5).shutdown(save=True)
        else:
            connection = pymysql.connect(host="127.0.0.1", port=13306, user="root", password="acceptance-root-local-only", autocommit=True)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SHUTDOWN")
            finally:
                connection.close()
    time.sleep(1)


def provision_demo(state):
    record = state.get("mysql")
    if not record or not owned_process(record, process_info(record["pid"])) or not owns_port(record, 13306):
        raise RuntimeError("只允许在本脚本创建的独立MySQL上准备演示库")
    with pymysql.connect(host="127.0.0.1", port=13306, user="root", password="acceptance-root-local-only", autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE IF NOT EXISTS private_store_demo CHARACTER SET utf8mb4")
            cursor.execute("CREATE USER IF NOT EXISTS 'store_demo'@'127.0.0.1' IDENTIFIED BY 'store-demo-local-only'")
            cursor.execute("GRANT ALL ON private_store_demo.* TO 'store_demo'@'127.0.0.1'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "status", "stop", "provision-demo"])
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("此脚本仅用于Windows隔离验收")
    ROOT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    try:
        for name, port in (("mysql", 13306), ("redis", 16379)):
            adopt_listener(name, port, state)
        if args.action == "start":
            start(state)
        elif args.action == "stop":
            stop(state)
        elif args.action == "provision-demo":
            provision_demo(state)
        result = {name: {"owned_process_running": bool(state.get(name) and owned_process(state[name], process_info(state[name]["pid"]))), "port_open": not available(port)} for name, port in (("mysql", 13306), ("redis", 16379))}
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__, "detail": str(error) if isinstance(error, RuntimeError) else "请检查独立服务日志；未清空数据或停止其他进程"}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
