# PROJECT CONTEXT

## Project Name

Secure Financial Document Intelligence and Proposal Generation Platform

---

## Project Goal

Build a secure enterprise AI platform that analyzes financial documents and generates consulting proposals using a private Retrieval-Augmented Generation (RAG) architecture.

The platform must operate entirely within the enterprise boundary and must not use external web search or internet-based retrieval.

---

## Domain

* Banking
* Finance
* Investment Consulting
* Risk Assessment

---

## Security Constraints

* No internet access
* No web search
* No external APIs
* Private enterprise deployment
* Retrieval only from approved repositories

---

## Knowledge Sources

### Financial Documents Repository

Contains:

* Annual Reports
* Financial Statements
* Investment Reports
* Uploaded User Documents

### Proposal Knowledge Repository

Contains:

* Financial proposal examples
* Banking consulting proposals
* Investment proposals
* Risk assessment proposals
* Previously approved proposals

### Template Repository

Contains:

* Executive Summary Templates
* Proposal Structure Templates
* Pricing Templates
* Timeline Templates
* Risk Templates

---

## Supported Files

* PDF
* DOCX
* PPTX
* PNG
* JPG

---

## Core Workflow

User Uploads Documents

↓

Document Processing

↓

OCR & Extraction

↓

Information Loss Analysis

↓

Embedding Generation

↓

ChromaDB Storage

↓

Private RAG Retrieval

↓

Proposal Generation

↓

Proposal Preview

↓

User Editing

↓

Download PDF / DOCX

---

## Technology Stack

### Frontend

* Next.js
* TypeScript
* TailwindCSS
* shadcn/ui
* Framer Motion

### Backend

* FastAPI
* Python
* LangGraph

### Storage

* PostgreSQL
* Redis
* ChromaDB

### Document Processing

* PyMuPDF
* Docling
* PaddleOCR
* python-docx
* python-pptx

### AI

Prototype:

* Claude Sonnet

Production:

* Internal Enterprise SLM

---

## Major Features

1. Financial Document Intelligence
2. Private RAG
3. Proposal Generation
4. Proposal Preview
5. Side-by-Side Editing
6. Prompt History
7. Metrics Dashboard
8. Information Loss Analysis
9. OCR Quality Analysis

---

## Proposal Preview Requirements

Layout:

Left Side:
Generated Proposal

Right Side:
Editable Proposal

Allowed:

* Text Editing

Not Allowed:

* Structural Editing
* Template Editing
* Section Reordering

---

## Metrics Dashboard

Track:

* Prompt History
* OCR Confidence
* Extraction Quality
* Information Loss %
* Processing Time
* Retrieved Sources
* Repository Contribution %
* Embedded Chunks
* Last Ingestion Date

---

## Repository Structure

knowledge_base/

financial_documents/

proposal_repository/

template_repository/

---

## Development Rules

* Follow Clean Architecture
* Follow SOLID Principles
* Use modular design
* Prefer reusable components
* Use async processing where appropriate
* Keep security-first architecture
* Use private RAG only
* Use architecture documents in /docs as detailed references

ARCHITECTURE_SUMMARY.md is the primary source of truth.

If conflicts exist:

1. ARCHITECTURE_SUMMARY.md
2. architecture.md
3. document-intelligence.md
4. rag-design.md
5. ui-design.md