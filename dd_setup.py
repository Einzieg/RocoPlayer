"""Installer-only DD setup and diagnostics. Never loads the DD DLL or sends input."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

SERVICE = 'ddhid63340'
RUNTIMES = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')


def inspect_driver():
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    adv.OpenSCManagerW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    adv.OpenSCManagerW.restype = wintypes.HANDLE
    adv.OpenServiceW.argtypes = (wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD)
    adv.OpenServiceW.restype = wintypes.HANDLE
    adv.CloseServiceHandle.argtypes = (wintypes.HANDLE,)
    adv.CloseServiceHandle.restype = wintypes.BOOL
    adv.QueryServiceStatus.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    adv.QueryServiceStatus.restype = wintypes.BOOL
    manager = adv.OpenSCManagerW(None, None, 1)
    if not manager:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = None
    try:
        handle = adv.OpenServiceW(manager, SERVICE, 4)
        if not handle:
            error = ctypes.get_last_error()
            if error != 1060:
                raise ctypes.WinError(error)
            state = {'registered': False, 'state': None}
        else:
            status = (wintypes.DWORD * 7)()
            if not adv.QueryServiceStatus(handle, ctypes.byref(status)):
                raise ctypes.WinError(ctypes.get_last_error())
            state = {'registered': True, 'state': status[1], 'win32_exit': status[3],
                     'service_exit': status[4]}
    finally:
        if handle:
            adv.CloseServiceHandle(handle)
        adv.CloseServiceHandle(manager)

    cfg = ctypes.WinDLL('cfgmgr32', use_last_error=True)
    cfg.CM_Get_Device_ID_List_SizeW.argtypes = (ctypes.POINTER(wintypes.ULONG), wintypes.LPCWSTR, wintypes.ULONG)
    cfg.CM_Get_Device_ID_ListW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG)
    cfg.CM_Locate_DevNodeW.argtypes = (ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.ULONG)
    cfg.CM_Get_DevNode_Status.argtypes = (ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG), wintypes.DWORD, wintypes.ULONG)
    for name in ('CM_Get_Device_ID_List_SizeW', 'CM_Get_Device_ID_ListW', 'CM_Locate_DevNodeW', 'CM_Get_DevNode_Status'):
        getattr(cfg, name).restype = wintypes.ULONG
    flags = 0x2 | 0x100  # Service filter, present devices only.
    for _ in range(3):
        size = wintypes.ULONG()
        result = cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), SERVICE, flags)
        if result:
            raise RuntimeError(f'CM_Get_Device_ID_List_SizeW: {result:#x}')
        buffer = ctypes.create_unicode_buffer(max(size.value, 2))
        result = cfg.CM_Get_Device_ID_ListW(SERVICE, buffer, len(buffer), flags)
        if result != 0x1A:  # CR_BUFFER_SMALL: devices changed between calls.
            break
    if result:
        raise RuntimeError(f'CM_Get_Device_ID_ListW: {result:#x}')
    devices = []
    for identity in buffer[:].split('\0'):
        if not identity:
            continue
        node, status, problem = wintypes.DWORD(), wintypes.ULONG(), wintypes.ULONG()
        result = cfg.CM_Locate_DevNodeW(ctypes.byref(node), ctypes.create_unicode_buffer(identity), 0)
        if not result:
            result = cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), node, 0)
        devices.append({'id': identity, 'query_result': result, 'status': status.value,
                        'problem': problem.value, 'started': bool(status.value & 8)})
    state['devices'] = devices
    return state


def healthy(state):
    devices = state.get('devices', [])
    return bool(state.get('registered') and state.get('state') == 4 and devices and
                all(d['query_result'] == 0 and d['problem'] == 0 and d['started'] for d in devices))


def run_setup(driver, logs, *, inspect_only=False, inspect=inspect_driver, launch=subprocess.Popen, sleep=time.sleep):
    logs.mkdir(parents=True, exist_ok=True)
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    events = logs / f'dd-{session}.jsonl'
    output = logs / f'dd-{session}-vendor.log'
    pending = logs / 'dd-install-pending.json'

    def record(event, **fields):
        with events.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'event': event,
                                     **fields}, ensure_ascii=False) + '\n')

    def finish(code, reason):
        record('result', code=code, reason=reason)
        print(f'DD setup: {reason}. Log: {events}', flush=True)
        return code

    try:
        record('start', driver_directory=str(driver), vendor_log=str(output))
        before = inspect()
        record('before', **before)
        if inspect_only:
            return finish(0 if healthy(before) else 2, 'read_only_inspection')
        if healthy(before):
            return finish(0, 'service_and_pnp_ready_not_input_tested')
        if before['registered'] or before['devices']:
            return finish(2, 'existing_driver_unhealthy_reinstallation_skipped')
        # A timed-out installer may still be changing the device. Never overlap it.
        if pending.exists():
            return finish(2, 'previous_install_timed_out_manual_review_required')
        missing = [name for name in (*RUNTIMES, 'ddc.exe', 'ddhid63340.inf', 'ddhid63340.sys', 'ddhid63340.cat')
                   if not (driver / name).is_file()]
        if missing:
            return finish(2, 'missing_files: ' + ', '.join(missing))
        record('files', sha256={name: hashlib.sha256((driver / name).read_bytes()).hexdigest()
                               for name in (*RUNTIMES, 'ddc.exe', 'ddhid63340.inf', 'ddhid63340.sys', 'ddhid63340.cat')})
        with output.open('wb') as stream:
            process = launch([str(driver / 'ddc.exe')], cwd=str(driver), stdin=subprocess.DEVNULL,
                             stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            record('vendor_started', pid=process.pid)
            try:
                code = process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                pending.write_text(json.dumps({'pid': process.pid, 'log': str(events)}, ensure_ascii=False), encoding='utf-8')
                # Do not kill a vendor process in the middle of device installation.
                return finish(3010, 'vendor_timeout_do_not_rerun_restart_and_review')
        record('vendor_exit', code=code)
        after = inspect()
        record('after', attempt=0, **after)
        if code not in (0, 3010):
            return finish(2, f'vendor_failed: {code}')
        if code == 3010:
            return finish(3010, 'vendor_requested_restart')
        for attempt in range(1, 11):
            if healthy(after):
                return finish(0, 'service_and_pnp_ready_not_input_tested')
            sleep(1)
            after = inspect()
            record('after', attempt=attempt, **after)
        return finish(2, 'service_or_pnp_not_ready_after_install')
    except Exception as exc:
        record('exception', type=type(exc).__name__, message=str(exc))
        return finish(2, 'setup_or_state_query_failed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dd-setup', action='store_true', required=True)
    parser.add_argument('--driver-dir', type=Path, required=True)
    parser.add_argument('--log-dir', type=Path, required=True)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    try:
        return run_setup(args.driver_dir.resolve(), args.log_dir.resolve(), inspect_only=args.inspect_only)
    except Exception as exc:
        # In particular, an unwritable log directory must prevent installation.
        print(f'DD setup aborted before installation: {exc}', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
