# Agentic RAG nhập khẩu Trung Quốc vào Việt Nam

MVP triển khai theo `GUIDE_AGENTIC_RAG_NHAP_KHAU_TRUNG_QUOC_VIET_NAM.md`.

## Thiết lập

```powershell
conda activate nlp
pip install -r requirements.txt
pip install -e .
```

## Pipeline dữ liệu

```powershell
python -m agentic_rag_import_vn.pipeline inventory
python -m agentic_rag_import_vn.pipeline extract-text
python -m agentic_rag_import_vn.pipeline build-chunks
python -m agentic_rag_import_vn.pipeline build-bm25
python -m agentic_rag_import_vn.pipeline build-vnaccs
```

Chạy toàn bộ:

```powershell
python -m agentic_rag_import_vn.pipeline all
```

Nếu chưa cài package ở chế độ editable, có thể tạm chạy bằng:

```powershell
$env:PYTHONPATH="$PWD\src"
```

## Kiểm tra

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
