# Arquitectura de FinanceGPT

## Visión General

FinanceGPT es un asistente financiero personal inteligente basado en arquitectura multiagente con IA Generativa. El sistema permite gestionar finanzas personales de forma conversacional y automatizada.

## Stack Tecnológico

| Capa | Tecnología | Propósito |
|------|------------|-----------|
| **LLM** | Cohere Command R+ | Generación de respuestas, análisis |
| **Embeddings** | Cohere Embed v3 Multilingual | Vectorización de transacciones |
| **Vector DB** | Pinecone Serverless | Almacenamiento y búsqueda de vectores |
| **Base de Datos** | Supabase (PostgreSQL) | Datos estructurados, usuarios |
| **Auth** | Supabase Auth | Autenticación y autorización |
| **Backend** | FastAPI + Python 3.11+ | API REST (Async) |
| **Orquestación** | LangGraph | Sistema multiagente |
| **Framework LLM** | LangChain | Integración con LLMs |
| **Observabilidad** | Langfuse | Monitoreo de LLM |
| **Frontend** | React + TypeScript | Interfaz de usuario |

---

## Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│                         React + TypeScript                                   │
│                    Supabase JS Client (Auth + Realtime)                     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SUPABASE                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │      Auth       │  │   PostgreSQL    │  │        Realtime             │  │
│  │  JWT + OAuth2   │  │   (500MB free)  │  │    (Alertas push)           │  │
│  │  Row Level Sec  │  │                 │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ JWT Validado
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             FASTAPI BACKEND (Async)                          │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         API ROUTES                                     │  │
│  │   /chat  │  /transactions  │  /budgets  │  /goals  │  /health         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                           │
│  ┌───────────────────────────────▼───────────────────────────────────────┐  │
│  │                 LANGGRAPH HYBRID MULTIAGENT SYSTEM                    │  │
│  │                                                                        │  │
│  │    ┌─────────────┐                                                    │  │
│  │    │ Orchestrator│──────────────────────────────────────┐             │  │
│  │    │  (Router)   │                                      │             │  │
│  │    └──────┬──────┘                                      │             │  │
│  │           │                                             │             │  │
│  │    ┌──────┴──────┐                                      │             │  │
│  │    │ Complexity  │                                      │             │  │
│  │    │ Classifier  │                                      │             │  │
│  │    └──────┬──────┘                                      │             │  │
│  │           │                                             │             │  │
│  │    ┌──────┴──────────────────────┐                      │             │  │
│  │    ▼                             ▼                      │             │  │
│  │ ┌──────────────┐          ┌──────────────────────┐      │             │  │
│  │ │ SIMPLE PATH  │          │    COMPLEX PATH      │      │             │  │
│  │ │   (Direct)   │          │ (Plan-Execute-Replan)│      │             │  │
│  │ └──────┬───────┘          └──────────┬───────────┘      │             │  │
│  │        │                             │                  │             │  │
│  │        ▼                             ▼                  │             │  │
│  │ ┌────────────┐              ┌─────────────────┐         │             │  │
│  │ │Single Agent│              │   Planner       │         │             │  │
│  │ │ Execution  │              │   ↓             │         │             │  │
│  │ └──────┬─────┘              │   Executor(s)   │         │             │  │
│  │        │                    │   ↓             │         │             │  │
│  │        │                    │   Replanner     │◄────────┘             │  │
│  │        │                    └────────┬────────┘                       │  │
│  │        │                             │                                │  │
│  │        └─────────────┬───────────────┘                                │  │
│  │                      ▼                                                │  │
│  │              ┌─────────────────┐                                      │  │
│  │              │    RESPONSE     │                                      │  │
│  │              │   GENERATOR     │                                      │  │
│  │              └─────────────────┘                                      │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                  │                                           │
│  ┌───────────────────────────────▼───────────────────────────────────────┐  │
│  │                         SERVICES LAYER                                 │  │
│  │   TransactionService │ BudgetService │ GoalService │ EmbeddingService │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                           │
│  ┌───────────────────────────────▼───────────────────────────────────────┐  │
│  │                        REPOSITORIES LAYER                              │  │
│  │  TransactionRepo │ BudgetRepo │ GoalRepo │ UserRepo │ EmbeddingRepo   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└───────────┬─────────────────────────────────────┬────────────────────────────┘
            │                                     │
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│        COHERE         │             │       PINECONE        │
│  ┌─────────────────┐  │             │    ┌─────────────┐    │
│  │ Command R+      │  │             │    │  Serverless │    │
│  │ (LLM)           │  │             │    │  Index      │    │
│  ├─────────────────┤  │             │    │             │    │
│  │ Embed v3        │  │────────────►│    │  Vectors +  │    │
│  │ (Embeddings)    │  │             │    │  Metadata   │    │
│  └─────────────────┘  │             │    └─────────────┘    │
└───────────────────────┘             └───────────────────────┘
            │
            ▼
┌───────────────────────┐
│       LANGFUSE        │
│   (Observabilidad)    │
│   - Traces            │
│   - Costs             │
│   - Latency           │
└───────────────────────┘
```

---

## Sistema Multiagente Híbrido (LangGraph)

### Filosofía del Diseño

El sistema utiliza una **arquitectura híbrida** que optimiza el balance entre latencia/costo y capacidad de análisis:

| Tipo de Consulta | Path | Latencia | Costo | Ejemplo |
|------------------|------|----------|-------|---------|
| Simple | Direct | ~1-2s | Bajo | "Registra un gasto de $50 en comida" |
| Compleja | Plan-Execute-Replan | ~5-15s | Medio-Alto | "Analiza mis gastos del último trimestre y dame un plan para ahorrar $200" |

### Flujo del Grafo Híbrido

```
                         ┌─────────────────┐
                         │   User Input    │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  ORCHESTRATOR   │
                         │  (Intent Router)│
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   COMPLEXITY    │
                         │   CLASSIFIER    │
                         │                 │
                         │ ¿Requiere plan? │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
           ┌────────────────┐          ┌────────────────┐
           │  SIMPLE PATH   │          │  COMPLEX PATH  │
           │                │          │                │
           │  Ejecución     │          │ Plan-Execute-  │
           │  Directa       │          │ Replan Loop    │
           └───────┬────────┘          └───────┬────────┘
                   │                           │
                   │                           ▼
                   │                  ┌────────────────┐
                   │                  │    PLANNER     │
                   │                  │                │
                   │                  │ Genera plan de │
                   │                  │ N pasos        │
                   │                  └───────┬────────┘
                   │                          │
                   │                          ▼
                   │                  ┌────────────────┐
                   │                  │   EXECUTOR     │
                   │                  │                │
                   │         ┌───────►│ Ejecuta paso   │
                   │         │        │ actual         │
                   │         │        └───────┬────────┘
                   │         │                │
                   │         │                ▼
                   │         │        ┌────────────────┐
                   │         │        │   REPLANNER    │
                   │         │        │                │
                   │         │        │ ¿Plan completo?│
                   │         │        │ ¿Ajustar plan? │
                   │         │        └───────┬────────┘
                   │         │                │
                   │         │     ┌──────────┴──────────┐
                   │         │     │                     │
                   │         │     ▼                     ▼
                   │         │  Continuar            Finalizado
                   │         │  (siguiente paso)         │
                   │         │     │                     │
                   │         └─────┘                     │
                   │                                     │
                   └─────────────────┬───────────────────┘
                                     │
                                     ▼
                            ┌────────────────┐
                            │    RESPONSE    │
                            │   GENERATOR    │
                            └───────┬────────┘
                                    │
                                    ▼
                            ┌────────────────┐
                            │ Final Response │
                            └────────────────┘
```

### Ejemplo de Plan-Execute-Replan

**Usuario:** "Analiza mis gastos del último trimestre, identifica patrones y dame un plan de ahorro"

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PLANNER - Plan Inicial                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. Recuperar transacciones Q4 2024                                      │
│ 2. Calcular totales por categoría                                       │
│ 3. Identificar categorías con mayor gasto                               │
│ 4. Detectar patrones de gasto (días, frecuencia)                        │
│ 5. Comparar con meses anteriores                                        │
│ 6. Generar recomendaciones de ahorro personalizadas                     │
│ 7. Crear plan de ahorro mensual                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ EXECUTOR - Paso 1                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│ Agente: ANALYST                                                          │
│ Acción: query_transactions(user_id, start="2024-10", end="2024-12")     │
│ Resultado: 156 transacciones recuperadas                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ REPLANNER - Evaluación                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ ✅ Paso 1 completado exitosamente                                        │
│ Nuevo estado: 156 transacciones disponibles                              │
│ Decisión: Continuar con paso 2                                           │
│ Ajuste: Ninguno necesario                                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                              [...pasos 2-7...]
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ RESPONSE GENERATOR                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ "Basándome en el análisis de tus 156 transacciones del último           │
│  trimestre, encontré que:                                                │
│                                                                          │
│  📊 Principales gastos:                                                  │
│  - Comida: $450.000 (35%)                                               │
│  - Transporte: $280.000 (22%)                                           │
│  - Entretenimiento: $180.000 (14%)                                      │
│                                                                          │
│  🔍 Patrones detectados:                                                 │
│  - Mayor gasto en fines de semana (+45%)                                │
│  - Picos en delivery los viernes                                        │
│                                                                          │
│  💰 Plan de ahorro sugerido:                                            │
│  1. Reducir delivery de 8 a 4 veces/mes: ahorro $60.000                 │
│  2. Usar transporte público 2 días/semana: ahorro $40.000               │
│  3. Establecer límite de entretenimiento: ahorro $50.000                │
│                                                                          │
│  Meta alcanzable: $150.000-200.000/mes"                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### Descripción de Agentes

#### Agentes Base (Ambos Paths)

| Agente | Responsabilidad | Herramientas |
|--------|-----------------|--------------|
| **Orchestrator** | Interpreta intención y clasifica complejidad | Intent classification, complexity scoring |
| **Categorizer** | Clasifica transacciones usando similitud semántica | Cohere Embed, Pinecone search |
| **Analyst** | Detecta patrones de gasto, genera insights y métricas | SQL queries, aggregations, statistics |
| **Planner** | Diseña planes de ahorro y estrategias financieras | Goal calculations, projections |
| **Recommender** | Genera alertas proactivas y sugerencias de optimización | Budget analysis, trend detection |
| **Response Generator** | Sintetiza respuesta final coherente y personalizada | Template rendering, formatting |

#### Agentes Exclusivos del Complex Path

| Agente | Responsabilidad | Herramientas |
|--------|-----------------|--------------|
| **Task Planner** | Descompone consultas complejas en pasos ejecutables | LLM planning, task decomposition |
| **Executor** | Ejecuta cada paso del plan delegando al agente apropiado | Agent routing, tool execution |
| **Replanner** | Evalúa resultados y ajusta el plan según necesidad | State evaluation, plan modification |

### Estado Compartido (AgentState)

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class PlanStep(TypedDict):
    """Representa un paso del plan."""
    step_number: int
    description: str
    assigned_agent: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    result: dict | None
    error: str | None

class AgentState(TypedDict):
    """Estado compartido entre todos los agentes."""

    # Mensajes de la conversación
    messages: Annotated[list, add_messages]

    # Contexto del usuario
    user_id: str
    user_preferences: dict

    # Datos financieros relevantes
    recent_transactions: list[dict]
    current_budgets: list[dict]
    active_goals: list[dict]

    # Clasificación de consulta
    detected_intent: str
    query_complexity: Literal["simple", "complex"]

    # Plan-Execute-Replan (solo para complex path)
    current_plan: list[PlanStep]
    current_step_index: int
    execution_history: list[dict]
    requires_replan: bool

    # Resultados intermedios
    category_suggestion: str | None
    analysis_results: dict | None
    recommendations: list[str]

    # Control de flujo
    next_agent: str
    should_respond: bool
    iteration_count: int  # Para prevenir loops infinitos
    max_iterations: int
```

### Implementación del Grafo LangGraph

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def create_financegpt_graph() -> StateGraph:
    """Crea el grafo híbrido de FinanceGPT."""

    graph = StateGraph(AgentState)

    # Nodos principales
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("complexity_classifier", classify_complexity)

    # Nodos del Simple Path
    graph.add_node("categorizer", categorizer_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("planner", planner_node)
    graph.add_node("recommender", recommender_node)

    # Nodos del Complex Path (Plan-Execute-Replan)
    graph.add_node("task_planner", task_planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("replanner", replanner_node)

    # Nodo final
    graph.add_node("response_generator", response_generator_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Edges desde orchestrator
    graph.add_edge("orchestrator", "complexity_classifier")

    # Routing condicional basado en complejidad
    graph.add_conditional_edges(
        "complexity_classifier",
        route_by_complexity,
        {
            "simple": "route_simple",
            "complex": "task_planner",
        }
    )

    # Simple path: routing directo a agente especializado
    graph.add_conditional_edges(
        "route_simple",
        route_to_agent,
        {
            "categorizer": "categorizer",
            "analyst": "analyst",
            "planner": "planner",
            "recommender": "recommender",
        }
    )

    # Todos los agentes simples van al response generator
    for agent in ["categorizer", "analyst", "planner", "recommender"]:
        graph.add_edge(agent, "response_generator")

    # Complex path: ciclo Plan-Execute-Replan
    graph.add_edge("task_planner", "executor")
    graph.add_edge("executor", "replanner")

    # Replanner decide si continuar o finalizar
    graph.add_conditional_edges(
        "replanner",
        should_continue_or_finish,
        {
            "continue": "executor",
            "replan": "task_planner",
            "finish": "response_generator",
        }
    )

    # Response generator es el final
    graph.add_edge("response_generator", END)

    return graph.compile(checkpointer=MemorySaver())


def route_by_complexity(state: AgentState) -> str:
    """Determina qué path tomar basado en la complejidad."""
    return state["query_complexity"]


def should_continue_or_finish(state: AgentState) -> str:
    """Decide si continuar ejecutando, replanificar, o finalizar."""

    # Prevenir loops infinitos
    if state["iteration_count"] >= state["max_iterations"]:
        return "finish"

    # Verificar si el plan está completo
    current_plan = state["current_plan"]
    all_completed = all(
        step["status"] == "completed"
        for step in current_plan
    )

    if all_completed:
        return "finish"

    # Verificar si necesita replanificación
    if state["requires_replan"]:
        return "replan"

    return "continue"
```

### Criterios de Clasificación de Complejidad

```python
def classify_complexity(state: AgentState) -> AgentState:
    """Clasifica la consulta como simple o compleja."""

    message = state["messages"][-1].content

    # Indicadores de consulta COMPLEJA
    complex_indicators = [
        # Múltiples acciones
        " y " in message and any(verb in message for verb in ["analiza", "compara", "planifica"]),

        # Análisis temporal extenso
        any(term in message for term in ["trimestre", "semestre", "año", "histórico"]),

        # Solicitudes de planificación elaborada
        any(term in message for term in ["plan de ahorro", "estrategia", "optimizar"]),

        # Comparaciones múltiples
        "compara" in message and "categorías" in message,

        # Proyecciones
        any(term in message for term in ["proyección", "futuro", "meta"]),
    ]

    # Indicadores de consulta SIMPLE
    simple_indicators = [
        # Acciones únicas
        message.startswith("registra") or message.startswith("agrega"),

        # Consultas puntuales
        "cuánto gasté" in message and "hoy" in message,

        # Categorizaciones simples
        "categoriza" in message and "transacción" in message,

        # Consultas de balance
        "saldo" in message or "balance" in message,
    ]

    is_complex = any(complex_indicators) and not any(simple_indicators)

    return {
        **state,
        "query_complexity": "complex" if is_complex else "simple",
    }
```

---

## Pipeline RAG

### Flujo de Indexación

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Transaction    │────►│  Cohere Embed   │────►│    Pinecone     │
│  Created        │     │  v3 Multilingual│     │    Upsert       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       │                       │
        ▼                       ▼                       ▼
   "Almuerzo con         [0.123, -0.456,          id: "tx_123"
    colegas en            0.789, ...]             vector: [...]
    restaurante"          (1024 dims)             metadata: {
                                                    user_id: "u_1"
                                                    category: "food"
                                                    amount: 50000
                                                    date: "2024-12"
                                                  }
```

### Flujo de Retrieval

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  User Query     │────►│  Cohere Embed   │────►│ Pinecone Search │
│  "¿Cuánto gasté │     │  (search_query) │     │ + Metadata      │
│   en comida?"   │     └─────────────────┘     │   Filter        │
└─────────────────┘                             └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Final Response │◄────│  Cohere LLM     │◄────│ Top K Results   │
│  "Este mes has  │     │  Command R+     │     │ + Context       │
│   gastado..."   │     │  (RAG prompt)   │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Modelo de Datos (Supabase)

### Diagrama ER

```
┌─────────────────────┐
│       users         │
├─────────────────────┤
│ id (UUID) PK        │
│ email               │
│ created_at          │
│ preferences (JSONB) │
└──────────┬──────────┘
           │
           │ 1:N
           ▼
┌─────────────────────┐      ┌─────────────────────┐
│   transactions      │      │     categories      │
├─────────────────────┤      ├─────────────────────┤
│ id (UUID) PK        │      │ id (UUID) PK        │
│ user_id FK          │◄────►│ name                │
│ amount (DECIMAL)    │      │ icon                │
│ description         │      │ color               │
│ transaction_type    │      │ is_default          │
│ category_id FK      │      └─────────────────────┘
│ date                │
│ embedding_id        │
│ created_at          │
└──────────┬──────────┘
           │
           │ N:1
           ▼
┌─────────────────────┐      ┌─────────────────────┐
│      budgets        │      │       goals         │
├─────────────────────┤      ├─────────────────────┤
│ id (UUID) PK        │      │ id (UUID) PK        │
│ user_id FK          │      │ user_id FK          │
│ category_id FK      │      │ name                │
│ amount_limit        │      │ target_amount       │
│ period (monthly)    │      │ current_amount      │
│ alert_threshold     │      │ deadline            │
│ created_at          │      │ status              │
└─────────────────────┘      │ created_at          │
                             └─────────────────────┘
```

### Row Level Security (RLS)

```sql
-- Usuarios solo ven sus propios datos
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own transactions"
  ON transactions FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own transactions"
  ON transactions FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own transactions"
  ON transactions FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own transactions"
  ON transactions FOR DELETE
  USING (auth.uid() = user_id);
```

---

## Observabilidad

### Langfuse Integration

```python
from langfuse.callback import CallbackHandler

# En cada llamada al agente
langfuse_handler = CallbackHandler(
    user_id=user_id,
    session_id=session_id,
    tags=["financegpt", "chat"],
)

response = await agent.ainvoke(
    input={"messages": messages},
    config=RunnableConfig(callbacks=[langfuse_handler]),
)
```

### Métricas Tracked

| Métrica | Descripción |
|---------|-------------|
| **Latencia** | Tiempo de respuesta por agente y por path (simple/complex) |
| **Tokens** | Input/output tokens por request |
| **Costo** | Costo estimado por request |
| **Errores** | Tasa de errores por tipo |
| **Traces** | Flujo completo de cada request |
| **Plan Success Rate** | % de planes completados vs. replanificados |
| **Iteration Count** | Promedio de iteraciones en complex path |

### Logging Estructurado

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

logger.info(
    "Transaction created",
    extra={
        "transaction_id": tx.id,
        "user_id": user_id,
        "amount": float(tx.amount),
        "category": tx.category,
    }
)
```

---

## Seguridad

### Autenticación

- **Supabase Auth** para gestión de usuarios
- **JWT** tokens para autenticación de API
- **OAuth2** opcional (Google, GitHub)

### Autorización

- **Row Level Security (RLS)** en Supabase
- **Middleware** de validación de JWT en FastAPI
- **Scopes** por tipo de operación

### Protección de Datos

| Medida | Implementación |
|--------|----------------|
| Cifrado en tránsito | TLS 1.3 |
| Cifrado en reposo | Supabase encryption |
| API Keys | Variables de entorno (.env) |
| Rate Limiting | FastAPI middleware |
| Input Validation | Pydantic models |

### Prevención de Prompt Injection

```python
# Sanitización de inputs
def sanitize_user_input(text: str) -> str:
    """Elimina patrones potencialmente maliciosos."""
    # Remover intentos de inyección de prompts
    dangerous_patterns = [
        "ignore previous instructions",
        "system:",
        "assistant:",
    ]
    for pattern in dangerous_patterns:
        text = text.replace(pattern, "")
    return text.strip()
```

---

## Deployment

### Desarrollo Local

```bash
# Clonar repositorio
git clone <repo>
cd financegpt

# Instalar dependencias
uv sync

# Configurar variables de entorno
cp .env.example .env

# Ejecutar en desarrollo
uv run fastapi dev app/main.py
```

### Docker

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - redis

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

### Producción

```
┌─────────────────────────────────────────────────────────────┐
│                    VPS (Hetzner ~$15/mes)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   FastAPI       │  │    Langfuse     │  │   Grafana   │  │
│  │   (Docker)      │  │   (Self-host)   │  │   + Loki    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    Supabase     │  │    Pinecone     │  │     Cohere      │
│    (Managed)    │  │   (Serverless)  │  │      (API)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Estimación de Costos

### MVP (0-100 usuarios)

| Servicio | Costo/mes |
|----------|-----------|
| Supabase Free | $0 |
| Pinecone Free | $0 |
| Cohere (pay-as-you-go) | ~$1-5 |
| VPS Hetzner CX22 | ~$8 |
| Langfuse Cloud Free | $0 |
| **Total** | **~$10-15/mes** |

### Producción (100-1000 usuarios)

| Servicio | Costo/mes |
|----------|-----------|
| Supabase Pro | $25 |
| Pinecone (pay-as-you-go) | ~$10-20 |
| Cohere | ~$20-50 |
| VPS Hetzner CX32 | ~$15 |
| **Total** | **~$70-110/mes** |

---

## Estructura del Proyecto

```
financegpt/
├── app/
│   ├── main.py                    # Entry point FastAPI
│   ├── api/
│   │   ├── main.py                # API Router
│   │   └── routes/
│   │       ├── chat.py            # Chat endpoints
│   │       ├── transactions.py    # Transaction CRUD
│   │       └── health.py          # Health checks
│   ├── core/
│   │   ├── config.py              # Settings (Pydantic)
│   │   ├── logging.py             # Structured logging
│   │   └── lifespan.py            # App lifecycle
│   ├── agents/
│   │   ├── graph.py               # LangGraph definition
│   │   ├── state.py               # AgentState
│   │   ├── nodes/
│   │   │   ├── orchestrator.py
│   │   │   ├── categorizer.py
│   │   │   ├── analyst.py
│   │   │   ├── planner.py
│   │   │   ├── recommender.py
│   │   │   ├── task_planner.py    # Complex path
│   │   │   ├── executor.py        # Complex path
│   │   │   ├── replanner.py       # Complex path
│   │   │   └── response_generator.py
│   │   └── tools/
│   │       ├── transaction_tools.py
│   │       ├── budget_tools.py
│   │       └── goal_tools.py
│   ├── modules/
│   │   ├── transactions/
│   │   ├── budgets/
│   │   ├── goals/
│   │   └── embeddings/
│   └── shared/
│       ├── interfaces/
│       └── clients/
├── tests/
├── docs/
│   ├── ARCHITECTURE.md
│   └── MODULE_STRUCTURE_GUIDE.md
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```
