# Agentic QA on Kernel

An intelligent QA automation agent that uses LangGraph and browser automation to perform automated testing and quality assurance tasks.

## Features

- 🤖 **AI-Powered Automation**: Uses LLMs (OpenAI, Anthropic, Gemini) to understand and execute QA tasks
- 🌐 **Browser Automation**: Integrates with onkernel browser for real browser interactions
- 📊 **LangGraph Workflow**: Structured agent workflow with planning, execution, and verification
- 🔄 **WebSocket Streaming**: Real-time updates via WebSocket connections
- 🎯 **Multi-LLM Support**: Supports OpenAI, Anthropic Claude, and Google Gemini models
- 📸 **Screenshot & Recording**: Captures screenshots and records browser sessions

## Quick Start

### Prerequisites

- Python 3.10+
- OpenAI API key (required)
- Gemini API key (optional, for fallback advisor)

### Installation

1. Clone the repository:
```bash
git clone git@github-personal:Mustafa9658/agentic_qa_onkerne.git
cd agentic_qa_onkernel
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp env.example .env
# Edit .env and add your API keys
```

4. Run the API server:
```bash
python run.py
```

The API will be available at `http://localhost:8000`

## Configuration

Key environment variables (see `env.example`):

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `GEMINI_API_KEY`: Your Gemini API key (optional)
- `LLM_MODEL`: LLM model to use (default: `gpt-4.1-mini`)
- `MAX_STEPS`: Maximum workflow steps (default: `50`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## API Endpoints

- `GET /`: Health check
- `POST /api/workflow/run`: Execute a QA workflow
- `WS /api/websocket`: WebSocket streaming endpoint
- `GET /api/health`: Detailed health status

## Project Structure

```
├── api/              # FastAPI application and routes
├── qa_agent/         # Core agent logic
│   ├── agent/        # Agent orchestration
│   ├── browser/      # Browser automation
│   ├── nodes/        # LangGraph workflow nodes
│   └── tools/        # Agent tools
└── run.py            # Application entry point
```

## License

MIT
