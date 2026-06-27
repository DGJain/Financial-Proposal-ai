# Financial-Proposal-AI

**Secure Financial Document Intelligence & Proposal Generation Platform**

An enterprise AI platform that analyzes financial documents and generates consulting
proposals using a **private, air-gapped Retrieval-Augmented Generation (RAG)** architecture.
The system operates entirely within the enterprise boundary — **no internet access, no web
search, no external APIs** — retrieving only from approved internal repositories.

> Domain: Banking · Finance · Investment Consulting · Risk Assessment

---

## Key Features

- **Financial Document Intelligence** — ingest and analyze PDF, DOCX, PPTX, and image files
- **Private RAG** — retrieval restricted to approved internal corpora (no external retrieval)
- **Proposal Generation** — produces a structured advisory proposal grounded in the corpus
- **Side-by-Side Preview & Editing** — generated proposal (left) vs. editable proposal (right);
  text editing only, no structural/template changes
- **WYSIWYG Export** — export edited proposals to company-template **PDF / DOCX**
- **Query-First UX** — natural-language query auto-detects company, year, and sector;
  generates a style-only draft when no evidence is available (no hallucinated figures)
- **Metrics Dashboard** — OCR confidence, extraction quality, information-loss %, retrieval
  sources, repository contribution, embedded chunks, and processing time

---

## Architecture

```
User Query / Upload
      ↓
Document Processing  →  OCR & Extraction  →  Information-Loss Analysis
      ↓
Embedding Generation  →  Vector Storage (ChromaDB)
      ↓
Private RAG Retrieval  →  Proposal Generation
      ↓
Preview & Editing  →  Download PDF / DOCX
```

Built following **Clean Architecture** and **SOLID** principles with a modular,
security-first, async design.

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | Next.js, TypeScript, TailwindCSS, shadcn/ui, Framer Motion |
| **Backend** | FastAPI, Python, LangGraph |
| **Storage** | PostgreSQL, Redis, ChromaDB |
| **Doc Processing** | PyMuPDF, Docling, PaddleOCR, python-docx, python-pptx |
| **AI (local/offline)** | Ollama — `qwen2.5:3b` (free, offline, no API key) |
| **AI (dev/prototype)** | Claude (Anthropic) |

---

## Project Structure

```
financial-proposal-platform/
├── backend/            # FastAPI app, RAG pipeline, content engine
├── frontend/           # Next.js UI (preview, editing, dashboard)
├── packages/           # Shared types
├── knowledge_base/     # financial_documents / proposal_repository / template_repository
├── infra/              # Docker / Kubernetes manifests
├── scripts/            # Dev & seed scripts
├── docs/               # Architecture references (ARCHITECTURE_SUMMARY.md is source of truth)
├── test_data/          # Sample documents
└── docker-compose.yml
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and pnpm
- Docker (for PostgreSQL, Redis, ChromaDB)
- [Ollama](https://ollama.com/) with the `qwen2.5:3b` model pulled

### 1. Clone

```bash
git clone https://github.com/DGJain/Financial-Proposal-ai.git
cd Financial-Proposal-ai
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# edit the .env files with your local settings
```

### 3. Start infrastructure

```bash
docker-compose up -d   # PostgreSQL, Redis, ChromaDB
ollama pull qwen2.5:3b
```

### 4. Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# starts on http://localhost:8000
python serve_with_seed.py
```

### 5. Frontend

```bash
cd frontend
pnpm install
pnpm dev                         # http://localhost:3001
```

---

## Testing

```bash
cd backend
pytest                           # backend test suite
```

---

## Security Constraints

This platform is designed for **private enterprise deployment**:

- No internet access · No web search · No external APIs
- Retrieval restricted to approved internal repositories only
- Air-gap-friendly Kubernetes manifests (NetworkPolicies) in `infra/`

---

## License

This project is part of an academic dissertation. All rights reserved unless stated otherwise.
