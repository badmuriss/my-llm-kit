# Auditoria do harness: contexto, proporcionalidade, portabilidade e unlazy

Nota: este diagnóstico registra o estado anterior à implementação autorizada em seguida. As mudanças estão descritas no [README atual](../README.md); as verificações e limites estão no [registro de validação](sources/2026-09-06-harness-audit/implementation-validation.json).

O harness tem mecanismos úteis, mas acumula processo em pontos onde deveria apenas orientar uma decisão. A prioridade é corrigir a instalação e o intake, depois reduzir a ativação de instruções e separar o caminho comum da orquestração. Não recomendo instalar `unlazy` por cima do runtime atual.

## Protocol

- Question: O harness atende tarefas de diferentes escopos, contextos e agentes sem impor processo desnecessário, e a unlazy acrescenta valor?
- Decision criterion: falhas reproduzíveis, conflitos de instrução, dependências ausentes e custo contextual observável; preservar invariantes que evitam falhas concretas.
- Falsifier: uma condição de entrada, resolução de dependência ou comportamento executável que elimine o problema apontado.
- Risk: material
- Credits used: 1

Data de inspeção: 2026-09-06. Fonte local: checkout `c276d1a8a943889e7f847c36f16d2bf6b30cd94f`, com mudanças preexistentes em `agent_graph.py` e `test_agent_graph_cli.py`, preservadas. O [manifesto local](sources/2026-09-06-harness-audit/corpus-manifest.json) registra arquivos e hashes.

O artigo foi fornecido como texto, sem URL, autoria ou imagens. Uso suas recomendações como critérios de auditoria, não como prova de comportamento ou superioridade de um modelo. A `skill-creator` fornecida pelo usuário sustenta os critérios de descoberta precisa, divulgação progressiva, respeito ao escopo e proporcionalidade.

Escopo executado: leitura dos entrypoints das skills versionadas, instruções globais, instaladores, manifesto, caminhos relevantes do intake e runtime; inventário dos metadados globais; inspeção dirigida das skills instaladas que competem pelos mesmos pedidos; leitura da unlazy fixada por commit e verificações locais focadas. Não foi feita revisão linha a linha de todos os scripts ou de todo o conteúdo das skills globais, auditoria de memórias privadas, benchmark de modelos ou certificação de segurança.

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Harness atual | local | arquivos, symlinks, histórico identificado e reproduções | evidências do checkout e instalação local | 0 | None |
| Critérios editoriais | user | artigo e skill-creator fornecidos | critérios disponíveis; autoria do artigo não verificada | 0 | None |
| Ler unlazy | ScrapingDog | /scrape, dynamic=false | página GitHub obtida e aberta | 1 | MCP ScrapingDog não exposto nesta sessão; helper HTTP existente |
| Fixar e inspecionar código | GitHub | API de commit/tree e raw por SHA | fontes primárias salvas e abertas | 0 | complemento direto da fonte, sem fallback de busca |

Crédito obtido pela diferença das consultas sanitizadas de conta antes/depois. Não houve busca de papers: esta auditoria não depende de validar alegações científicas sobre raciocínio. Não houve fallback para Firecrawl ou busca nativa.

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| O intake converte a frase condicional sobre compatibilidade em required | https://github.com/badmuriss/my-llm-kit/blob/c276d1a8a943889e7f847c36f16d2bf6b30cd94f/skills/agent-graph/scripts/adaptive_intake.py | 2026-09-06 | sources/2026-09-06-harness-audit/intake-reproduction.json | yes | yes | yes | unknown | accepted |
| O manifesto reduzido omite agent-graph, chamado por spec e impl | https://github.com/badmuriss/my-llm-kit/blob/c276d1a8a943889e7f847c36f16d2bf6b30cd94f/install-manifest.json | 2026-09-06 | sources/2026-09-06-harness-audit/reduced-install-reproduction.json | yes | yes | yes | unknown | accepted |
| A unlazy atual exige gates e passes, mas exclui tarefas triviais | https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/SKILL.md | 2026-09-06 | sources/2026-09-06-harness-audit/unlazy/raw/SKILL.md | yes | yes | yes | unknown | accepted |
| O próprio projeto não oferece os artefatos para reproduzir sua comparação histórica | https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/research/validation-protocol.md | 2026-09-06 | sources/2026-09-06-harness-audit/unlazy/raw/research/validation-protocol.md | yes | yes | yes | unknown | accepted |

## Findings

### Problemas prioritários

**[Alta, reproduzido] O intake interpreta uma pergunta como política vigente.**

Em [`adaptive_intake.py:43`](../skills/agent-graph/scripts/adaptive_intake.py), `inspect_repository` busca substrings, incluindo `backward compatibility is required`. Essa substring aparece em [`AGENTS.md:62`](../AGENTS.md) dentro de uma instrução condicional para perguntar ao usuário. O resultado real para este repositório é `compatibility: required`, apesar da preferência explícita por mudança incompatível em MVP. Uma fixture contendo apenas a frase condicional produz o mesmo resultado. `_material_questions` pode consumir esse resultado como fato e dispensar a pergunta.

Correção proposta: não inferir autorização ou política de compatibilidade de substring em prosa. Preservar como desconhecido quando não houver declaração inequívoca, ou aceitar um sinal explícito com proveniência. Não ampliar uma lista de palavras-chave para tentar interpretar linguagem natural. Evidência: [reprodução](sources/2026-09-06-harness-audit/intake-reproduction.json).

**[Alta, reproduzido no caminho de cópia] A instalação reduzida não fecha suas dependências.**

[`install-manifest.json`](../install-manifest.json) instala `spec` e `impl`, mas não `agent-graph`. Ambas mandam executar esse runtime. A execução isolada da função de cópia de [`install.sh:41`](../install.sh), com o manifesto atual, termina sem erro e deixa o entrypoint ausente. Não executei os instaladores externos via npm: eles não são um contrato declarado para fornecer esse runtime privado.

Correção proposta: incluir a dependência no pacote reduzido ou retirar a dependência do caminho comum; adicionar um smoke test em diretório limpo que execute a capacidade instalada. Conferir apenas se a skill está visível não valida que ela funciona. [Evidência](sources/2026-09-06-harness-audit/reduced-install-reproduction.json).

**[Alta, instrução não portátil] Comandos pressupõem que o projeto consumidor seja o próprio my-llm-kit.**

[`spec`](../skills/spec/SKILL.md), [`impl`](../skills/impl/SKILL.md) e [`research`](../skills/research/SKILL.md) usam `python3 skills/agent-graph/scripts/agent_graph.py`. A instalação global coloca skills em outro diretório. Em um projeto arbitrário, esse caminho relativo não existe. O runtime já distingue o projeto por `--repo` e `AGENT_GRAPH_PROJECT_DIR` em [`runtime_config.py`](../skills/agent-graph/scripts/runtime_config.py); a instrução não comunica consistentemente essa separação.

Correção proposta: resolver o executável a partir da skill instalada e passar separadamente o diretório do projeto. Manter o caminho absoluto congelado durante um run já é uma boa prática do bootstrap; o problema aparece antes dele.

**[Alta, fronteira de conclusão] Graph pode parar porque o host não oferece uma nova sessão visível.**

[`impl`, Bootstrap](../skills/impl/SKILL.md) exige um coordenador novo, proíbe usar subagente como coordenador e manda imprimir uma invocação e parar quando o host não oferece handoff visível. A exceção exige declaração explícita do dono de que a sessão atual é o coordenador novo.

Isso é uma limitação de portabilidade do fluxo, mesmo com um core Host sem dependência de Orca. Não é prova de defeito no fencing do runtime. Correção proposta: permitir que a sessão atual assuma coordenação quando consegue cumprir ownership, geração e orçamento de contexto; exigir handoff apenas quando isolamento contextual ou capacidade realmente demandarem isso. Não remover fencing, reconciliação ou proteção contra coordenadores simultâneos.

**[Alta, acúmulo de processo] O fechamento de impl não separa claramente os modos leves do graph.**

O início promete mudança local e check nos modos leves. O bloco `Finish` volta a ordenar `thermo-nuclear-code-quality-review`, `digest`, cleanup e `complete`, sem delimitar todos esses comandos a graph. Há ambiguidade para uma edição simples e chamadas sem run correspondente. O gate de complexidade também aparece tanto em impl quanto na revisão especializada.

Correção proposta: encerramento explícito para os modos leves; seção graph em referência própria; revisão independente apenas quando o risco, o diff ou o pedido justificar. Reutilizar a evidência do mesmo diff em vez de repetir checks sem alteração. Não abolir revisão ou testes.

### Descoberta e custo de contexto

O diretório versionado contém **15 entrypoints**, enquanto o diretório global inspecionado contém **84**. O somatório dos campos brutos de descrição é **4.414 caracteres** no repositório e **33.712** no global. São contagens de texto, incluindo sintaxe YAML capturada, não tokens nem medição do prompt real. Fontes: [inventário local](sources/2026-09-06-harness-audit/inventory-repo.json), [inventário global](sources/2026-09-06-harness-audit/inventory-global.json), accessed 2026-09-06.

Isso não significa que todos os corpos sejam carregados em toda tarefa. Há camadas diferentes: catálogo disponível, seleção da skill e leitura de referências. Nesta sessão algumas descrições expostas já aparecem interrompidas; não medi o limite do host nem atribuo todo truncamento ao kit. Há também skills de sistema e plugins fora do diretório global inventariado.

**[Média] Instalação ampla aumenta a disputa no catálogo.** [`setup.sh:304`](../setup.sh) instala todos os diretórios versionados e o fan-out distribui também skills que já estavam na raiz compartilhada. O manifesto instala famílias de design e pesquisa por padrão. O kit não criou todas as skills globais, mas participa da distribuição indiscriminada. Recomendo um núcleo pequeno e pacotes opcionais por capacidade. Não mudar `allow_implicit_invocation` de skills existentes sem decisão explícita do usuário; melhorar descrição e seleção do pacote já reduz ruído.

**[Média] Há roteadores concorrentes para a mesma tarefa.**

| Pedido | Sobreposição observada | Ajuste recomendado |
|---|---|---|
| Corrigir CSS de componente existente | refero-design se declara padrão, incredibly-pretty-websites também cobre visual, frontend-visual-validation exige evidência | preservar a autoridade do componente existente; pesquisa de direção só quando faltarem referências relevantes |
| Criar imagem | imagegen do sistema e image-gen global | ferramenta nativa quando disponível; adaptador CLI apenas quando necessário |
| Escrever código React | coding-guidelines, typescript, react e vercel-react-best-practices | uma base de convenções; referências de performance ou framework conforme o problema |
| Ler fonte pública | research, scrapingdog e firecrawl | research decide profundidade; um roteador decide provedor; adaptadores executam |
| Ler documento | ingest, firecrawl-parse e skills do formato | extração quando necessária; skill do formato para edição e preservação estrutural |
| Preparar apresentação | pptx, frontend-slides e hyperframes | selecionar pelo formato e movimento pedidos, sem assumir que todo deck é vídeo |

Fontes instaladas estão registradas no inventário global. A inspeção foi de metadados e trechos de roteamento, não revisão integral de cada pacote.

**[Média] Entry points grandes não aplicam bem divulgação progressiva.** O `incredibly-pretty-websites` instalado tem **102.217 caracteres** no entrypoint; `rule-curator` tem **15.463** e `research`, **12.931**. Fonte: [inventários](sources/2026-09-06-harness-audit/inventory-global.json), accessed 2026-09-06. Não proponho um teto arbitrário: mover modos, exemplos, preços e contratos específicos para referências selecionadas. A skill de websites já diferencia `local`, `surface` e `world`, o que deve ser preservado; ainda assim, seu corpo exige muita leitura para usar essa distinção.

**[Média] Research aplica um protocolo de pesquisa formal a fatos pequenos.** Sua descrição pode ativar por qualquer número ou superlativo. O corpo manda cumprir estações, consultas de créditos, snapshots, ledger, formato fixo e validação. A coleta delegada ainda é descrita como pacote Agent Graph. Para uma URL conhecida, isso pode custar mais que a verificação.

Correção proposta: separar consulta factual, pesquisa comparativa e pesquisa de alto risco. Uma consulta factual precisa da fonte aberta e de limites de certeza; não necessariamente de pasta de pesquisa, grafo ou consulta de saldo. Manter rastreabilidade completa para relatórios como este. As instruções de provedores também precisam resolver a prioridade explícita de ScrapingDog contra a descrição de Firecrawl que se oferece para qualquer trabalho web.

### AGENTS.md e fronteiras

**[Média] A mesma política global também é a política do projeto.** Os arquivos `~/.agents/AGENTS.md`, `~/.codex/AGENTS.md` e `~/.claude/CLAUDE.md` resolvem para o `AGENTS.md` deste checkout. O contexto fornecido nesta conversa mostra o texto global e o de projeto repetidos. Isso sustenta duplicação nesta sessão; não prova que todo host deixe de deduplicar.

Correção proposta: separar instruções globais das instruções específicas de desenvolvimento do kit. Globais guardam preferências duráveis; o projeto registra comandos, limites e invariantes próprios. Não duplicar o corpus para manter uma “fonte única”.

**[Média] Há políticas locais espalhadas e exemplos contraditórios.**

- AGENTS manda conventional commits; `writing` exemplifica commits sem tipo convencional. Corrigir exemplos, mantendo a regra do dono.
- A escada de modelos aparece em AGENTS, referências e seed de roteamento. Guardar candidatos e esforço no catálogo/política; deixar no global apenas a preferência por custo proporcional. Não avaliei se algum modelo é melhor ou mais barato no mercado atual.
- AGENTS traz nomes de subagentes OpenCode específicos desta máquina; o setup não provisiona esses perfis. Eles existem aqui, mas isso não garante instalação limpa. Distinguir personalização local de capacidade distribuída.
- `ingest` amplia a conversão para repositórios inteiros e obriga delegação mecânica. Para um README Markdown conhecido, leitura direta é suficiente. Preservar a verificação de ordem e tabelas em documentos difíceis.
- `readme-pass` manda preparar staging e sugere uma estética específica de banner. Um pedido de clareza textual não autoriza automaticamente reorganizar o índice Git nem estabelecer identidade visual. Tornar esses passos condicionais ao pedido.
- `trim-code-comments` pede uma seleção adicional, exceto quando a remoção imediata foi explícita. Tratar “remova os comentários redundantes” como autorização existente; manter confirmação para ambiguidade real.

**[Média] Evidência visual correta ficou acoplada ao runtime e à política de viewport.** A skill visual manda passar manifesto ao Agent Graph e manter esse manifesto como gate mesmo usando outras suítes. Isso é útil em graph, mas não deve obrigar um run para toda edição visual. A política também usa uma matriz fixa para superfícies responsivas gerais.

Preservar a inspeção real com visão. Separar a prova visual do transporte do manifesto; dimensionar cobertura conforme superfícies, estados e plataformas suportadas. Qualquer mudança na exigência atual de cobertura precisa ser deliberada, pois é uma preferência explícita do usuário, não um detalhe descartável para economizar trabalho.

**[Média, cobertura não demonstrada] Instalar arquivos não comprova comportamento em todos os hosts.** Os aliases de instruções nos instaladores atendem explicitamente Claude e Codex. Há detecção de outros hosts e configuração de MCP no OpenCode, mas isso não constitui smoke test de descoberta, precedência e execução de instruções em cada agente. Os perfis de instrução usuais de Gemini e OpenCode não estavam presentes nos caminhos locais inspecionados; não concluo daí que esses hosts não tenham outra descoberta ou configuração.

Documentar por capacidade: descoberta de skill, instrução global, MCP, execução local, delegação, handoff, visão e cleanup. Marcar o que foi observado em host real e o que só tem teste de adapter. Não anunciar equivalência universal a partir de um symlink.

### Destino recomendado para cada skill versionada

| Skill | Destino | Mudança justificada |
|---|---|---|
| spec | manter, enxugar | seleção proporcional; referências para graph; evitar leitura ampla automática |
| impl | manter, corrigir | resolver runtime instalado; separar conclusão leve; flexibilizar handoff conforme capacidade |
| agent-graph | manter como capacidade especializada | não pagar protocolo durable em todo trabalho; preservar invariantes do journal |
| research | manter com modos | consulta simples sem cerimônia de relatório; pesquisa formal com ledger |
| scrapingdog | manter como adaptador | descrição curta; catálogo e preços nas referências |
| ingest | restringir | documentos que exigem extração; leitura direta de código e Markdown |
| frontend-visual-validation | manter | visão obrigatória no escopo atual, independente de haver graph |
| thermo-nuclear-code-quality-review | especializada | sair do fechamento obrigatório de mudanças triviais |
| rule-curator | especializada | auditoria pode entregar relatório; UI de curadoria quando for útil ao usuário |
| writing | enxugar | convenções e exemplos coerentes; evitar receita rígida de estrutura |
| readme-pass | especializada | conteúdo primeiro; staging e banner apenas dentro do pedido |
| grill-me | manter | entrada explícita já é curta e bem delimitada |
| grill-with-docs | manter | útil quando o usuário quer entrevista e decisões de domínio |
| trim-code-comments | manter | respeitar autorização de remoção já dada |
| remove-ai-marks | pacote opcional | capacidade específica sem necessidade no núcleo de coding; evitar oferecer reescrita em toda limpeza de metadados |

### Unlazy: avaliação da versão inspecionada

Fonte fixada: [SKILL.md](https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/SKILL.md), accessed 2026-09-06. Não instalei a skill nem hooks no ambiente real.

Ela não é apenas motivação do tipo “esforce-se mais”. Há um checker, evidências vinculadas à definição dos gates, distinção entre abandono e sucesso, isolamento lógico de escopos, estado de dispatch e um hook opcional de parada. Os testes focados executados confirmam comportamentos específicos desse mecanismo, sem provar aumento de produtividade de agentes.

O que vale aproveitar: tornar omissões visíveis, associar aceitação a evidência atual e não confundir fim de processo com tarefa concluída. Seu harness já implementa boa parte disso.

O que não recomendo importar: um ledger adicional, outro scheduler e outro estado de ownership ao lado do Agent Graph. Também não recomendo a condição “repetir até uma passagem de melhoria não encontrar nada”: ela não tem limite de esforço objetivo e pode promover polimento fora do pedido. A exigência de aprovação explícita inspecionada para checks precisa respeitar a autorização já fornecida, sem pedir novamente por tarefas locais conhecidas.

O hook de Stop é específico do Claude, opcional e tem escape de falta de progresso; não é uma garantia portátil de conclusão. Proteções de integridade desse mecanismo não devem ser removidas só por parecerem extensas. Fonte: [SECURITY.md](https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/SECURITY.md), accessed 2026-09-06.

A descrição do repositório ainda anuncia multiplicação de esforço por profundidade, enquanto o [método atual](https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/references/method.md) rejeita essa promessa aritmética. O [protocolo de validação](https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/research/validation-protocol.md) informa ausência dos artefatos da comparação histórica. Fontes accessed 2026-09-06. Portanto: mecanismo potencialmente útil em tarefas extensas sem acompanhamento existente; benefício incremental sobre este harness não demonstrado.

### Como atender contextos diferentes sem carregar tudo

| Contexto | Comportamento suficiente | O que não deve ser requisito de entrada |
|---|---|---|
| Dúvida sobre código local | ler trecho relevante e responder com evidência | intake executável, pesquisa externa, grafo |
| Typo ou edição mecânica | editar e inspecionar diff | spec persistida, auditoria especializada |
| Bug delimitado | reproduzir, corrigir, validar comportamento | refatoração geral ou mapa completo |
| Feature coesa | plano breve quando útil; implementar e verificar integração afetada | decomposição por disponibilidade de agentes |
| Mudança com contratos externos | reconhecer consumidor e decidir compatibilidade | presumir MVP apesar das evidências |
| Trabalho longo com pressão de contexto | resumo de objetivo, decisões, arquivos, evidência e pendências | reinício automático de sessão ou histórico inteiro |
| Trabalho independente em paralelo | ownership, dependências, coordenação e integração | árvore artificial para atingir profundidade |
| Retomada depois de interrupção | reconciliar estado real antes de repetir comandos | restaurar processos automaticamente |
| Ambiente offline ou sem MCP | fontes locais quando suficientes; declarar limites | bloquear por falta de provedor irrelevante |
| Host sem visão | concluir partes verificáveis e declarar visual não observado | afirmar sucesso visual por build |
| Windows, macOS ou Linux | resolver runtime, paths, shell e capacidades reais | assumir Bash, /proc ou Orca em todo host |
| Operação externa | preparar resultado revisável e respeitar autorização vigente | criar novas permissões por uma skill |

Arquitetura recomendada: instruções globais curtas; instruções de projeto específicas; skill do domínio escolhido; runtime adicional apenas quando houver necessidade de coordenação durável. A tarefa seleciona a capacidade. O modelo e o host determinam como executá-la, dentro dos limites disponíveis.

Uma regra de persistência suficiente seria: “Conclua o escopo autorizado, valide o resultado e corrija falhas causadas pela mudança. Pare quando a aceitação estiver demonstrada ou houver bloqueio concreto. Preserve as decisões e pendências em uma retomada; não amplie o escopo para continuar ocupado.” Isso substitui incentivo genérico por uma fronteira verificável.

### Ordem de implementação sugerida

- Corrigir o parsing de compatibilidade, fechar dependências da instalação e resolver caminhos fora do checkout.
- Separar o fluxo leve de impl e limitar comandos de graph ao modo correspondente.
- Ajustar coordenação ao host e provar instalação limpa por capacidade, sem presumir portabilidade.
- Separar instruções globais das locais; consolidar regras de commits, modelos e pesquisa.
- Reduzir descrições concorrentes e mover detalhes condicionais para referências.
- Oferecer instalação por capacidades, preservando skills e configurações já pertencentes ao usuário.
- Comparar o harness atual com a versão enxuta em tarefas equivalentes, com logs de custo e qualidade, antes de transformar preferências em novas regras.

Não proponho apagar o scheduler por tamanho. Ownership, fencing, cleanup, evidência por tentativa e retomada resolvem problemas reais. O excesso principal é exigir esses mecanismos antes de a tarefa precisar deles.

### Verificação realizada

As suítes focadas de intake e instaladores passaram. O teste isolado de compatibilidade ainda reproduz o erro, e a cópia reduzida ainda omite o runtime. Logo, passar nas suítes existentes não descarta esses achados. Logs: [intake](sources/2026-09-06-harness-audit/intake-tests.log), [instaladores](sources/2026-09-06-harness-audit/installer-tests.log).

Executei `tests/run-tests.mjs` da unlazy fixada, que passou. Não executei a suíte npm completa, hardening/stress nem testes nativos Windows/macOS. [Log](sources/2026-09-06-harness-audit/unlazy-tests.log). Fixtures de hooks foram temporárias; nenhum hook de usuário foi instalado.

As reproduções e fontes estão em `research/sources/`, ignorado pelo Git. O relatório é o único novo arquivo versionável desta auditoria. Nenhuma correção do harness, instalação de skill, commit ou alteração dos arquivos preexistentes foi feita.

## Disagreements

Há divergência entre a descrição pública da unlazy e o método atual quanto à multiplicação de esforço, observada em 2026-09-06. Uso o código e o método fixados por commit para descrever o funcionamento, mantendo a divergência explícita.

O artigo recomenda reduzir scaffolding para um modelo específico. Este relatório concorda com a direção onde há evidência local, mas não extrapola comportamento desse modelo para outros agentes. Algumas regras explícitas continuam necessárias em mecanismos de concorrência, autorização e integridade.

## Open questions

- Quais hosts e sistemas operacionais precisam de suporte operacional garantido, além de descoberta de skills? A recomendação cobre capacidades, mas testes reais nessa matriz ainda faltam.
- Quanto custo e retrabalho a versão enxuta remove? Não há comparação controlada nesta auditoria.
- Há projetos consumidores com contratos ativos que dependem dos comportamentos propostos para mudança? Verificar antes de aplicar alterações incompatíveis ao runtime distribuído.

Essas perguntas delimitam uma implementação posterior; não impedem os achados deste audit.

## Council review

- Status: not run
- Reason: auditoria material fundamentada em fontes primárias e reproduções; sem pedido de council, conclusões dependentes de fonte secundária ou controvérsia científica a adjudicar.
- Accepted findings: None.
- Rejected findings: None.

Não usei a UI de rule-curator: o pedido é um diagnóstico do harness, não uma sessão de curadoria manual e aplicação. Usei sua taxonomia como referência de auditoria. Não criei grafo para a coleta de uma fonte conhecida: isso acrescentaria o próprio overhead que está sendo avaliado sem melhorar a evidência.

## Sources consulted

- https://github.com/badmuriss/my-llm-kit/blob/c276d1a8a943889e7f847c36f16d2bf6b30cd94f/skills/agent-graph/scripts/adaptive_intake.py, accessed 2026-09-06. Conteúdo consultado no checkout local.
- https://github.com/badmuriss/my-llm-kit/blob/c276d1a8a943889e7f847c36f16d2bf6b30cd94f/install-manifest.json, accessed 2026-09-06. Conteúdo consultado no checkout local.
- https://github.com/Leonxlnx/unlazy, accessed 2026-09-06.
- https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/SKILL.md, accessed 2026-09-06.
- https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/SECURITY.md, accessed 2026-09-06.
- https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/references/method.md, accessed 2026-09-06.
- https://github.com/Leonxlnx/unlazy/blob/16671491f6679ad9378f52604d3bc2415b4120c7/research/validation-protocol.md, accessed 2026-09-06.

Demais fontes locais: links junto aos achados e manifesto do corpus; artigo e skill-creator fornecidos pelo usuário.

## Trial by fire

- Primary-source claims: comportamento textual das instruções, inventário local, reprodução do intake, reprodução da instalação reduzida e contratos da unlazy.
- Secondary-only claims: nenhuma usada para sustentar correção ou recomendação.
- Volatile claims: catálogo instalado e conteúdo upstream; revalidar antes de aplicar mudanças futuras.
- Limite: os conflitos de prompt indicam risco de comportamento; não medem sua frequência. Apenas os casos expressamente reproduzidos são falhas executadas.
