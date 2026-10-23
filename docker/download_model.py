"""Bundle one exact BGE revision; no private catalog or credentials are needed."""
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-large-en-v1.5',revision='d4aa6901d3a41ba39fb536a557fa166f842b0e09',
    cache_dir='/opt/model-cache',allow_patterns=['*.json','*.txt','README.md','model.safetensors','1_Pooling/*'])
