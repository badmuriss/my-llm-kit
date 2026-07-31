## Git workflow
- Do not include "Claude Code" in commit messages
- Use conventional commits (be brief and descriptive)

## Important concepts
Focus on these principles in all code:
- e2e type-safety
- error monitoring/observability
- automated tests
- readability/maintainability

All detailed coding guidelines are in the skills:
- Use `software-engineering` skill for core principles
- Use `typescript` skill for TypeScript/JavaScript standards
- Use `react` skill for React/Next.js best practices
- Use `reviewing-code` skill for code reviews
- Use `writing` skill for documentation and commit messages
- Use `scrapingdog` skill for scraping, Google Search/SERP, Google Maps, Google Trends, Google News, Amazon, LinkedIn, Instagram, market research, and lead enrichment when `SCRAPINGDOG_API_KEY` is available

## Escrita (prosa para humanos)
Todo texto em prosa destinado a leitores (post, newsletter, roteiro, caption, blog, e-mail, documento) passa pelo sistema da skill `unslop`:
- Gerar do zero: modo `escrever`. Revisar texto pronto: modo `editar`. Auditar sem alterar: modo `detectar`. Dar nota: modo `avaliar`.
- Texto em português carrega a camada pt-br da skill obrigatoriamente. A lista de tells em inglês não cobre o slop brasileiro.
- Regras da casa, em qualquer registro: nunca travessão (—/–), use vírgula, ponto ou dois pontos; "para" por extenso, nunca "pra"/"pro"/"pros"; sem hashtags em captions; frase-efeito vazia é banida, cada afirmação carrega substância concreta (dado, exemplo, mecanismo).
- Uma reescrita nunca introduz fato, nome, número ou data que não estava no original.

## Pesquisa
Nunca responder número, estatística ou superlativo de memória com cara de certeza. Antes de publicar qualquer dado, usar a skill `pesquisa`. Estas regras valem mesmo fora da skill:
1. Fonte primária na frente: documentação oficial e repositório antes de paper, paper antes de análise de terceiro. Blog agregador é pista, nunca destino final.
2. Divergência entre fontes é reportada com a data de cada uma, nunca resolvida em silêncio.
3. Padrão visto em menos de 5 casos entra como amostra fraca, jamais como conclusão.
4. Todo número, valor e superlativo sai com URL e data de acesso ao lado.

Documento recebido (PDF, planilha, deck, epub) passa pela skill `ingestao` antes de qualquer análise. PDF de duas colunas lido sem conversão gera conclusão embaralhada.
