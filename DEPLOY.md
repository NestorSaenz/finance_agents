# Despliegue de Safi en GCP (Cloud Run)

Dos servicios Cloud Run: **backend** (FastAPI) y **frontend** (Next.js). El frontend
proxya `/api` al backend (mismo esquema que en local, sin CORS). Vertex AI se autentica
con la **service account** del servicio (ADC), sin archivos de llave. Supabase, Groq y
Langfuse ya existen; sus claves van en **Secret Manager**.

> Ejecuta desde `E:\Ebis\TFM\financegpt`. Reemplaza `TU_PROJECT_ID` por tu proyecto GCP.

## 0) Variables y APIs (una vez)

```powershell
gcloud config set project TU_PROJECT_ID
gcloud config set run/region us-central1

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com
```

## 1) Secretos (Secret Manager)

Crea un secreto por cada credencial. La forma más simple sin problemas de saltos de línea
es la **consola** (Security → Secret Manager → Create secret, pega el valor). Por CLI:

```powershell
# Repite para cada uno; pega el valor cuando lo pida (Ctrl+Z + Enter para cerrar en PS).
# O usa un archivo temporal sin newline: Set-Content -NoNewline v.txt "VALOR"; gcloud secrets create NOMBRE --data-file=v.txt; Remove-Item v.txt
"VALOR" | gcloud secrets create SUPABASE_URL         --data-file=-
"VALOR" | gcloud secrets create SUPABASE_KEY         --data-file=-   # service key (sb_secret_...)
"VALOR" | gcloud secrets create SUPABASE_ANON_KEY    --data-file=-   # sb_publishable_...
"VALOR" | gcloud secrets create GROQ_API_KEY         --data-file=-
"VALOR" | gcloud secrets create LANGFUSE_PUBLIC_KEY  --data-file=-
"VALOR" | gcloud secrets create LANGFUSE_SECRET_KEY  --data-file=-
```

## 2) Service account con permisos

```powershell
gcloud iam service-accounts create safi-run --display-name="Safi Cloud Run"

# Guarda el email (o constrúyelo: safi-run@TU_PROJECT_ID.iam.gserviceaccount.com)
$SA = "safi-run@TU_PROJECT_ID.iam.gserviceaccount.com"

# Vertex AI (LLM + embeddings) por ADC
gcloud projects add-iam-policy-binding TU_PROJECT_ID --member="serviceAccount:$SA" --role="roles/aiplatform.user"
# Leer los secretos
gcloud projects add-iam-policy-binding TU_PROJECT_ID --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
```

## 3) Desplegar el BACKEND

```powershell
gcloud run deploy safi-backend `
  --source . `
  --service-account safi-run@TU_PROJECT_ID.iam.gserviceaccount.com `
  --allow-unauthenticated `
  --set-env-vars "ENVIRONMENT=production,LLM_PROVIDER=vertex,EMBEDDING_PROVIDER=vertex,VECTOR_STORE_PROVIDER=pgvector,EMBEDDING_DIMENSION=768,GCP_PROJECT=TU_PROJECT_ID,GCP_LOCATION=us-central1,VERTEX_LLM_MODEL_SIMPLE=gemini-2.5-flash-lite,VERTEX_LLM_MODEL_COMPLEX=gemini-2.5-flash,VERTEX_EMBED_MODEL=gemini-embedding-001,LANGFUSE_HOST=https://cloud.langfuse.com" `
  --set-secrets "SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_KEY=SUPABASE_KEY:latest,SUPABASE_ANON_KEY=SUPABASE_ANON_KEY:latest,GROQ_API_KEY=GROQ_API_KEY:latest,LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest,LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
```

Copia la **URL** que imprime (ej. `https://safi-backend-xxxx.a.run.app`).

## 4) Desplegar el FRONTEND (apuntando al backend)

> **IMPORTANTE**: los `rewrites` de Next.js (el proxy `/api` → backend) se hornean en
> tiempo de **BUILD**, no de runtime. Por eso la URL del backend va como `ARG API_URL` en
> `frontend/Dockerfile` (con la URL de producción como default), NO como env de runtime.
> Si el backend cambia de URL, actualiza ese `ARG` o pásalo con `--build-arg`.

```powershell
gcloud run deploy safi-frontend --source frontend --allow-unauthenticated
```

Abre la URL del frontend → ahí está Safi en vivo. 🎉

Verifica el proxy: `https://<frontend-url>/api/v1/health` debe devolver
`{"status":"healthy","service":"Safi"}`.

## Despliegue continuo (GitHub Actions + WIF)

Además del despliegue manual de arriba, cada **merge a `main`** despliega solo lo que
cambió, con un **gate de calidad** antes (si falla, no se despliega):

- `.github/workflows/deploy-backend.yml` — se dispara con cambios en `app/**`,
  `tests/**`, `pyproject.toml`, `uv.lock` o `Dockerfile`. Corre `ruff` + `mypy` +
  `pytest` y luego `gcloud run deploy safi-backend --source .`.
- `.github/workflows/deploy-frontend.yml` — se dispara con cambios en `frontend/**`.
  Corre `typecheck` + `lint` + `test` y luego `gcloud run deploy safi-frontend --source frontend`.

**Autenticación sin llaves (Workload Identity Federation):** GitHub se identifica ante GCP
por OIDC; no hay ninguna service-account key en el repo. La identidad de deploy es
`github-deployer@…` y el provider está **restringido al repo** `NestorSaenz/finance_agents`
(atributo `assertion.repository`). Los valores (provider y SA) no son secretos y viven en
el `env` de cada workflow.

Setup de infra (una vez, ya aplicado): pool + provider OIDC, la SA `github-deployer` con
roles `run.admin`, `cloudbuild.builds.editor`, `artifactregistry.writer`, `storage.admin`,
`iam.serviceAccountUser`, y binding `workloadIdentityUser` para el repo.

Se puede lanzar a mano desde la pestaña **Actions** (ambos workflows tienen `workflow_dispatch`).

## Notas

- **ENVIRONMENT=production** desactiva el usuario demo: la app exige login real (correcto).
- **CORS no hace falta** (el frontend proxya same-origin). Si algún día llamas la API
  directo desde el navegador, agrega el origen del front a `BACKEND_CORS_ORIGINS`.
- **Costo**: Cloud Run escala a cero; con poco uso, prácticamente gratis. Vertex/Groq/
  Supabase/Langfuse ya están configurados.
- **Actualizar**: vuelve a correr el `gcloud run deploy` correspondiente (rebuild + deploy).
- **Migraciones**: Supabase es externo; ya corriste 001–009. No hay paso de migración aquí.
