# 常驻一个 `waku mcp serve`（stdio JSON-RPC），中转里直接 tools/call，省掉每次起 CLI 的开销
import json, subprocess, threading, itertools, time


class WakuMCP:
    def __init__(self):
        self.p = subprocess.Popen(['waku', 'mcp', 'serve'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.ids = itertools.count(1); self.waiters = {}; self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()
        self.call_raw('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'magnus-voice', 'version': '1'}})
        self.p.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n'); self.p.stdin.flush()

    def _reader(self):
        for line in self.p.stdout:
            try: m = json.loads(line)
            except Exception: continue
            w = self.waiters.pop(m.get('id'), None)
            if w: w[1].update(m); w[0].set()

    def call_raw(self, method, params, timeout=120):
        i = next(self.ids); ev = threading.Event(); box = {}
        self.waiters[i] = (ev, box)
        with self.lock:
            self.p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}) + '\n'); self.p.stdin.flush()
        if not ev.wait(timeout): raise TimeoutError(method)
        if 'error' in box: raise RuntimeError(box['error'])
        return box['result']

    def tool(self, name, args, timeout=120):
        r = self.call_raw('tools/call', {'name': name, 'arguments': args}, timeout)
        txt = ''.join(c.get('text', '') for c in r.get('content', []))
        try: return json.loads(txt)
        except Exception: return {'raw': txt, 'isError': r.get('isError')}


if __name__ == '__main__':
    m = WakuMCP()
    tools = m.call_raw('tools/list', {})
    print([t['name'] for t in tools['tools']][:40])
    sch = [t for t in tools['tools'] if t['name'] == 'multimodal_run_model'][0]['inputSchema']
    print(json.dumps(sch)[:1500])
