# Agentic RAG nhập khẩu Trung Quốc vào Việt Nam

MVP triển khai theo các file guide trong repo.

## Thiết Lập

```powershell
conda activate nlp
pip install -r requirements.txt
pip install -e .
```

## Cấu Hình Model

Copy `.env.example` thành `.env`, rồi điền API key:

```powershell
RAG_LLM_PROVIDER=openai
RAG_LLM_MODEL=gpt-4o-mini
RAG_OPENAI_API_KEY=sk-...

RAG_EMBEDDING_PROVIDER=sentence_transformers
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_ENABLE_DENSE_RETRIEVAL=true
RAG_ENABLE_HYBRID_RETRIEVAL=true
```

Nếu chưa có `RAG_OPENAI_API_KEY`, hệ thống không gọi LLM thật và sẽ dùng phần tổng hợp deterministic fallback.

## Pipeline Dữ Liệu

```powershell
python -m agentic_rag_import_vn.pipeline inventory
python -m agentic_rag_import_vn.pipeline extract-text
python -m agentic_rag_import_vn.pipeline build-chunks
python -m agentic_rag_import_vn.pipeline build-bm25
python -m agentic_rag_import_vn.pipeline build-dense
python -m agentic_rag_import_vn.pipeline build-vnaccs
```

Chạy toàn bộ pipeline MVP không bao gồm dense index:

```powershell
python -m agentic_rag_import_vn.pipeline all
```

Build dense index riêng sau khi BM25/chunks đã có:

```powershell
python -m agentic_rag_import_vn.pipeline build-dense
```

Lần đầu chạy `build-dense` có thể tải model `BAAI/bge-m3` từ Hugging Face. Nếu dense index chưa tồn tại, hybrid retrieval tự fallback về BM25.

Nếu chưa cài package ở chế độ editable, có thể tạm chạy bằng:

```powershell
$env:PYTHONPATH="$PWD\src"
```

## Kiểm Tra

```powershell
python -m pytest
python -m compileall src
```

## API

```powershell
uvicorn agentic_rag_import_vn.api.main:app --reload
```

Endpoint chính:

- `GET /health`
- `GET /sources/{document_id}`
- `GET /vnaccs/search?q=CNY`
- `POST /legal/search`
- `POST /chat`

MVP này ưu tiên provenance, dữ liệu có cấu trúc và cảnh báo phạm vi. Các mức thuế/HS chuyên sâu chỉ được trả khi dữ liệu đã được parse vào bảng tương ứng.
