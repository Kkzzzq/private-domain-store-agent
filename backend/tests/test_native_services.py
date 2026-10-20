from scripts import native_services


def test_native_stop_requires_path_and_creation_identity():
    executable = str(native_services.MYSQL)
    record = {"exe": executable, "started": "original"}
    assert native_services.owned_process(record, {"ExecutablePath": executable, "Started": "original"})
    assert not native_services.owned_process(record, {"ExecutablePath": executable, "Started": "recycled_pid"})
    assert not native_services.owned_process(record, {"ExecutablePath": "C:/Windows/notepad.exe", "Started": "original"})
    assert not native_services.owned_process(record, None)


def test_native_stop_does_not_touch_foreign_port(monkeypatch):
    record = {"pid": 123, "exe": str(native_services.MYSQL), "started": "original"}
    monkeypatch.setattr(native_services, "process_info", lambda pid: {"ExecutablePath": record["exe"], "Started": "original"})
    monkeypatch.setattr(native_services, "owns_port", lambda record, port: False)
    monkeypatch.setattr(native_services.pymysql, "connect", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not connect to foreign service")))
    monkeypatch.setattr(native_services.time, "sleep", lambda duration: None)
    native_services.stop({"mysql": record})


def test_native_mysql_adopts_only_its_monitor_child(monkeypatch):
    executable = str(native_services.MYSQL)
    state = {"mysql": {"pid": 1, "exe": executable, "started": "parent"}}
    processes = {1: {"ExecutablePath": executable, "Started": "parent", "ParentProcessId": 0},
                 2: {"ExecutablePath": executable, "Started": "child", "ParentProcessId": 1}}
    monkeypatch.setattr(native_services, "process_info", lambda pid: processes.get(pid))
    monkeypatch.setattr(native_services, "listener_pid", lambda port: 2)
    monkeypatch.setattr(native_services, "save", lambda state: None)
    native_services.adopt_listener("mysql", 13306, state)
    assert state["mysql"]["pid"] == 2 and state["mysql"]["launcher"]["pid"] == 1
    state = {"mysql": {"pid": 1, "exe": executable, "started": "parent"}}
    processes[2]["ParentProcessId"] = 99
    native_services.adopt_listener("mysql", 13306, state)
    assert state["mysql"]["pid"] == 1
