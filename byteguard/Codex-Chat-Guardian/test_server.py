"""Monitor checks using synthetic local data only; never reads the user's Codex home."""
import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('monitor', pathlib.Path(__file__).with_name('server.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_rollout_compaction_estimates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'synthetic.jsonl'
            events = [
                {'type': 'session_meta', 'payload': {'id': 'test-thread', 'source': 'cli'}},
                {'type': 'response_item', 'payload': {'text': '中文'}},
                {'type': 'compacted', 'payload': {'replacement_history': [{'text': '摘要'}]}},
            ]
            path.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
            result = monitor.inspect_rollout(path)
            self.assertEqual(result['compactions'], 1)
            self.assertEqual(result['active_bytes'], monitor.encoded_size({'text': '摘要'}) + 2)

    def test_http_routes_and_rebinding_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            server = monitor.ThreadingHTTPServer(('127.0.0.1', 0), monitor.Handler)
            server.codex_home = pathlib.Path(directory)
            server.byteguard_project = pathlib.Path(directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with opener.open(base + '/api/chats') as response:
                    self.assertEqual(json.load(response)['chats'], [])
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
                for route, headers, code in [('/', {'Host': 'attacker.example'}, 403), ('/../auth.json', {}, 404)]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        opener.open(urllib.request.Request(base + route, headers=headers))
                    self.assertEqual(caught.exception.code, code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
