# 8. Conclusiones y trabajo futuro

## 8.1. Conclusiones

El objetivo general de este trabajo era diseñar y desarrollar un asistente conversacional multiagente,
basado en IA Generativa, capaz de gestionar finanzas personales en lenguaje natural y de sustituir el
control manual en hojas de cálculo por una experiencia guiada. Ese objetivo se ha cumplido. Safi es
una aplicación funcional, desplegada en la nube y utilizable, que permite registrar, consultar,
corregir y analizar movimientos simplemente conversando, y que además puede partir de una imagen de la
propia hoja de cálculo del usuario para incorporar la información que ya tenía.

Los objetivos específicos se han alcanzado en su gran mayoría. Se implementó la arquitectura de agentes
con un clasificador y un agente ReAct; la gestión conversacional de transacciones, presupuestos, metas
y tarjetas; la categorización con soporte de categorías propias; la ingesta multimodal; la memoria a
corto y largo plazo; la autenticación y el aislamiento por usuario; la observabilidad y la
optimización de coste; el despliegue reproducible; y la interfaz web con chat y dashboard. Solo el
seguimiento de inversiones, contemplado en el anteproyecto, se dejó fuera para concentrar el esfuerzo
en el núcleo transaccional, y se recoge como línea futura.

Merece una reflexión la relación entre lo propuesto y lo entregado. El proyecto evolucionó respecto al
anteproyecto: cambió parte del stack tecnológico y simplificó la arquitectura de agentes, a la vez que
incorporó capacidades que no estaban previstas, como la ingesta por imagen, las categorías dinámicas o
el despliegue en producción. Lejos de ser una desviación, considero que esa evolución es uno de los
valores del trabajo, porque refleja decisiones tomadas con criterio a medida que el problema real se
entendía mejor.

En lo personal, este TFM ha sido especialmente satisfactorio porque resuelve una necesidad que vivo de
cerca. Safi no es solo un ejercicio académico: es una herramienta que mi familia puede empezar a usar
para llevar sus cuentas mejor de lo que lo hacíamos con el Excel, y una base sólida sobre la que seguir
construyendo. Poner al servicio de un problema cotidiano los conocimientos del máster (los modelos de
lenguaje, los agentes, RAG, la multimodalidad y las buenas prácticas de ingeniería) ha sido la mejor
forma de comprobar que esos conocimientos se han asentado.

## 8.2. Trabajo futuro

La solución deja varias líneas naturales de continuación, ordenadas aproximadamente por cercanía:

- **Notificaciones proactivas.** Convertir las alertas de presupuesto, hoy evaluadas al consultar, en
  avisos que lleguen al usuario cuando se cruza el umbral, mediante un proceso en segundo plano.
- **Seguimiento de inversiones.** Recuperar el módulo previsto en el anteproyecto para dar cabida a
  activos y su seguimiento.
- **Evaluación formal de la categorización.** Construir un conjunto etiquetado de descripciones para
  medir con rigor la precisión del categorizador y ajustarlo.
- **Integración bancaria.** Permitir la importación automática de movimientos desde entidades, cuando
  el contexto lo haga viable, para reducir aún más la entrada manual.
- **Gestión avanzada de categorías.** Ofrecer una administración de categorías propias con icono y
  color, más allá de su creación conversacional.
- **Aplicación móvil.** Llevar la experiencia a una app nativa, complementando la web responsive
  actual.
- **Privacidad reforzada.** Alojar la observabilidad en infraestructura propia si el uso se ampliara,
  para que ningún dato financiero salga del entorno controlado, e incorporar limitación de peticiones
  por usuario.
- **Análisis predictivo.** Añadir capacidades de previsión de gasto y recomendaciones más ricas a
  partir del historial del usuario.

En conjunto, estas líneas muestran que Safi, más que un punto final, es un punto de partida con
recorrido, tanto como herramienta personal como en su posible evolución hacia un producto.
