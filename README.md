# MeetMemo — AI Meeting Notes

AI-powered meeting transcription, speaker diarization, structured summarization, and action item tracking. Self-hosted with enterprise authentication support.

## Features

- **Audio/Video Upload** — Upload meeting recordings or record directly from the browser
- **AI Transcription** — Powered by faster-whisper with word-level timestamps
- **Speaker Diarization** — Automatically identifies who said what using pyannote.audio
- **Structured Summaries** — LLM-generated meeting title, attendees, key points, decisions, and action items
- **Full-Text Search** — Search across transcripts and summaries using PostgreSQL tsvector
- **Team Management** — Organize meetings into teams with role-based access
- **Enterprise Auth** — LDAP (Active Directory) and OIDC (Azure AD / Entra ID) support
- **PWA Support** — Install as a desktop/mobile app with offline access
- **Real-time Updates** — Server-Sent Events for live progress tracking

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python FastAPI |
| Database | PostgreSQL 16 + tsvector |
| Task Queue | Celery + Redis |
| ML | faster-whisper + pyannote-audio |
| LLM | Ollama (local) / OpenAI API |
| Frontend | Next.js 14 + TypeScript |
| PWA | @serwist/next |
| UI | Tailwind CSS + shadcn/ui |
| Enterprise Auth | LDAP (python-ldap3) + OIDC (authlib) |
| Deployment | Docker Compose |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) NVIDIA GPU with CUDA for faster transcription
- (Optional) Ollama for local LLM summarization

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/meetmemo.git
   cd meetmemo
   ```

2. Copy the environment file:
   ```bash
   cp .env.example .env
   # Edit .env to configure settings
   ```

3. Start with Docker Compose (CPU):
   ```bash
   make dev
   ```

4. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Celery Monitor (Flower): http://localhost:5555

### GPU Acceleration

```bash
# Set GPU device in .env
WHISPER_DEVICE=cuda

# Start with GPU support
make dev-cuda
```

## Usage

1. **Register** — First user is automatically assigned admin role
2. **Upload** — Click "Upload" to upload a meeting recording or record directly
3. **Process** — Click "Process" to start transcription, diarization, and summarization
4. **Review** — View transcript with speaker labels and structured summary
5. **Search** — Use the search bar to find content across all meetings

## Enterprise AD Configuration

### LDAP / Active Directory

```env
LDAP_ENABLED=true
LDAP_SERVER=ldap://your-ad-server:389
LDAP_BASE_DN=dc=yourcompany,dc=com
LDAP_BIND_DN=cn=binduser,dc=yourcompany,dc=com
LDAP_BIND_PASSWORD=your-password
LDAP_USER_SEARCH_FILTER=(sAMAccountName={})
```

### OIDC / Azure AD

```env
OIDC_ENABLED=true
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/your-tenant/v2.0/.well-known/openid-configuration
```

### Group-to-Role Mapping

Configure in Admin panel (`/admin`) after login:
- AD Security Group → MeetMemo Role (admin / editor / viewer)
- Supports automatic role assignment on login

## Model Download

所有 AI 模型默认从 **ModelScope** 下载（国内可稳定访问）：

| 模型 | ModelScope 地址 | 用途 |
|------|----------------|------|
| faster-whisper-base | `modelscope/Systran/faster-whisper-base` | 语音转文字 |
| speaker-diarization-3.1 | `pyannote/speaker-diarization-3.1` | 说话人分离 |

如需要切换到 HuggingFace 下载，在 `.env` 中设置：

```env
MODEL_DOWNLOAD_SOURCE=huggingface
# 使用 HuggingFace 时需要 token（pyannote 需先同意协议）
HF_TOKEN=hf_your_token_here
```

模型文件会缓存到 `ml_cache` 卷中，重启不重复下载。

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/login` | Login |
| `POST /api/v1/auth/register` | Register |
| `POST /api/v1/teams` | Create team |
| `GET /api/v1/meetings` | List meetings |
| `POST /api/v1/meetings` | Upload meeting |
| `GET /api/v1/meetings/:id` | Get meeting detail |
| `POST /api/v1/meetings/:id/process` | Start processing |
| `GET /api/v1/meetings/:id/transcript` | Get transcript |
| `GET /api/v1/meetings/:id/summary` | Get summary |
| `GET /api/v1/search?q=...` | Full-text search |
| `GET /api/v1/events` | SSE real-time updates |
| `GET /api/v1/admin/users` | List users (admin) |

## Development

### Without Docker

```bash
# Backend
make backend-install
make backend-dev

# Worker
make worker-dev

# Frontend
make frontend-install
make frontend-dev
```

### Project Structure

```
meetmemo/
├── backend/           # FastAPI backend
│   ├── app/
│   │   ├── api/       # HTTP routes
│   │   ├── auth/      # Auth providers (LDAP, OIDC)
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   └── tasks/     # Celery tasks (ML pipeline)
│   └── migrations/    # Alembic migrations
├── worker/            # Celery worker with ML models
│   └── Dockerfile
├── frontend/          # Next.js frontend
│   └── src/
│       ├── app/       # Pages
│       ├── components/ # React components
│       ├── hooks/     # Custom hooks
│       └── lib/       # API client, auth
├── docker-compose.yml
└── Makefile
```

## License

MIT
