# Research finding: entrevista, capacidades e roteamento adaptativo

## Protocol

- Question: Como o my-llm-kit deve combinar entrevista proporcional, complexidade da mudança e capacidades disponíveis para escolher execução direta, loop único, spec ou grafo, e quando especializar modelos reduz custo ou contexto sem reduzir confiabilidade?
- Decision criterion: O kit deve funcionar sem Orca e sem OpenSpec, pedir ao usuário somente informação que altere uma decisão material e promover especialização ou grafo apenas quando houver evidência de separação de trabalho, verificação e ganho mensurável.
- Falsifier: Esta recomendação falha se uma avaliação representativa mostrar que entrevista curta perde requisitos materiais que uma entrevista longa captura sem custo relevante, ou que o caminho degradado sem ferramentas opcionais não consegue executar e verificar as mesmas mudanças dentro de seu escopo.
- Risk: material

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Fallback reason |
|---|---|---|---|---|
| Literatura sobre clarificação e agentes de código | `paper-search` MCP | catálogo local | Indisponível: servidor declarado `disabled` e `Unsupported`. | Seguiu para ScrapingDog. |
| Literatura sobre clarificação, roteamento e coordenação | ScrapingDog | `GET /google_scholar` | Três consultas concluídas; a resposta devolveu alguns URLs úteis, mas títulos incompletos e muitos links de perfil. | Fontes primárias foram localizadas e abertas por URL. |
| Guias oficiais de arquitetura de agentes | OpenAI e Anthropic | abertura direta de guias e documentação | Concluído. | Nenhum. |
| Evidência empírica de clarificação em software engineering | arXiv | abertura direta dos preprints | Concluído. | Nenhum. |
| Evidência anterior sobre custo, grafos e contexto | finding local e fontes primárias já abertas | leitura de `2026-08-21-adaptive-harness-evidence.md` | Reutilizada como contexto, com suas fontes primárias. | Nenhum. |

## Claim ledger

| Claim | Source | Accessed | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|
| Modelos têm dificuldade de distinguir instruções bem especificadas de subespecificadas; interação direcionada melhora desempenho quando há informação faltante. | https://arxiv.org/abs/2502.13069 | 2026-08-21 | yes | yes | yes | unknown | accepted |
| Boa geração de código não implica boa identificação de ambiguidade; uma métrica de qualidade de pergunta deve penalizar turnos ineficientes. | https://arxiv.org/abs/2607.00711 | 2026-08-21 | yes | yes | yes | unknown | limited |
| Um scaffold que separa detectar subespecificação de executar código superou sua baseline de agente único em um SWE-bench Verified subespecificado. | https://arxiv.org/abs/2603.26233 | 2026-08-21 | yes | yes | yes | unknown | limited |
| O guia oficial da OpenAI recomenda começar com um agente e evoluir para múltiplos somente quando necessário; oferece lógica complexa e sobrecarga de ferramentas como sinais de divisão. | https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/ | 2026-08-21 | yes | yes | yes | unknown | accepted |
| A OpenAI descreve um padrão de manager central que preserva controle e síntese ao delegar capacidades especializadas. | https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/ | 2026-08-21 | yes | yes | yes | unknown | accepted |
| Gateways podem centralizar limites de gasto, auditoria, atribuição de uso e troca de provider, mas não provam que qualquer roteamento melhora resultado. | https://code.claude.com/docs/en/llm-gateway | 2026-08-21 | yes | yes | yes | unknown | accepted |
| O caso Hebbia relata roteamento por modelo e processamento paralelo para pesquisa documental de alto valor, mas é estudo de caso comercial e não mede um kit de coding genérico. | https://openai.com/index/hebbia/ | 2026-08-21 | yes | yes | partial | unknown | limited |
| A recomendação de usar terminais separados para documentação, execução rápida e auditoria como ganho universal de custo ou confiabilidade não possui evidência comparativa geral aberta. | https://www.anthropic.com/engineering/multi-agent-research-system | 2026-08-21 | yes | partial | yes | unknown | rejected |
| O paralelismo de pesquisa e leitura pode justificar subagentes, mas escrita de código com dependências continua menos paralelizável e mais cara em tokens. | https://www.anthropic.com/engineering/multi-agent-research-system | 2026-08-21 | yes | yes | yes | unknown | accepted |
| Preservar prefixos idênticos pode reduzir custo de cache, mas fan-out não é automaticamente mais barato porque também duplica contexto e pode gerar escritas de cache. | https://developers.openai.com/api/docs/guides/prompt-caching | 2026-08-21 | yes | yes | yes | unknown | accepted |
| A portabilidade entre máquinas e hosts exige separar contrato do harness de adapters de provider, e tratar capacidade e configuração de provider como dados observáveis. | https://github.com/badmuriss/my-llm-kit/blob/main/README.md | 2026-08-21 | yes | yes | yes | unknown | accepted |

## Findings

### Você está certo sobre a forma do produto

O harness deve ser capability-first para instalar e process-first para decidir trabalho. Em outras palavras, a escolha de **modo de trabalho** não pode depender de ter Orca, OpenSpec, Canvas ou um provider específico. A escolha de **perfil de execução** depende do que existe no ambiente. Misturar as duas decisões é a origem da fragilidade que você descreveu.

| Decisão | Pergunta | Resultado |
|---|---|---|
| Modo de trabalho | Quanto há de ambiguidade, risco, acoplamento, validação e paralelismo real? | direto, loop único, spec leve ou grafo. |
| Perfil de execução | Quais capacidades existem e foram verificadas? | local mínimo, spec disponível, grafo host, ou grafo com Orca. |

Assim, um usuário sem nada além de shell e um agente ainda pode executar Modo 0 ou 1: ler o repositório, fazer a mudança, rodar o menor check e reportar evidência. Sem OpenSpec, uma spec leve é Markdown comum e não bloqueia a mudança. Sem Orca, um grafo aprovado pode usar o driver Host. Com Orca, ganha-se supervisão e lifecycle mais rico, mas Orca é aceleração, não pré-requisito. Uma capacidade ausente deve produzir um receipt de degradação e uma alternativa explícita, nunca um erro implícito ou uma mudança secreta de rigor.

### Portabilidade é um requisito de arquitetura, não uma conveniência

Você está descrevendo dois tipos de portabilidade, ambos necessários:

| Tipo | O que precisa sobreviver | O que não pode virar dependência do núcleo |
|---|---|---|
| Máquina e sistema operacional | instruções, skills, políticas, contratos, checks, memória revisada e instalação idempotente | caminho absoluto local, terminal específico, credential, daemon, worktree ou banco de runtime de uma máquina. |
| Host e fornecedor | mesma intenção, modo, capsule, ownership, evidência, orçamento e resultado aceito | sintaxe de um CLI, identificador de modelo, API privada, Canvas ou semântica de sessão de um host. |

O README atual já expressa esse rumo: skills vivem uma vez em uma raiz compartilhada, os hosts recebem links ou cópias gerenciadas, e Host e Orca compartilham contratos de grafo. A conclusão é estender o mesmo princípio a todo o selector adaptativo. Fonte primária local publicada, acessada em 2026-08-21: https://github.com/badmuriss/my-llm-kit/blob/main/README.md.

O núcleo portátil deve falar apenas em capacidades, não em marcas: `can_run_check`, `can_create_isolated_workspace`, `can_dispatch_visible_worker`, `can_read_usage`, `can_cache_prefix`, `can_ask_user`, `can_cleanup_process_tree`. Cada host, CLI ou tendência nova implementa um adapter que declara o que suporta, como verifica a capacidade e como degrada. O selecionador escolhe o modo a partir do trabalho e escolhe o adapter a partir das capacidades. Ele nunca precisa saber se o adapter se chama Claude Code, Codex, OpenCode ou algo lançado amanhã.

Isso também impede lock-in de modelo. O contrato de um papel deve descrever raciocínio necessário, contexto máximo, ferramentas, risco, formato de retorno, check e orçamento, não “use o modelo X”. O catálogo do ambiente resolve um modelo disponível e registra o motivo. Trocar de fornecedor então muda resolução e telemetria, não muda a semântica da tarefa, do check nem do journal. Se um host não oferece a capacidade, o kit reduz para um perfil compatível ou informa a limitação antes de começar.

Portabilidade não significa uniformizar tudo até o menor denominador comum. Significa ter um núcleo mínimo que funciona em toda parte e extensões que melhoram a experiência onde existirem. Orca pode acrescentar terminal supervisionado e Canvas. OpenSpec pode acrescentar schema, validação e durabilidade. Um host pode acrescentar cache ou telemetria de custo. Nenhuma dessas extensões pode ser necessária para alterar um arquivo, rodar um check ou produzir uma evidência honesta.

### A entrevista é necessária, mas não deve ser o Grill Me

Sua crítica ao `grill-me` atual é correta. O próprio `spec` local já diz para chamar `grill-me` somente quando uma decisão não resolvida do dono muda comportamento, arquitetura ou escopo. Mas o `grill-me` se descreve como entrevista implacável de toda a árvore de decisões. Há uma incompatibilidade de produto: o primeiro é um gate proporcional; o segundo é uma ferramenta de stress test voluntária.

Pesquisa recente sustenta uma entrevista **cirúrgica**. Ambig-SWE encontrou que modelos têm dificuldade em saber sozinhos quando a instrução está incompleta, e que interação fornece informação vital em entradas subespecificadas. Fonte primária, acessada em 2026-08-21: https://arxiv.org/abs/2502.13069. ClarifyCodeBench reforça que desempenho de código e capacidade de detectar ambiguidade são capacidades distintas e mede qualidade de pergunta com penalidade para turnos desnecessários. É um preprint recente, portanto a generalização é limitada. Fonte primária, acessada em 2026-08-21: https://arxiv.org/abs/2607.00711.

O mecanismo recomendado não é “pergunte até não haver dúvida”. É uma triagem de valor de informação:

1. Inspecionar antes o pedido, repositório, instruções, código, histórico e contratos. Não perguntar o que o ambiente responde.
2. Formular a menor mudança plausível e listar somente incertezas que podem mudar comportamento, escopo, risco, interface, dado persistido, custo externo ou modo de execução.
3. Para cada incerteza, perguntar: “se a resposta for A ou B, a ação muda?”. Se não mudar, assumir, declarar a suposição e seguir.
4. Se mudar, perguntar uma questão concreta, preferencialmente já com a recomendação e as consequências. Agrupar somente questões independentes.
5. Parar a entrevista quando não restar incerteza material. O usuário também deve poder declarar “assuma a opção segura e implemente”.

Essa triagem permite perguntas como “o Canvas precisa persistir posições entre máquinas, ou apenas no workspace local?”, pois cada resposta muda storage, identidade e risco. Ela elimina perguntas como “qual seu estilo de documentação?”, se o repositório já define o padrão e a resposta não muda a aceitação.

O preprint Ask or Assume? é uma confirmação útil, mas limitada: ao separar detector de subespecificação da execução, reportou 69,40% contra 61,20% de resolução em uma variante subespecificada de SWE-bench Verified, acessado em 2026-08-21: https://arxiv.org/abs/2603.26233. A conclusão prática não é adicionar um agente para toda tarefa. É transformar detecção de ambiguidade em gate curto antes de escolher o modo.

### Quando seus dois exemplos merecem grafo

**Redesenho com auditoria e loop de melhoria.** Sim, é um bom candidato, mas o grafo deve representar trabalho verificável, não fases performáticas. O núcleo de produto e a decisão de design devem continuar sob um responsável ou integrador. Em paralelo, podem existir: pesquisa de referências, baseline de métricas, implementação em paths isolados, auditoria independente e coleta de evidência. O loop só é útil se você definir antes a baseline, as métricas, o orçamento de tentativas e o que conta como regressão. Sem isso, “auditar e melhorar” vira uma conversa de agentes sem oráculo.

**Canvas infinito que toca vários sistemas.** Também é candidato forte a spec leve ou completa seguida de grafo, porque há contratos entre Canvas, runtime, lifecycle, estado e execução. O grafo entra depois que a entrevista e a spec congelarem apenas as interfaces de fronteira. A partir daí, os pacotes precisam ter ownership não sobreposto, como schema e lifecycle, bridge de execução, UI Canvas e checks de integração. Uma pessoa ou agente integrador deve manter as decisões transversais. Não se deve paralelizar duas interpretações de identidade, persistência ou semântica de cleanup.

**Pesquisa.** É o melhor uso do grafo, desde que coletores sejam somente leitura e a adjudicação continue central. Pesquisa naturalmente separa fonte oficial, artigo, implementação local e contraditório. Porém, a síntese precisa de uma pessoa responsável por abrir as fontes e resolver conflito. Esta regra já aparece na skill `research` do kit.

Isso coincide com o guia oficial da OpenAI: começar por agente único, separar quando lógica e ferramentas já não são claras, e usar um manager central quando é necessário preservar controle e síntese. Fonte oficial, acessada em 2026-08-21: https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/. Também coincide com o relato da Anthropic: pesquisa larga encaixa bem em múltiplos agentes; coding com dependências, em geral, não. Fonte oficial, acessada em 2026-08-21: https://www.anthropic.com/engineering/multi-agent-research-system.

### Terminais e modelos especializados: hipótese boa, não garantia

A divisão que você descreve tem mérito se a responsabilidade for objetiva e o retorno for verificável:

| Responsabilidade | Perfil útil | Regra de segurança |
|---|---|---|
| Busca e triagem de fontes | barato, rápido, somente leitura | Não aceita conclusão; devolve URLs, datas e trechos localizáveis. |
| Comando determinístico ou coleta mecânica | rápido e barato | Só passa com exit code e artefato esperado; não interpreta qualidade. |
| Implementação coesa | modelo mais capaz necessário, um escritor | Executa checks e conserva decisões de arquitetura. |
| Auditoria ou revisão adversarial | contexto limpo e independente | Não altera o trabalho avaliado; aponta evidência que o integrador verifica. |
| Integração e decisão | modelo com contexto suficiente ou humano | É dono da síntese, das emendas e da aceitação. |

Há duas correções essenciais. Primeiro, o terminal não é a unidade de confiabilidade. O contrato é: input delimitado, permissões, ownership, orçamento, output estruturado e check. Um terminal dedicado sem esses limites apenas fragmenta contexto.

Segundo, economia de token é uma hipótese a medir por classe de tarefa. A Anthropic reporta aproximadamente 15x tokens de chat para seu sistema multiagente de pesquisa, acessado em 2026-08-21: https://www.anthropic.com/engineering/multi-agent-research-system. Cache pode reduzir parte do custo quando o prefixo permanece exatamente igual, mas conteúdo, ordem e configurações precisam coincidir. Fonte oficial, acessada em 2026-08-21: https://developers.openai.com/api/docs/guides/prompt-caching. Logo, um modelo rápido para tarefas determinísticas e um modelo forte para síntese pode reduzir custo, mas múltiplos agentes podem também gastar muito mais por duplicar instruções, ferramentas e contexto.

O caso Hebbia mostra que roteamento por modelo e execução paralela podem ter valor em pesquisa documental de alto valor. Não é prova para coding generalista: é estudo de caso comercial em finanças e direito. Fonte oficial, acessada em 2026-08-21: https://openai.com/index/hebbia/. O kit deve tornar roteamento uma política auditável por papel, risco, ferramentas e check, e comparar custo, tempo e resultado aceito antes de transformá-lo em default. Gateways ajudam a impor orçamento, logs e troca de provider, mas não substituem essa avaliação. Fonte oficial, acessada em 2026-08-21: https://code.claude.com/docs/en/llm-gateway.

### Proposta concreta de produto

1. Criar uma entrada única de “intake adaptativo”, que funciona em qualquer instalação. Ela inspeciona primeiro, aplica a triagem de perguntas, classifica o modo e escolhe o perfil disponível.
2. Fazer `grill-me` virar ferramenta explícita de stress test, nunca etapa automática. Criar ou incorporar uma entrevista curta, com orçamento de perguntas e o teste “a resposta muda a ação?”.
3. Manter dois artefatos pequenos em todos os modos acima do direto: `decision capsule` com objetivo, suposições e check; e `capability receipt` com as capacidades encontradas, ausentes e o fallback usado.
4. Tratar OpenSpec como upgrade de durabilidade para Modo 2 e 3, não como requisito. Sem ele, usar a mesma estrutura em Markdown local e checks comuns.
5. Tratar Orca como upgrade de supervisão para Modo 3, não como requisito. O Host continua o caminho funcional equivalente, com a degradação visível.
6. Antes de permitir grafo, exigir uma tabela de pacotes: objetivo, read/write, path ou ambiente, decisão compartilhada, check, integração e cleanup. Se dois pacotes responderem “decisão compartilhada”, eles não são paralelos ainda.
7. Para redesenhos e loops de melhoria, exigir baseline, métrica, janela de comparação, orçamento e decisão de parada. O gráfico mostra o experimento; não substitui sua definição.
8. Rodar roteamento de modelos em shadow mode: registrar papel, modelo, custo, cache, duração, retries, check e resultado aceito. Promover um perfil somente após comparação repetida em tarefas do kit.
9. Definir um schema de `capability manifest` e adapters por host. O manifest deve ser o único lugar que conhece comandos, limites e degradações de Codex, Claude Code, OpenCode, Orca ou qualquer sucessor.
10. Manter contratos, capsules, specs leves, checks e evidence grades provider-agnostic. Migração de máquina ou host deve exigir instalação e reconciliação de capacidades, não reescrita de processo ou de conhecimento do projeto.

## Disagreements

- OpenAI recomenda começar com um agente e dividir por lógica complexa ou sobrecarga de ferramentas. Ask or Assume? reporta ganho de um scaffold multiagente para uma variante subespecificada de SWE-bench. As fontes não se contradizem: a segunda fornece precisamente uma condição de escalonamento, subespecificação detectável e pergunta útil. https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/ e https://arxiv.org/abs/2603.26233, accessed 2026-08-21.
- Anthropic relata alto custo de multiagente e menor paralelismo para coding. O caso Hebbia relata valor com modelos múltiplos para pesquisa documental de alto valor. Tarefa, valor, contexto e métrica são diferentes; o caso comercial não generaliza para implementação de software. https://www.anthropic.com/engineering/multi-agent-research-system e https://openai.com/index/hebbia/, accessed 2026-08-21.

## Open questions

- Qual é o conjunto mínimo de perguntas de alto valor para categorizar mudanças de UI, dados, integração externa e arquitetura no my-llm-kit?
- Como representar uma `decision capsule` portável sem introduzir outra spec obrigatória?
- Quais métricas do redesenho de Lupalids já existem e qual é o baseline que permitiria avaliar uma iteração sem subjetividade?
- Quais contratos de fronteira do Canvas infinito podem ser definidos antes do grafo, e quais precisam emergir de um spike único?
- Quais providers expõem tokens de cache, custo e modelo resolvido de forma suficiente para comparar roteamento na prática?

## Council review

- Status: not run
- Reason: risco material, mas as conclusões usam fontes primárias e as divergências são condicionais, não desacordo direto sobre a mesma tarefa e métrica.
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://arxiv.org/abs/2502.13069, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2502.13069.
- https://arxiv.org/abs/2607.00711, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2607.00711.
- https://arxiv.org/abs/2603.26233, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2603.26233.
- https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/, accessed 2026-08-21.
- https://code.claude.com/docs/en/llm-gateway, accessed 2026-08-21.
- https://openai.com/index/hebbia/, accessed 2026-08-21.
- https://www.anthropic.com/engineering/multi-agent-research-system, accessed 2026-08-21.
- https://developers.openai.com/api/docs/guides/prompt-caching, accessed 2026-08-21.
- https://github.com/badmuriss/my-llm-kit/blob/main/skills/spec/SKILL.md, accessed 2026-08-21.
- https://github.com/badmuriss/my-llm-kit/blob/main/research/2026-08-21-adaptive-harness-evidence.md, accessed 2026-08-21.

## Trial by fire

- Primary-source claims: a utilidade de interação para requisitos subespecificados, o limite de modelos em detectar ambiguidade, a orientação de começar simples, a condição para dividir agentes, os controles de gateway, a cautela sobre custo multiagente e a semântica de cache.
- Secondary-only claims: None. Snippets de busca e resposta do ScrapingDog foram usados apenas para descoberta.
- Volatile claims: disponibilidade de MCP, providers, modelos, preços, telemetria e interfaces de gateway. Confirmar no ambiente antes de cada execução.
