# JOMIVO Events Feed
O site lê `events.json` automaticamente ao abrir e usa a agenda embutida apenas como fallback.

Formato:
`{"updated":"YYYY-MM-DD","events":[{"name":"","area":"Porto|Braga|Aveiro","city":"","type":"","start":"YYYY-MM-DD","end":"YYYY-MM-DD","date":"","desc":"","url":""}]}`

Produção: um job diário deve recolher apenas fontes oficiais, normalizar para este formato e substituir `events.json`. Eventos expirados devem ser removidos. Fontes-base:
- Agenda Porto / Ágora
- Câmara Municipal de Braga / Agenda Cultural
- Câmara Municipal de Aveiro / Agenda Aveiro
