"""Docker subprocess adapter, including Windows CLI from WSL; never pass secrets on argv."""
import os,subprocess,shutil
from pathlib import Path

def binary():
    explicit=os.environ.get('MARKET_DOCKER_BIN')
    if explicit:return explicit
    windows=Path('/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe')
    return str(windows) if windows.is_file() else shutil.which('docker') or 'docker'

def run(*args,input=None,check=True,capture=True):
    env=os.environ.copy()
    forwarded=[k for k in ['OLLAMA_API_KEY','LANGSMITH_API_KEY','LANGSMITH_ENDPOINT','LANGSMITH_PROJECT'] if k in env]
    if binary().endswith('.exe'):
        env['WSLENV']=':'.join(filter(None,[env.get('WSLENV',''),*forwarded]))
    return subprocess.run([binary(),*map(str,args)],input=input,text=True,capture_output=capture,check=check,env=env)
