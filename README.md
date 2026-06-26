# Nextleap Zomato - AI-Powered Restaurant Recommendation System

An AI-powered restaurant recommendation service inspired by Zomato. Combines structured restaurant data from a Hugging Face dataset with Groq LLM to deliver personalized, explainable recommendations.

## Features

- 🔍 **Smart Filtering** — Filter by location, budget, cuisine, and rating
- 🤖 **AI Explanations** — Groq LLM provides human-like explanations for each recommendation
- ⚡ **Fast Inference** — Groq's optimized inference for near-instant responses
- 🎯 **Adaptive Results** — Automatically relaxes filters when results are too narrow

## Quick Start

### 1. Setup

```bash
# Clone the repository
git clone <repo-url>
cd "Nextleap Zomato"

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your GROQ_API_KEY
```

### 2. Run

```bash
python src/main.py
```

## Project Structure

```
Nextleap Zomato/
├── Docs/                        # Project documentation
│   ├── ProblemStatement.txt
│   ├── context.md
│   ├── architecture.md
│   ├── implementation-plan.md
│   └── edge-cases.md
├── src/
│   ├── main.py                  # Application entry point
│   ├── config.py                # Configuration management
│   ├── data/
│   │   ├── loader.py            # Hugging Face dataset loader
│   │   └── preprocessor.py      # Data cleaning & indexing
│   ├── models/
│   │   └── restaurant.py        # Restaurant data model
│   ├── services/                # (Phase 2-3)
│   └── api/                     # (Phase 4)
├── tests/                       # (Phase 5)
├── .env.example
├── requirements.txt
└── README.md
```

## Documentation

- [Problem Statement](Docs/ProblemStatement.txt)
- [Architecture](Docs/architecture.md)
- [Implementation Plan](Docs/implementation-plan.md)
- [Edge Cases](Docs/edge-cases.md)

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Dataset | Hugging Face `datasets` |
| Data Processing | pandas |
| LLM | Groq (llama-3.3-70b-versatile) |
| Web Framework | FastAPI |
| Config | python-dotenv |

## License

MIT
