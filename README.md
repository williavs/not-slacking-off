# Not Slacking Off

**Not Slacking Off** is an open source, AI-powered Slack assistant for internal knowledge management. It connects your Slack workspace to your Confluence (or other knowledge bases) and uses LLMs to answer employee questions, route requests, and provide context-aware support—all while keeping your data private and under your control.

---

## Features
- Seamless Slack integration: `/ai` command for instant answers
- Connects to your internal Confluence (or other knowledge sources)
- Modular, category-based routing and context building
- Extensible with custom prompts and knowledge bases
- Runs entirely in your infrastructure (no SaaS lock-in)

---

## Quickstart (Local Development)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd not-slacking-off
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.example` to `.env` and fill in your secrets (Slack, Confluence, OpenAI, etc.)

4. **Run the bot locally:**
   ```bash
   python slack-bolt.py
   ```

5. **Test your setup:**
   - In Slack, use `/ai <your question>` in a channel where the bot is present.

---

## Deploying Internally (Docker & Kubernetes)

### Docker Compose (Simple)

1. **Build the Docker image:**
   ```bash
   docker build -t not-slacking-off .
   ```
2. **Run with Docker Compose:**
   - Edit `docker-compose.yml` (see example below) with your environment variables.
   - Start the stack:
     ```bash
     docker-compose up -d
     ```

**Example `docker-compose.yml`:**
```yaml
version: '3.8'
services:
  not-slacking-off:
    image: not-slacking-off:latest
    env_file:
      - .env
    restart: unless-stopped
```

### Kubernetes (Production)

1. **Build and push your Docker image to your registry.**
2. **Create a Kubernetes deployment and service:**
   - Use the provided `helm/` chart or write your own manifests.
   - Mount your `.env` as a Kubernetes Secret or ConfigMap.
   - Example snippet:
     ```yaml
     apiVersion: apps/v1
     kind: Deployment
     metadata:
       name: not-slacking-off
     spec:
       replicas: 1
       selector:
         matchLabels:
           app: not-slacking-off
       template:
         metadata:
           labels:
             app: not-slacking-off
         spec:
           containers:
             - name: bot
               image: <your-registry>/not-slacking-off:latest
               envFrom:
                 - secretRef:
                     name: not-slacking-off-env
     ```
3. **Expose the bot to your Slack workspace:**
   - Use an Ingress, LoadBalancer, or port-forward as appropriate.

---

## Configuration

All configuration is via environment variables. See `.env.example` for all required and optional settings, including:
- `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_API_TOKEN`
- `OPENAI_API_KEY` (or your preferred LLM provider)
- Logging, tracing, and more

---

## Extending & Customizing
- **Add new knowledge domains:** See [ADDING_NEW_PROMPT.md](./ADDING_NEW_PROMPT.md)
- **Understand the architecture:** See [README_ARCHITECTURE.md](./README_ARCHITECTURE.md)
- **Write your own prompts:** Edit files in `prompts/` and `knowledge_bases/`
- **Register new categories:** Edit the `CATEGORIES` dictionary in `bot.py`

---

## Contributing
We welcome issues, feature requests, and pull requests! Please open an issue to discuss major changes before submitting a PR.

---

## License
MIT (see [LICENSE](./LICENSE))

---

**Not Slacking Off** is built for organizations that want AI-powered knowledge management—without giving up control of their data or workflows. 