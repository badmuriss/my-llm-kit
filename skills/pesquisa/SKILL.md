---
name: pesquisa
description: Conduz pesquisa com embasamento verificável, do levantamento de fonte primária até o achado auditável em markdown. Use quando o usuário pedir para pesquisar um tema, levantar evidência, checar um dado, comparar fontes, escrever relatório com citação, ou disser variações como "pesquisa isso", "de onde vem esse número", "isso é verdade?", "levanta os papers", "monta um relatório". Também use antes de publicar qualquer número, valor monetário ou superlativo.
---

# Pesquisa

Conduza a pesquisa em estações, na ordem. Não pule a ingestão nem a memória.

## As quatro regras inegociáveis

Aplique em toda pesquisa, sem exceção e sem esperar o usuário pedir.

1. **Fonte primária na frente.** Ordem de confiança: documentação oficial e repositório do projeto, depois publicação primária ou paper, depois análise de terceiro, e por último blog agregador, que serve apenas como pista para confirmar em outro lugar. Nunca encerre em blog agregador.
2. **Divergência é reportada, nunca resolvida em silêncio.** Quando duas fontes discordam, apresente as duas com a data de cada uma e diga qual é a primária. Escolher a mais conveniente sem avisar é falha grave.
3. **Amostra fraca é marcada.** Padrão observado em menos de cinco casos entra como "amostra fraca", jamais como conclusão.
4. **Saída auditável.** Todo número, valor monetário ou superlativo carrega a URL e a data de acesso ao lado. Sem isso, o dado não sai do rascunho.

## Estação 1: fontes

**Papers e literatura científica**: use o MCP `paper-search` para localizar material em arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex e Unpaywall. Peça sempre o DOI junto do título, porque o DOI sobrevive a link quebrado.

**Web geral**: siga a ordem de fallback do stack.
1. ScrapingDog (skill `scrapingdog`) é o scraper e SERP default quando `SCRAPINGDOG_API_KEY` existe no ambiente.
2. Firecrawl (skills `firecrawl-search` e `firecrawl-scrape`) é o fallback quando ScrapingDog não estiver disponível ou falhar.
3. WebSearch nativo só entra por último, quando os dois anteriores não resolverem.

**Tecnologia ou produto**: quando o tema for tecnologia em vez de ciência, a fonte primária é o repositório, a documentação oficial e o changelog do projeto. Contagem de stars, número de versão e preço devem ser lidos na página do próprio projeto, nunca em artigo de terceiro que cita o projeto.

**Pulso da comunidade (últimos 30 dias)**: quando a pergunta envolver sentimento atual, recepção de lançamento, reputação de pessoa ou empresa, ou "o que estão dizendo agora", rode o plugin `/last30days` (Reddit, Hacker News, X, Polymarket, GitHub, arXiv, Techmeme, pontuado por engajamento real). Duas ressalvas: engajamento mede relevância, não verdade, então afirmação factual achada ali ainda precisa de fonte primária; e todo dado que sair no relatório segue as quatro regras (URL + data ao lado). Reddit, HN, Polymarket, GitHub e arXiv funcionam sem chave; X, YouTube e TikTok são opt-in com chave própria.

## Estação 2: ingestão legível

Antes de ler qualquer documento, converta. Delegue para a skill `ingestao`, que roteia cada tipo de arquivo para o conversor certo.

Nunca analise um PDF de duas colunas sem converter antes. Ordem de leitura embaralhada gera conclusão embaralhada.

## Estação 3: protocolo

Antes de investigar, escreva no arquivo de saída:

- a pergunta exata, em uma frase
- o critério que decide a resposta, fixado agora e não depois
- o que falsificaria a hipótese

## Estação 4: investigação

Cruze as fontes convertidas. Registre no arquivo cada afirmação com a fonte correspondente enquanto pesquisa, não no final. Reconstruir a origem depois é onde o rastro se perde.

## Estação 5: memória

Salve o achado em markdown na pasta `pesquisa/` do projeto atual, ou onde o usuário pedir. Estrutura padrão:

- pergunta e critério, fixados antes da investigação
- achados, cada um com fonte e data
- divergências encontradas, com as duas versões
- o que ficou em aberto
- fontes consultadas, com URL e data de acesso

Insight durável sobre o negócio, que vale reaproveitar em pesquisas futuras, vai para o sistema de memória do Claude, não para o arquivo de pesquisa. O agente já sabe quando e como gravar lá.

## Estação 6: prova de fogo

Ao terminar, liste explicitamente para o usuário:

- quais afirmações vieram de fonte primária
- quais ficaram apoiadas apenas em fonte secundária
- quais números merecem reconfirmação por serem voláteis, como contagem de stars, preço e cargo

Para decisão de alto risco, sugira subir o mesmo conjunto de fontes no Gemini Notebook via a skill `notebooklm` como segunda leitura.

## Anti-padrões

- responder de memória sem abrir fonte, mesmo quando a resposta parece óbvia
- citar número redondo sem data
- apresentar consenso quando as fontes divergem
- deixar o achado morrer no chat sem virar arquivo

---

Adaptado de [research-stack](https://github.com/nett0eth/research-stack) (Netto, @nett0eth), licença MIT.
