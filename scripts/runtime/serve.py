"""Provision an isolated demo catalog once, keep vectors current, serve the API/UI."""
import signal,subprocess,sys,time

def main():
    subprocess.run([sys.executable,'-m','scripts.runtime.provision'],check=True)
    worker=subprocess.Popen([sys.executable,'-m','app.product_indexing.commands','watch'])
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8600'])
    def stop(signum,frame):
        server.terminate();worker.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:return server.wait()
    finally:
        worker.terminate()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.kill();worker.wait()
if __name__=='__main__':raise SystemExit(main())
