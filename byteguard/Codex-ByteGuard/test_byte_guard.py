"""End-to-end local SSE tests. Uses an isolated home, no login or external model."""
import argparse, json, os, pathlib, subprocess, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def assistant(text):
    return {'type':'response.output_item.done','item':{'type':'message','role':'assistant','id':'msg_guard','content':[{'type':'output_text','text':text}]}}

def completed(index):
    return {'type':'response.completed','response':{'id':f'resp_{index}','usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}}

def scenario(binary, mode):
    maximum=300000
    records=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=json.dumps({'data':[]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
            request=json.loads(raw)
            # Local compaction uses Prompt::default() with no tools. Custom
            # providers omit internal request_kind metadata by default.
            compact=bool(records) and not request.get('tools')
            records.append({'bytes':len(raw),'compaction':compact})
            if compact:
                text='Summary: continue the original task after updating the plan.' if mode!='ineffective' else 'x'*maximum
                events=[assistant(text)]
            elif len(records)==1:
                # Push the next generation over 90%, while leaving compaction
                # headroom. Fake tokens remain low to exclude token-triggered rollover.
                growth=maximum*2 if mode=='huge_compaction' else maximum*9//10-len(raw)+10000
                events=[assistant('x'*max(1,growth)),{'type':'response.output_item.done','item':{'type':'function_call','call_id':'call_guard','name':'update_plan','arguments':json.dumps({'plan':[{'step':'Finish ByteGuard test','status':'in_progress'}]})}}]
            else:
                events=[assistant('BYTE_GUARD_CONTINUED')]
            events=[{'type':'response.created','response':{'id':f'resp_{len(records)}'}}]+events+[completed(len(records))]
            body=''.join('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n' for event in events).encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='codex-byteguard-test-') as directory:
            home=pathlib.Path(directory)
            (home/'config.toml').write_text(f'''model = "gpt-5.1-codex-max"
model_provider = "byteguard_mock"
model_reasoning_effort = "low"
[model_providers.byteguard_mock]
name = "ByteGuard local mock"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
''',encoding='utf-8')
            env=os.environ.copy();env['CODEX_HOME']=directory;env['CODEX_MAX_REQUEST_BYTES']=str(maximum)
            env['CODEX_BYTE_GUARD_STATUS_DIR']=str(home/'byteguard/status')
            if mode=='disabled':
                env.pop('CODEX_MAX_REQUEST_BYTES',None)
            for key in ('OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'):
                env.pop(key,None)
            env['NO_PROXY']='127.0.0.1,localhost';env['no_proxy']=env['NO_PROXY']
            result=subprocess.run([str(binary),'exec','--ephemeral','--skip-git-repo-check','--sandbox','read-only','--json','-C',directory,'Update the plan once, then finish the task.'],env=env,capture_output=True,timeout=120)
            output=result.stdout.decode('utf-8',errors='replace')+result.stderr.decode('utf-8',errors='replace')
            compactions=[r for r in records if r['compaction']]
            assert records, ('No requests reached local server',output[-3000:])
            status_files=list((home/'byteguard/status').glob('*.json'))
            if mode not in ('baseline','disabled'):
                assert len(status_files)==1,status_files
                status=json.loads(status_files[0].read_text(encoding='utf-8'))
                assert status['blocked_generation_checks']>=1,status
                assert status['maximum_bytes']==maximum,status
                assert status['compaction_checks']>=1,status
                assert 'input' not in status and 'tools' not in status,status
                if mode=='success':
                    assert status['request_bytes']==records[-1]['bytes'],status
                    assert not status['blocked'] and not status['compaction'],status
            elif mode=='disabled':
                assert not status_files,status_files
            if mode in ('baseline','disabled'):
                assert result.returncode==0,(result.returncode,output[-3000:])
                assert not compactions,records
                assert any(r['bytes']>maximum*9//10 for r in records),records
                return {'scenario':mode,'exit_code':result.returncode,'requests':records,'passed':True}
            assert all(r['bytes']<=(maximum if r['compaction'] else maximum*9//10) for r in records), records
            if mode=='success':
                assert result.returncode==0,(result.returncode,output[-3000:])
                assert '[ByteGuard] 开始自动压缩上下文' in output,output[-3000:]
                assert '[ByteGuard] 上下文自动压缩完成' in output,output[-3000:]
                assert len(compactions)==1,records
                assert 'BYTE_GUARD_CONTINUED' in output,output[-3000:]
                assert len(records)==3,records
            else:
                assert result.returncode!=0,output[-3000:]
                if mode=='huge_compaction':
                    assert '[ByteGuard] 自动压缩失败' in output,output[-3000:]
                assert len(compactions)==(0 if mode=='huge_compaction' else 1),records
                assert '[request-byte-budget]' in output,output[-3000:]
            return {'scenario':mode,'exit_code':result.returncode,'requests':records,'passed':True}
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('binary',type=pathlib.Path)
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    for mode in (('baseline',) if args.baseline else ('success','ineffective','huge_compaction','disabled')):
        print(json.dumps(scenario(args.binary.resolve(),mode)),flush=True)
