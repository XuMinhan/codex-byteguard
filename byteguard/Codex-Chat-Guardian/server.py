"""Read-only local Codex chat size monitor. Python standard library only."""
import argparse, datetime, json, os, pathlib, sqlite3, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
CACHE = {}
LOCK = threading.Lock()

def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def scan_byteguard(home, project=None):
    project = project or HERE.parent / 'Codex-ByteGuard'
    directory = pathlib.Path(os.environ.get('CODEX_BYTE_GUARD_STATUS_DIR', str(home / 'byteguard/status')))
    latest = {}
    errors = 0
    for path in directory.glob('*.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('schema') != 1 or not isinstance(record.get('thread_id'), str):
                continue
            for field in ('updated_at', 'request_bytes', 'limit_bytes', 'maximum_bytes', 'generation_limit_bytes'):
                if not isinstance(record.get(field), (int, float)) or record[field] < 0:
                    raise ValueError('invalid status')
            record['process_alive'] = process_alive(record.get('pid'))
            previous = latest.get(record['thread_id'])
            if previous is None or record['updated_at'] > previous['updated_at']:
                latest[record['thread_id']] = record
        except (OSError, ValueError, TypeError):
            errors += 1
    binary = project / ('bin/codex.exe' if os.name == 'nt' else 'bin/codex')
    return dict(project_path=str(project.resolve()), installed=binary.is_file(),
                binary_modified=binary.stat().st_mtime if binary.is_file() else None,
                status_directory=str(directory), records=sorted(latest.values(), key=lambda x:x['updated_at'], reverse=True),
                unreadable=errors)

def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))

def inspect_rollout(path):
    stat = path.stat()
    key = (stat.st_size, stat.st_mtime_ns)
    old = CACHE.get(str(path))
    if old and old[0] == key:
        return dict(old[1])
    total = active = count = active_count = compactions = malformed = 0
    active_known = True
    tokens = window = None
    gateway403 = False
    running = False
    thread_id = ''
    source_name = cwd = ''
    with path.open(encoding='utf-8', errors='replace') as source:
        for line in source:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                malformed += 1
                continue
            payload = event.get('payload') or {}
            kind = event.get('type')
            if kind == 'event_msg':
                if payload.get('type') in ('task_started', 'turn_started'):
                    running = True
                elif payload.get('type') in ('task_complete', 'turn_complete', 'turn_aborted', 'task_aborted'):
                    running = False
            if kind == 'session_meta':
                thread_id = payload.get('id', '')
                source_name = payload.get('source', '')
                cwd = payload.get('cwd', '')
            if kind == 'response_item':
                size = encoded_size(payload)
                total += size
                active += size
                count += 1
                active_count += 1
            if kind == 'compacted':
                compactions += 1
                history = payload.get('replacement_history')
                if isinstance(history, list):
                    active = sum(encoded_size(item) for item in history)
                    active_count = len(history)
                    active_known = True
                else:
                    active = 0
                    active_count = 0
                    active_known = False
            if payload.get('type') == 'token_count' and payload.get('info'):
                info = payload['info']
                tokens = (info.get('last_token_usage') or {}).get('input_tokens')
                window = info.get('model_context_window')
            if payload.get('type') in ('task_complete', 'error'):
                error = str(payload.get('error', payload.get('message', '')))
                if '403' in error and ('HIS Proxy' in error or 'NetentSec' in error):
                    gateway403 = True
    result = dict(id=thread_id, source=source_name, cwd=cwd, bytes=total + max(count - 1, 0) + 2,
                  active_bytes=active + max(active_count - 1, 0) + 2 if active_known else None,
                  compactions=compactions, items=count, tokens=tokens, window=window,
                  gateway403=gateway403, running=running, malformed=malformed, file_bytes=stat.st_size,
                  modified=stat.st_mtime)
    CACHE[str(path)] = (key, result)
    return dict(result)

def scan(home, project=None):
    byteguard = scan_byteguard(home, project)
    guard_by_id = {record['thread_id']:record for record in byteguard['records']}
    metadata = {}
    warnings = []
    db = home / 'state_5.sqlite'
    if db.exists():
        try:
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as connection:
                connection.row_factory = sqlite3.Row
                for row in connection.execute('SELECT id,title,archived,updated_at,thread_source,source FROM threads'):
                    metadata[row['id']] = dict(row)
        except sqlite3.Error as error:
            warnings.append('聊天标题数据库暂不可读：' + type(error).__name__)
    index = home / 'session_index.jsonl'
    if index.exists():
        for line in index.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                entry = json.loads(line)
                title = entry.get('thread_name', '')
                if title and '\ufffd' not in title:
                    metadata.setdefault(entry['id'], {})['display_title'] = title
            except (ValueError, KeyError):
                continue
    byteguard['records'] = [record for record in byteguard['records']
                           if metadata.get(record['thread_id'], {}).get('thread_source') != 'guardian_review'
                           and '"guardian"' not in metadata.get(record['thread_id'], {}).get('source', '')]
    rows = []
    for folder in ('sessions', 'archived_sessions'):
        directory = home / folder
        if not directory.exists():
            continue
        for path in directory.rglob('*.jsonl'):
            try:
                row = inspect_rollout(path)
                if not row['id']:
                    continue
                meta = metadata.get(row['id'], {})
                if meta.get('thread_source') == 'guardian_review' or '"guardian"' in meta.get('source', ''):
                    continue
                title = meta.get('display_title') or (meta.get('title') or row['id']).splitlines()[0]
                if len(title) > 100:
                    title = title[:77] + '…'
                row.update(title=title,
                           byteguard=guard_by_id.get(row['id']),
                           archived=bool(meta.get('archived', folder == 'archived_sessions')))
                row['modified'] = max(row['modified'], meta.get('updated_at', 0))
                rows.append(row)
            except (OSError, ValueError, TypeError) as error:
                warnings.append(path.name + '：' + type(error).__name__)
    unique = {}
    for row in rows:
        if row['id'] not in unique or row['modified'] > unique[row['id']]['modified']:
            unique[row['id']] = row
    return dict(scanned_at=datetime.datetime.now().astimezone().isoformat(),
                chats=list(unique.values()), warnings=warnings, byteguard=byteguard,
                metric='UTF-8 compact JSON of response_item payloads; not HTTP request size')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Reject other Host headers to avoid exposing local metadata via DNS rebinding.
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403)
            return
        route = self.path.split('?', 1)[0]
        try:
            if route == '/api/chats':
                with LOCK:
                    body = json.dumps(scan(self.server.codex_home, self.server.byteguard_project), ensure_ascii=False).encode('utf-8')
                mime = 'application/json; charset=utf-8'
            elif route in ('/', '/index.html'):
                body = (HERE / 'index.html').read_bytes()
                mime = 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_error(500, 'Local scan failed')

    def log_message(self, *_):
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--codex-home', type=pathlib.Path, default=pathlib.Path(os.environ.get('CODEX_HOME', str(pathlib.Path.home() / '.codex'))))
    parser.add_argument('--byteguard-project', type=pathlib.Path, default=HERE.parent / 'Codex-ByteGuard')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.codex_home = args.codex_home.resolve()
    server.byteguard_project = args.byteguard_project.resolve()
    print(f'Chat monitor: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
