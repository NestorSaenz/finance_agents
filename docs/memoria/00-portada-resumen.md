# 0. Portada, resumen y agradecimientos

## Portada

**Máster en Ingeniería y Desarrollo de Soluciones de IA Generativa**

**Trabajo Final de Máster**

**Safi: asistente conversacional multiagente para la gestión de finanzas personales**

Autor: Néstor Raúl Sáenz Chajín

Tutor de contenidos: `[NOMBRE DEL TUTOR]`

Repositorio del proyecto: `[URL DEL REPOSITORIO GIT]`

Fecha: `[MES] de 2026`

---

## Resumen

La gestión de las finanzas personales sigue apoyándose, en muchos hogares, en hojas de cálculo que
exigen constancia, imponen estructuras rígidas y no ofrecen ninguna lectura inteligente de los datos.
A partir de esa necesidad, vivida en el propio entorno familiar del autor, este Trabajo Final de
Máster presenta Safi, un asistente conversacional para la gestión de finanzas personales basado en IA
Generativa. Safi permite registrar, consultar, corregir y analizar movimientos económicos escribiendo
en lenguaje natural, y admite además la carga de una imagen de la hoja de cálculo del usuario para
extraer de ella la información de forma asistida.

La solución se articula en torno a una arquitectura de agentes orquestada con LangGraph, que combina
un clasificador de intención económico con un agente de razonamiento y acción (ReAct) capaz de invocar
herramientas sobre datos reales. Se apoya en modelos de lenguaje de gran tamaño (Gemini, a través de
Vertex AI, con un respaldo en Groq), en la generación aumentada por recuperación (RAG) para la
categorización, y en capacidades multimodales para la ingesta por imagen. El sistema incorpora memoria
conversacional, autenticación con aislamiento por usuario, observabilidad de coste y comportamiento, y
un despliegue reproducible en Google Cloud Run.

El resultado es una aplicación funcional y desplegada, verificada mediante pruebas automatizadas y
validada con uso real, que demuestra cómo la IA Generativa puede sustituir el registro manual por una
experiencia conversacional útil y de bajo coste.

**Palabras clave:** IA Generativa, modelos de lenguaje, agentes, ReAct, RAG, multimodalidad, finanzas
personales, LangGraph.

---

## Abstract

Managing personal finances still relies, in many households, on spreadsheets that demand discipline,
impose rigid structures and offer no intelligent reading of the data. Motivated by this need,
experienced first-hand in the author's own family, this Master's Thesis presents Safi, a conversational
assistant for personal finance management based on Generative AI. Safi lets users record, query,
correct and analyse their transactions using natural language, and it also accepts an image of the
user's spreadsheet to extract that information in an assisted way.

The solution is built around an agent architecture orchestrated with LangGraph, combining a lightweight
intent classifier with a reasoning-and-acting (ReAct) agent that invokes tools over real data. It
relies on large language models (Gemini, through Vertex AI, with a Groq fallback), on
retrieval-augmented generation (RAG) for categorisation, and on multimodal capabilities for image
ingestion. The system includes conversational memory, authentication with per-user data isolation,
cost and behaviour observability, and a reproducible deployment on Google Cloud Run.

The result is a functional, deployed application, verified through automated tests and validated with
real use, showing how Generative AI can replace manual bookkeeping with a useful, low-cost
conversational experience.

**Keywords:** Generative AI, large language models, agents, ReAct, RAG, multimodality, personal
finance, LangGraph.

---

## Índice

*(En el documento final, generar el índice automáticamente: en Google Docs, Insertar → Tabla de
contenido, tras haber marcado los títulos con los estilos Título 1 / Título 2.)*

---

## Agradecimientos

`[Opcional y personal. Ejemplo para adaptar:]`

A mi familia, que inspiró este proyecto y fue su primera usuaria. A mi tutor, por su
acompañamiento a lo largo del desarrollo. Y a los compañeros y docentes del máster, por lo aprendido
durante este tiempo.
