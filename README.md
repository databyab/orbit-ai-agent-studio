# Orbit — AI Agent Studio

Orbit is an independent, feature-oriented AI agent studio built with React, FastAPI, PostgreSQL, Redis, and Qdrant. It provides a dashboard for configuring agents, managing knowledge sources, testing conversations, and deploying an embeddable chat widget.

This project is an independent implementation inspired by publicly observable product concepts. It is not affiliated with Chatbase and does not include Chatbase proprietary source code.

## Features

- Create and configure agents, including instructions, model, and temperature.
- Add knowledge from website URLs, text, Q&A pairs, and PDF, DOCX, or TXT files.
- Retrieve knowledge with Q&A matching and Qdrant vector search.
- Stream assistant responses and review conversations.
- Configure procedures and actions for supported workflows.
- Embed a chat widget using the served loader and isolated iframe.
- Explore the dashboard in preview mode when the API is unavailable.

## Technology

| Area | Technology |
| --- | --- |
| Dashboard | React, TypeScript, Vite |
| API | FastAPI, SQLAlchemy, Python |
| Relational data | PostgreSQL |
| Vector search | Qdrant and Sentence Transformers |
| Cache and service support | Redis |
| Local deployment | Docker Compose |

## Screenshots

Add screenshots to this section before publishing. Suggested images are the dashboard, agent configuration, knowledge sources, and chat playground.

### Dashboard

Screenshot placeholder — add the dashboard image here.

### Agent configuration

Screenshot placeholder — add the agent configuration image here.

### Knowledge sources

Screenshot placeholder — add the knowledge sources image here.

### Chat playground

Screenshot placeholder — add the chat playground image here.

## Run with Docker Compose

### Requirements

- Docker Engine with the Docker Compose plugin.
- A Groq or OpenAI API key for live model responses. The UI can still be explored in preview mode without a provider key.

### Start the stack

From the repository root, create a local environment file and add your provider key:

```bash
cp .env.example .env
```

Edit `.env`. Replace `SECRET_KEY` and `POSTGRES_PASSWORD`, then add `GROQ_API_KEY` or `OPENAI_API_KEY` if you want live model responses. Keep `.env` private; it is excluded from Git.

Build and start the dashboard, API, PostgreSQL, Redis, and Qdrant:

```bash
docker compose up --build
```

To start the stack in the background instead:

```bash
docker compose up -d --build
```

Open these local URLs:

| Service | URL |
| --- | --- |
| Dashboard | http://localhost:3000 |
| API documentation | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |

The Compose stack exposes PostgreSQL on port `5432`, Redis on host port `16379`, and Qdrant on ports `6333` and `6334`. Change the published ports in `docker-compose.yml` if they conflict with services on your machine.

View service logs with:

```bash
docker compose logs -f
```

Stop the containers while preserving database and vector data:

```bash
docker compose down
```

Docker volumes preserve PostgreSQL, Redis, and Qdrant data between restarts. The first knowledge ingestion may take longer while the embedding model is downloaded and initialized.

## Run the dashboard without Docker

The dashboard can run in preview mode without the API:

```bash
cd frontend
npm install
npm run dev
```

The Vite server uses port `3000` and proxies API requests to `http://localhost:8000`.

## Repository layout

```text
backend/       FastAPI application and Dockerfile
frontend/      React dashboard and Dockerfile
widget/        TypeScript widget loader source
docker-compose.yml
```

## Limitations

- This is an MVP foundation, not a production-ready multi-tenant service.
- Authentication and workspace authorization are not fully implemented. Do not expose the API publicly without adding authentication and enforcing tenant scoping.
- Provider keys and signing secrets need managed storage and rotation in a deployed environment.
- Rate limits, ingestion retries and background jobs, and monitoring need production configuration.
- Website ingestion and outbound actions need additional SSRF protections and network controls.
- Analytics and dashboard sample values are illustrative; they are not production measurements.
- Local inference and vector retrieval can be slow on a cold start while models initialize.
- No project license is included yet. Choose and add a license before accepting external contributions or publishing under open-source terms.

