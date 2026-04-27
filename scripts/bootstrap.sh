#!/usr/bin/env bash
# scripts/bootstrap.sh — setup completo de zero.
# Idempotente: rodar várias vezes não quebra nada.

set -euo pipefail

BLUE='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

log() { echo -e "${BLUE}[bootstrap]${RESET} $*"; }
ok()  { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "${RED}✗${RESET} $*"; exit 1; }

# ─── Pré-requisitos ─────────────────────────────────────────
log "Verificando pré-requisitos..."

command -v docker >/dev/null || fail "Docker não encontrado. Instale: https://docs.docker.com/engine/install/"
command -v docker compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 \
    || fail "docker compose v2 não encontrado."
command -v uv >/dev/null || fail "uv não encontrado. Instale: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v jq >/dev/null || warn "jq não encontrado — alguns alvos do Makefile vão falhar (apt install jq / brew install jq)"
command -v java >/dev/null || warn "Java não encontrado — necessário para SUSHI/IG Publisher/validator_cli"
command -v node >/dev/null || warn "Node não encontrado — necessário para SUSHI (npm install -g fsh-sushi)"

ok "Docker, docker compose e uv presentes."

# ─── vm.max_map_count para Elasticsearch ────────────────────
log "Configurando vm.max_map_count para Elasticsearch (Snowstorm requirement)..."
CURRENT_VM=$(sysctl -n vm.max_map_count 2>/dev/null || echo "0")
if [ "$CURRENT_VM" -lt 262144 ]; then
    if [ "$(uname)" = "Linux" ]; then
        warn "vm.max_map_count atual: $CURRENT_VM (Snowstorm precisa ≥262144)"
        echo "    Rodar manualmente como root: sudo sysctl -w vm.max_map_count=262144"
        echo "    Persistir em /etc/sysctl.conf: vm.max_map_count=262144"
    else
        ok "Não-Linux detectado, Docker Desktop gerencia o sysctl."
    fi
else
    ok "vm.max_map_count = $CURRENT_VM (ok)"
fi

# ─── .env ───────────────────────────────────────────────────
log "Configurando .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    ok ".env criado a partir de .env.example"
    warn "EDITE .env antes de continuar — especialmente segredos do Langfuse e ANTHROPIC_API_KEY"

    # Gerar segredos Langfuse automaticamente
    NEXTAUTH=$(openssl rand -base64 32)
    SALT=$(openssl rand -base64 32)
    ENC_KEY=$(openssl rand -hex 32)

    # Substituir in-place (compat macOS + Linux)
    if [ "$(uname)" = "Darwin" ]; then
        sed -i '' "s|^LANGFUSE_NEXTAUTH_SECRET=.*|LANGFUSE_NEXTAUTH_SECRET=$NEXTAUTH|" .env
        sed -i '' "s|^LANGFUSE_SALT=.*|LANGFUSE_SALT=$SALT|" .env
        sed -i '' "s|^LANGFUSE_ENCRYPTION_KEY=.*|LANGFUSE_ENCRYPTION_KEY=$ENC_KEY|" .env
    else
        sed -i "s|^LANGFUSE_NEXTAUTH_SECRET=.*|LANGFUSE_NEXTAUTH_SECRET=$NEXTAUTH|" .env
        sed -i "s|^LANGFUSE_SALT=.*|LANGFUSE_SALT=$SALT|" .env
        sed -i "s|^LANGFUSE_ENCRYPTION_KEY=.*|LANGFUSE_ENCRYPTION_KEY=$ENC_KEY|" .env
    fi
    ok "Segredos Langfuse gerados automaticamente."
else
    ok ".env já existe (não vou sobrescrever)"
fi

# ─── Diretórios ────────────────────────────────────────────
log "Criando diretórios necessários..."
mkdir -p data/snomed-import
mkdir -p data/codesystems/{cid10,tuss,sigtap,brcbhpmtuss,cbo,snomed_br,loinc}/raw
mkdir -p data/conceptmaps
mkdir -p data/golden/{swagger_specs,fhir_bundles,conceptmap_pairs}
mkdir -p data/fixtures
mkdir -p ig/{input/fsh,input/pagecontent,input/images}
mkdir -p ig/input-cache ig/output
mkdir -p tools
mkdir -p secrets
mkdir -p .langfuse
ok "Diretórios criados"

# ─── Permissões ────────────────────────────────────────────
chmod 700 secrets
ok "secrets/ com permissões 700"

# ─── Python deps ──────────────────────────────────────────
log "Instalando dependências Python via uv..."
uv sync --all-extras --dev
ok "uv sync concluído"

# ─── pre-commit ───────────────────────────────────────────
log "Instalando pre-commit hooks..."
uv run pre-commit install || warn "pre-commit não instalado (config faltando? OK se ainda não criou .pre-commit-config.yaml)"

# ─── Subir docker stack ───────────────────────────────────
log "Subindo stack Docker..."
docker compose pull --quiet
docker compose up -d
ok "Stack iniciada — healthchecks rodando em background"

# ─── Aguardar health ──────────────────────────────────────
log "Aguardando serviços ficarem healthy (até 3 minutos)..."
TIMEOUT=180
ELAPSED=0
INTERVAL=5
while [ $ELAPSED -lt $TIMEOUT ]; do
    UNHEALTHY=$(docker compose ps --format json | grep -c '"Health":"starting"' || echo "0")
    if [ "$UNHEALTHY" = "0" ]; then
        break
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    echo -n "."
done
echo ""

# ─── Status final ──────────────────────────────────────────
log "Status final dos serviços:"
docker compose ps

echo ""
ok "Bootstrap concluído!"
echo ""
echo "Próximos passos:"
echo "  1. Edite .env com sua ANTHROPIC_API_KEY (e demais providers que for usar)"
echo "  2. make health           # confirmar que tudo respondeu"
echo "  3. make download-validator # baixa validator_cli.jar para tools/"
echo "  4. npm install -g fsh-sushi # se for usar SUSHI"
echo "  5. make api              # sobe FastAPI gateway em modo dev"
echo ""
echo "URLs locais:"
echo "  HAPI FHIR:    http://localhost:8090/fhir"
echo "  Snowstorm:    http://localhost:8080"
echo "  Minio:        http://localhost:9001  (UI; user/pass do .env)"
echo "  Langfuse:     http://localhost:3000"
echo "  Adminer:      http://localhost:8081  (sobe com: docker compose --profile debug up -d)"
echo ""
