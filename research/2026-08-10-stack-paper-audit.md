# Auditoria de papers da stack `my-llm-kit`

> Revisão: a reauditoria feita com o modelo Sol corrigiu recomendações que iam além da evidência. Leia [2026-08-10-stack-paper-audit-sol-review.md](./2026-08-10-stack-paper-audit-sol-review.md) antes de implementar este finding.

Data de acesso: 2026-08-10.

## Pergunta

Quais mecanismos presentes no `my-llm-kit` são apoiados, limitados ou contraditos por pesquisa primária sobre raciocínio de LLMs, agentes de programação, verificação, planejamento, colaboração multiagente e execução de longo horizonte, e quais mecanismos são implementáveis no repositório?

## Critério de decisão

Um mecanismo só é classificado como apoiado quando um paper primário mede um comportamento ou uma falha compatível, com as mesmas condições e limites. Uma implementação só é recomendada quando é genérica, compatível com o harness atual, verificável por teste ou por uma checagem mecânica e não duplica uma proteção existente. “Refutado” fica reservado para uma afirmação específica contradita diretamente por um estudo, não para qualquer técnica vizinha com resultado misto.

## Falsificadores

Esta auditoria falha se transformar um abstract em uma afirmação mais forte que a testada, esconder discordâncias entre papers ou recomendar uma mudança sem arquivo, critério de aceite e caso de falha concreto. Uma proposta é rejeitada quando depende apenas de anedota, tem menos de cinco casos comparáveis ou não possui custo e modo de falha delimitados.

## Protocolo e trilha de pesquisa

- O repositório e a skill local de pesquisa foram lidos antes das fontes externas.
- `SCRAPINGDOG_API_KEY` estava ausente em 2026-08-10. O fallback documentado para Firecrawl foi usado, e a falha foi registrada antes da coleta.
- O Firecrawl estava autenticado no início da coleta. O saldo reportado é volátil e não é usado como conclusão sobre a arquitetura.
- O instalador documenta um MCP `paper-search`. O executável local `paper-search-mcp` e a CLI `paper-search` estão instalados, mas nenhuma ferramenta MCP com esse nome foi exposta nesta sessão. A busca da CLI no arXiv foi útil como descoberta, porém teve baixa cobertura sem as chaves opcionais configuradas e não encontrou todos os papers centrais. A validação final usou páginas primárias do arXiv e seus HTMLs oficiais, com DOI arXiv quando disponível.
- Os papers foram lidos como HTML ou Markdown convertido pelo Firecrawl. Não houve PDF para analisar diretamente, portanto não foi necessário fazer uma conversão local de PDF.
- O snapshot local analisado está no commit `86a731f`, verificado em [git log e arquivos do repositório](../.git/HEAD). A evidência do código vem dos arquivos locais, não de uma descrição externa.

## Veredito curto

O núcleo da stack é defensável: especificar antes de editar, agir por interfaces de ferramenta, receber feedback externo, validar o resultado e guardar evidência. CodePlan, SWE-agent e Reflexion dão suporte compatível a essas ideias.

Há três limites importantes:

1. O resultado não sustenta a tese de que um harness mais complexo ou um conselho multiagente é sempre melhor. Agentless obteve um resultado forte com um fluxo fixo e simples, e papers recentes documentam conformismo e perda de acurácia em debates ingênuos.
2. Não é seguro transformar “mais raciocínio” em “melhor raciocínio”. s1 mostra que forcing pode ajudar em um modelo ajustado para matemática, mas OptimalThinkingBench e When More Thinking Hurts mostram que orçamento uniforme pode desperdiçar tokens ou afastar o modelo de uma resposta correta.
3. Prompt, plano e disciplina podem melhorar a qualidade inicial sem impedir a degradação em tarefas iterativas. SlopCodeBench apoia adicionar métricas de trajetória, não apenas gates de passagem.

Não encontrei um paper que refute o `my-llm-kit` como um todo. Encontrei contraexemplos suficientes para não instalar o `unlazy` como regra padrão. A melhor integração é seletiva: importar seus gates de aceite e verificação, manter a árvore de profundidade como opt-in experimental e substituir esforço fixo por escalada adaptativa baseada em evidência.

## Fotografia da stack atual

| Mecanismo local | Evidência no repositório | Avaliação da literatura |
| --- | --- | --- |
| Pesquisa com fontes primárias, URLs e data | [skills/research/SKILL.md](../skills/research/SKILL.md) | Forte como disciplina de rastreabilidade. Não é uma hipótese de desempenho de agente e não precisa de paper para justificar a auditabilidade. |
| `spec` antes de `impl` | [skills/spec/SKILL.md](../skills/spec/SKILL.md), [commands/spec.md](../commands/spec.md) | Apoiamento condicional. CodePlan favorece planos para mudanças interdependentes; resultados de plan-first são mistos em tarefas longas. |
| Conselho independente e bounded | [spec-council/SKILL.md](../../spec-council/SKILL.md), referenciado pelo [install-manifest.json](../install-manifest.json) | Misto. Debate pode ajudar, mas debate sem incentivo e verificação externa pode piorar. O conselho deve ser advisory, nunca prova de correção. |
| `impl` com workers, feedback, evidência e estado retomável | [skills/impl/SKILL.md](../skills/impl/SKILL.md), [impl_state.py](../skills/impl/scripts/impl_state.py) | Forte na direção. SWE-agent e Reflexion apoiam interface mais feedback externo; ainda falta tornar parte dos gates mecanicamente executável. |
| Grades `pass`, `fail`, `unobserved`, `blocked` | [skills/impl/SKILL.md](../skills/impl/SKILL.md), [learning.py](../skills/impl/scripts/learning.py) | Forte contra conclusão sem observação. A literatura sobre agentes mostra que teste de passagem isolado não captura toda a degradação estrutural. |
| Aprendizado pós-run e promoção por recorrência | [learning.py](../skills/impl/scripts/learning.py) | Boa proteção de processo. Não há evidência de que regras textuais sozinhas evitem regressões, então gate candidates devem virar testes ou guards quando possível. |
| Roteamento por custo e dificuldade | [model-routing.md](../skills/impl/references/model-routing.md) | Heurística plausível, não validada pela literatura como política ótima. A evidência favorece orçamento adaptativo por tarefa, não uma tabela fixa universal. |
| `dcg` e `agent-resource-guard` | [dcg/config.toml](../dcg/config.toml), [agent_resource_guard.py](../scripts/agent_resource_guard.py) | Não há contradição encontrada. São controles operacionais, não alegações de capacidade do modelo. |
| `ingest` antes de ler documentos | [skills/ingest/SKILL.md](../skills/ingest/SKILL.md) | Boa higiene de entrada e auditabilidade. Não foi encontrada evidência primária de que o conversor específico escolhido seja sempre superior. |
| `unlazy` como disciplina opcional | fonte externa [SKILL.md do unlazy](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/SKILL.md), acessada em 2026-08-10 | Partes são apoiadas, a árvore binária com orçamento integral por folha não foi validada em coding agents. O default “nunca parar” entra em conflito com papers sobre overthinking e custo. |

## Achados por mecanismo

### 1. Planejamento, interface e execução com feedback são o núcleo mais apoiado

O CodePlan formula edição de repositório como um problema de planejamento e relata que passou em 5 de 6 repositórios em tarefas de migração e edição temporal, enquanto os baselines sem planejamento não passaram em nenhum dos mesmos casos. O estudo cobre tarefas com mudanças interdependentes em 2 a 97 arquivos, portanto apoia a direção do `spec` para mudanças realmente distribuídas, não a obrigação de produzir um plano longo para qualquer tarefa. Fonte primária: [CodePlan, arXiv:2309.12499, DOI](https://doi.org/10.48550/arXiv:2309.12499), acessada em 2026-08-10.

SWE-agent apoia a construção de interfaces próprias para o agente navegar no repositório, editar arquivos e executar programas. O paper relata pass@1 de 12,5% no SWE-bench e 87,7% no HumanEvalFix em sua configuração, mas esses números são resultados do paper e não uma garantia para outro harness. Fonte primária: [SWE-agent, arXiv:2405.15793, DOI](https://doi.org/10.48550/arXiv:2405.15793), acessada em 2026-08-10.

Isso corresponde ao que `my-llm-kit` faz quando separa decisão, implementação e verificação. A lacuna é que o repositório descreve o check no contrato de task, porém [impl_state.py](../skills/impl/scripts/impl_state.py) persiste texto, status e referências, sem interpretar a parte “Check” de `tasks.md` nem executar um comando de aceite próprio. A regra existe no prompt; a execução ainda depende do orquestrador.

### 2. Planejamento não deve virar complexidade obrigatória

Agentless é o contraexemplo mais importante para uma leitura maximalista da literatura. Seu fluxo fixo de localização, reparo e validação, sem deixar o LLM decidir todos os próximos passos, relata 32,00%, ou 96 de 300 problemas, no SWE-bench Lite e custo médio de US$ 0,70 por problema em sua configuração. Fonte primária: [Agentless, arXiv:2407.01489, DOI](https://doi.org/10.48550/arXiv:2407.01489), acessada em 2026-08-10.

Esse resultado não refuta CodePlan nem prova que agentes são desnecessários em todos os cenários. Os benchmarks, modelos, splits e custos não são idênticos. A conclusão válida é mais estreita: complexidade de scaffolding não é um proxy de qualidade. O `spec` deve continuar sendo o caminho para mudanças com decisões reais, mas tarefas triviais precisam de uma saída explícita e barata, ou o próprio protocolo passa a cobrar custo sem evidência de benefício.

### 3. Verificação externa é mais segura que autoavaliação textual

Reflexion melhora decisões usando feedback do ambiente e memória textual entre tentativas, sem atualizar os pesos do modelo. O paper relata ganho em tarefas de decisão, coding e raciocínio, mas o mecanismo relevante para esta stack é o feedback externo ou observável, não a frase “revise sua resposta”. Fonte primária: [Reflexion, arXiv:2303.11366, DOI](https://doi.org/10.48550/arXiv:2303.11366), acessada em 2026-08-10.

Em sentido contrário, Large Language Models Cannot Self-Correct Reasoning Yet conclui que correção intrínseca, sem feedback externo, frequentemente não corrige o raciocínio e pode degradar o resultado. Fonte primária: [Large Language Models Cannot Self-Correct Reasoning Yet, arXiv:2310.01798, DOI](https://doi.org/10.48550/arXiv:2310.01798), acessada em 2026-08-10.

Aplicação direta: o `council-review.md`, a reflexão de um worker ou o “Wait” do `unlazy` devem gerar uma hipótese, nunca um `pass`. O `pass` precisa continuar dependente de teste, diff, commit ou outro artefato verificável. Nesse ponto a regra atual de [skills/impl/SKILL.md](../skills/impl/SKILL.md) está alinhada, mas ainda é uma obrigação textual em parte do fluxo.

### 4. Conselho multiagente: evidência favorável e refutação de uso ingênuo

O paper Multiagent Debate relata ganhos em raciocínio matemático, estratégico e factual ao fazer instâncias debaterem por várias rodadas. Fonte primária: [Improving Factuality and Reasoning in Language Models through Multiagent Debate, arXiv:2305.14325, DOI](https://doi.org/10.48550/arXiv:2305.14325), acessada em 2026-08-10.

Há uma discordância primária importante. Talk Isn't Always Cheap relata que o debate pode reduzir a acurácia: modelos mudam de uma resposta correta para uma errada, favorecendo acordo em vez de contestar um argumento incorreto. Fonte primária: [Talk Isn't Always Cheap, arXiv:2509.05396, DOI](https://doi.org/10.48550/arXiv:2509.05396), acessada em 2026-08-10.

When and Why Does Multi-Agent Debate Fail and Does It Really Underperform? atribui a diferença ao protocolo: consenso prematuro e competição podem filtrar discordâncias informativas ou incentivar mensagens estratégicas. O trabalho propõe um protocolo colaborativo e relata melhora de até 10 pontos percentuais em suas tarefas, mas também se identifica como preprint em andamento. Fonte primária: [When and Why Does Multi-Agent Debate Fail, arXiv:2510.20963, DOI](https://doi.org/10.48550/arXiv:2510.20963), acessada em 2026-08-10.

O [spec-council/SKILL.md](../../spec-council/SKILL.md) já contém três salvaguardas corretas: reviewers independentes não veem respostas anteriores, maioria não é tratada como prova e falta de capacidade produz `unverified`. O que não deve ser adicionado é um mecanismo que converta consenso em verdade. A verificação final precisa permanecer fora do conselho.

### 5. `unlazy`: bons gates, árvore não demonstrada

O `unlazy` foi lido no [README](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/README.md) e no [SKILL.md](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/SKILL.md), acessados em 2026-08-10. Ele propõe: gates de aceite antes de começar, verificação em vez de confiança, sweeps completos, continuação forçada, uma linha de ataque por vez e proibição de placeholders. Essas regras são compatíveis com `impl` e em boa parte já existem no contrato de [skills/impl/SKILL.md](../skills/impl/SKILL.md).

O método específico, entretanto, não aparece testado como método experimental de coding agent. A evidência pública do repositório é uma lista de papers sobre falhas de esforço e um relato de uso próprio no projeto `sakura-realm`. Isso é evidência de projeto e demonstração, não um estudo comparativo independente da Depth Tree.

Os papers que o `unlazy` cita apoiam a existência de falhas de esforço, mas não sua fórmula de esforço multiplicativo:

- Quantifying Laziness define preguiça como truncamento prematuro ou cumprimento parcial de instruções multi-parte. O mesmo abstract relata evidência limitada de decoding suboptimality em uma tarefa simples e robustez inesperada contra degradação de contexto em um teste caótico de 200 turnos. Fonte primária: [arXiv:2512.20662, DOI](https://doi.org/10.48550/arXiv:2512.20662), acessada em 2026-08-10. Isso apoia gates de completude, mas não autoriza afirmar que toda ansiedade de contexto ou todo problema de parada exige força bruta.
- Thoughts Are All Over the Place identifica underthinking como troca frequente de linha de raciocínio antes de explorar uma linha promissora e propõe uma penalidade de troca. Fonte primária: [arXiv:2501.18585, DOI](https://doi.org/10.48550/arXiv:2501.18585), acessada em 2026-08-10. Isso apoia “não abandonar uma linha cedo”, mas não exige que toda tarefa seja dividida em uma árvore binária.
- `s1` usa budget forcing para suprimir o marcador de fim ou anexar “Wait”. O resultado depende de fine-tuning do Qwen2.5-32B-Instruct em um conjunto curado de 1.000 questões e é medido em benchmarks de matemática competitiva. Fonte primária: [s1: Simple test-time scaling, arXiv:2501.19393, DOI](https://doi.org/10.48550/arXiv:2501.19393), acessada em 2026-08-10. É uma inspiração para forcing adaptativo, não uma validação da árvore em tarefas de software.
- OptimalThinkingBench avalia 33 modelos, distingue overthinking de underthinking e relata que nenhum modelo foi ótimo em ambos os lados de seu benchmark. O abstract diz que métodos que melhoram um subbenchmark frequentemente prejudicam o outro. Fonte primária: [arXiv:2508.13141, DOI](https://doi.org/10.48550/arXiv:2508.13141), acessada em 2026-08-10.
- When More Thinking Hurts relata retornos marginais decrescentes, abandono de respostas corretas e vantagem de parar em orçamentos moderados em parte dos casos. Fonte primária: [arXiv:2604.10739, DOI](https://doi.org/10.48550/arXiv:2604.10739), acessada em 2026-08-10.

Veredito: importar os gates de `unlazy` como checklist opcional é útil. Importar `tree N`, orçamento integral por folha ou “nunca pare porque parece pronto” como default é refutado no sentido operacional pelos contraexemplos de overthinking, custo e mudança para respostas erradas. A Depth Tree deve ser tratada como hipótese experimental, com profundidade baixa, limite de custo e validação externa.

### 6. Tarefas longas exigem medir qualidade de trajetória, não apenas passagem

SlopCodeBench mede tarefas iterativas em que o agente continua estendendo o próprio código. O paper relata 36 problemas, 196 checkpoints e 15 agentes avaliados; nenhum agente resolveu um problema inteiro end-to-end e o melhor passou 14,8% dos checkpoints. Em 77% das trajetórias a erosão estrutural aumentou, e em 75,5% a verbosidade aumentou. Fonte primária: [SlopCodeBench, arXiv:2603.24755, DOI](https://doi.org/10.48550/arXiv:2603.24755), acessada em 2026-08-10.

O resultado mais acionável é o experimento de prompts: `anti-slop` e `plan-first` melhoraram a qualidade inicial, mas não eliminaram a degradação iterativa; em média os prompts elevaram o custo por checkpoint em 12,1%. Fonte primária: [seção 3.4 do HTML de SlopCodeBench](https://arxiv.org/html/2603.24755v2#S3.SS4), acessada em 2026-08-10.

Isso limita duas expectativas do `my-llm-kit`: uma boa instrução de estilo não substitui medição, e um plano aprovado não prova que a implementação continuará saudável após novas mudanças. O `impl` já registra grades e incidentes, mas ainda não registra uma linha de base de qualidade do diff ou uma métrica de erosão/verbosidade. A recomendação é começar por sinais simples e observáveis, sem impor um threshold universal para todas as linguagens.

### 7. Roteamento de modelo e esforço: boa heurística, não fato estabelecido

O [model-routing.md](../skills/impl/references/model-routing.md) recomenda começar com o modelo mais barato que possa concluir a task e escalar para ambiguidade, integração ou risco. Essa política é coerente com OptimalThinkingBench e When More Thinking Hurts, que favorecem adaptação ao problema. Não há, porém, paper consultado que valide os rótulos locais `luna`, `terra` e `sol` ou a tabela de esforço para os modelos específicos do ambiente.

O veredito correto é “heurística operacional pendente de telemetria”, não “otimizado”. O falsificador já previsto no [research/2026-08-10-codex-model-routing.md](./2026-08-10-codex-model-routing.md) é adequado: comparar pelo menos cinco implementações comparáveis, medindo retrabalho e custo total, antes de promover a política.

### 8. Pesquisa, ingestão, guardas e portabilidade

Não encontrei paper que contradiga a ordem de pesquisa do [skills/research/SKILL.md](../skills/research/SKILL.md), nem a separação de ingestão do [skills/ingest/SKILL.md](../skills/ingest/SKILL.md). Essas são decisões de rastreabilidade, segurança e ergonomia do processo. A literatura consultada recomenda não confundir correção aparente com correção executada, o que favorece o desenho geral.

Há uma lacuna operacional verificável: [setup.sh](../setup.sh) instala e registra `paper-search`, mas o fluxo não confirma uma consulta real funcionando antes de declarar a instalação concluída. Nesta sessão o MCP foi documentado no repositório, mas não estava disponível para uso. A mesma propriedade merece um preflight explícito no instalador Windows.

O `agent-resource-guard` e o `dcg` também não foram refutados. A literatura sobre agentes longos aumenta, e não reduz, a justificativa para limitar fan-out, impedir comandos destrutivos e limpar processos órfãos. Isso continua sendo uma decisão de engenharia operacional, não uma conclusão de benchmark.

## Implementações recomendadas

### Prioridade alta: tornar o aceite executável

Criar um contrato de validação de task que não dependa apenas do texto do worker:

- [skills/impl/scripts/impl_state.py](../skills/impl/scripts/impl_state.py) deve exigir que toda task não trivial tenha um comando ou fixture de validação identificável.
- [skills/impl/references/impl-state.schema.json](../skills/impl/references/impl-state.schema.json) deve persistir o check, o resultado observado e os artefatos produzidos.
- [skills/impl/SKILL.md](../skills/impl/SKILL.md) deve manter a regra de quebrar o check com fixture isolada, mas o estado deve distinguir `check_passed`, `check_failed` e `check_unobserved`.
- Uma nova suíte comportamental deve provar que um check passa com a implementação correta, falha com uma mutação isolada e volta a passar depois da restauração. O repositório atualmente não expõe uma suíte automatizada própria, então esse gap precisa ser fechado antes de chamar a proteção de mecânica.

Base da recomendação: CodePlan, SWE-agent, Agentless, Reflexion e o contraexemplo de self-correction sem feedback.

### Prioridade alta: registrar saúde da trajetória

Adicionar ao estado e ao run exportado sinais de cada checkpoint: arquivos alterados, linhas adicionadas e removidas, número de reparos, checks executados, checks não observados e duração. Depois, adicionar métricas opcionais por linguagem para complexidade concentrada, duplicação e verbosidade.

Não impor um score universal nem bloquear uma mudança só por aumento de linhas. O gate deve sinalizar regressão para revisão, e não substituir testes funcionais. Base da recomendação: SlopCodeBench, que separa correção de erosão e verbosidade e mostra que passagem pode coexistir com piora estrutural.

Arquivos prováveis: [impl_state.py](../skills/impl/scripts/impl_state.py), [learning.py](../skills/impl/scripts/learning.py), [learning-run.schema.json](../skills/impl/references/learning-run.schema.json) e uma suíte de testes nova.

### Prioridade média: escalada adaptativa de esforço

Manter o primeiro worker barato e escalar apenas quando houver sinal: check falho, task não observada, ambiguidade registrada, mudança cross-cutting ou risco de segurança. Persistir a razão da escalada e o custo aproximado. Nunca usar `tree N` ou `xhigh` como substituto de um critério de aceite.

Arquivos prováveis: [model-routing.md](../skills/impl/references/model-routing.md), [skills/impl/SKILL.md](../skills/impl/SKILL.md) e o estado do run. Antes de automatizar, é necessário confirmar a interface de roteamento do host e medir pelo menos cinco casos comparáveis.

### Prioridade média: preflight real do `paper-search`

Alterar [setup.sh](../setup.sh) e [setup.ps1](../setup.ps1) para validar a presença do executável, a versão e uma consulta mínima ou handshake do MCP. Se falhar, registrar a razão exata e declarar que o fallback web permanece ativo. Isso evita que “pacote instalado” seja confundido com “skill de pesquisa operacional”.

### Prioridade baixa e opt-in: adaptar `unlazy`, não vendê-lo como default

Extrair apenas estas regras para uma skill opcional ou para uma seção de `impl`: gates antes de executar, verificação externa, sweep completo quando o pedido exigir, uma linha de ataque por vez e proibição de placeholders. Exigir profundidade declarada, orçamento máximo e condição de parada.

Não adotar como padrão: árvore binária fixa, tempo integral por folha, `Wait` indiscriminado, proibição de relatório durante todo o trabalho ou “nunca parar” sem um critério observável. A evidência atual apoia forcing condicionado a feedback e ao tipo de task, não esforço ilimitado.

### Não implementar agora: debate automático como etapa universal

O `spec-council` pode continuar opt-in no modo `--no-council` e bounded no fluxo padrão, porque já evita algumas falhas de independência. Não há justificativa para adicionar mais rodadas, mais agentes ou consenso automático antes de medir ganho líquido em tarefas reais. Se uma tarefa for de alto risco, prefira candidatos independentes avaliados por um teste ou artefato comum.

## Disputas e limites da evidência

| Questão | Evidência em conflito | Como a decisão foi limitada |
| --- | --- | --- |
| Planejamento versus fluxo simples | CodePlan favorece planejamento; Agentless relata resultado forte com três fases fixas | Planejar ajuda quando há dependências e contexto distribuído; não é motivo para tornar toda task mais complexa. |
| Debate versus agente único | Multiagent Debate relata ganho; Talk Isn't Always Cheap relata perda; ColMAD atribui o resultado ao protocolo | Conselho é revisão de hipóteses, não prova. Verificação externa decide. |
| Forcing versus mais compute | s1 relata ganhos em matemática com modelo ajustado; OptimalThinkingBench e When More Thinking Hurts mostram overthinking e custo | Forcing só como intervenção adaptativa e mensurada, nunca como orçamento fixo geral. |
| Contexto e “ansiedade” | `unlazy` usa fonte secundária sobre context anxiety; Quantifying Laziness relata robustez em um teste específico de 200 turnos | Não usar context anxiety como fato geral. Tratar como hipótese dependente do modelo, tarefa e janela. |
| Benchmarks de coding | SWE-bench mede issue resolution; SlopCodeBench mede evolução iterativa e qualidade estrutural | Não comparar percentuais de benchmarks diferentes como ranking global. |

## O que permanece aberto

- Nenhum paper consultado avaliou o `my-llm-kit` diretamente.
- Nenhum paper consultado validou a Depth Tree do `unlazy` como política de coding agent.
- O efeito líquido do `spec-council` local, incluindo custo e correções evitadas, ainda não foi medido em pelo menos cinco tasks comparáveis.
- O roteamento local de modelos é uma hipótese operacional. Falta telemetria de custo, retrabalho, falhas e tempo por classe de task.
- Falta uma suíte própria para provar os invariantes de `impl_state.py`, `learning.py`, instaladores e guardas. Os scripts existem, mas a auditoria encontrou [apenas os arquivos de implementação e documentação](../skills), sem uma suíte automatizada no snapshot analisado.

## Trial by fire

### Afirmações apoiadas por fontes primárias

As afirmações sobre CodePlan, SWE-agent, SWE-bench, Agentless, Reflexion, self-correction, debate, s1, underthinking, OptimalThinkingBench e SlopCodeBench vêm dos próprios papers no arXiv, com DOI e data de acesso ao lado. As afirmações sobre a implementação atual vêm dos arquivos locais do repositório e do `spec-council` instalado localmente.

### Afirmações baseadas apenas em fontes secundárias ou autorrelato

O README do `unlazy` é uma fonte primária sobre o que o próprio projeto afirma, mas não é evidência independente de que sua Depth Tree seja eficaz. A referência a context anxiety do Inkeep e a referência do README a documentação do Aider são secundárias para as alegações comportamentais. Não foram usadas para sustentar um veredito forte.

### Números que exigem reconfirmação

Percentuais, custos, pass rates, número de exemplos e resultados de benchmark são propriedades da versão do paper, modelo, harness e dataset. Foram preservados apenas com a URL primária e a data de acesso de 2026-08-10. Saldo do Firecrawl, versão de ferramenta, preços, estrelas, disponibilidade de MCP e compatibilidade de host são voláteis e não devem ser copiados para uma regra permanente sem nova checagem.

## Fontes consultadas

### Repositório e fontes locais

- [README.md](../README.md), acessado em 2026-08-10.
- [AGENTS.md](../AGENTS.md), acessado em 2026-08-10.
- [skills/research/SKILL.md](../skills/research/SKILL.md), acessada em 2026-08-10.
- [skills/ingest/SKILL.md](../skills/ingest/SKILL.md), acessada em 2026-08-10.
- [skills/spec/SKILL.md](../skills/spec/SKILL.md), acessada em 2026-08-10.
- [skills/impl/SKILL.md](../skills/impl/SKILL.md), acessada em 2026-08-10.
- [impl_state.py](../skills/impl/scripts/impl_state.py), acessado em 2026-08-10.
- [learning.py](../skills/impl/scripts/learning.py), acessado em 2026-08-10.
- [spec-council/SKILL.md](../../spec-council/SKILL.md), acessada em 2026-08-10.

### Papers primários

- [CodePlan, arXiv:2309.12499, DOI](https://doi.org/10.48550/arXiv:2309.12499), acessado em 2026-08-10.
- [SWE-bench, arXiv:2310.06770, DOI](https://doi.org/10.48550/arXiv:2310.06770), acessado em 2026-08-10.
- [SWE-agent, arXiv:2405.15793, DOI](https://doi.org/10.48550/arXiv:2405.15793), acessado em 2026-08-10.
- [Agentless, arXiv:2407.01489, DOI](https://doi.org/10.48550/arXiv:2407.01489), acessado em 2026-08-10.
- [Reflexion, arXiv:2303.11366, DOI](https://doi.org/10.48550/arXiv:2303.11366), acessado em 2026-08-10.
- [Large Language Models Cannot Self-Correct Reasoning Yet, arXiv:2310.01798, DOI](https://doi.org/10.48550/arXiv:2310.01798), acessado em 2026-08-10.
- [Improving Factuality and Reasoning through Multiagent Debate, arXiv:2305.14325, DOI](https://doi.org/10.48550/arXiv:2305.14325), acessado em 2026-08-10.
- [Talk Isn't Always Cheap, arXiv:2509.05396, DOI](https://doi.org/10.48550/arXiv:2509.05396), acessado em 2026-08-10.
- [When and Why Does Multi-Agent Debate Fail, arXiv:2510.20963, DOI](https://doi.org/10.48550/arXiv:2510.20963), acessado em 2026-08-10.
- [Thoughts Are All Over the Place, arXiv:2501.18585, DOI](https://doi.org/10.48550/arXiv:2501.18585), acessado em 2026-08-10.
- [s1: Simple Test-Time Scaling, arXiv:2501.19393, DOI](https://doi.org/10.48550/arXiv:2501.19393), acessado em 2026-08-10.
- [OptimalThinkingBench, arXiv:2508.13141, DOI](https://doi.org/10.48550/arXiv:2508.13141), acessado em 2026-08-10.
- [Quantifying Laziness, arXiv:2512.20662, DOI](https://doi.org/10.48550/arXiv:2512.20662), acessado em 2026-08-10.
- [When More Thinking Hurts, arXiv:2604.10739, DOI](https://doi.org/10.48550/arXiv:2604.10739), acessado em 2026-08-10.
- [SlopCodeBench, arXiv:2603.24755, DOI](https://doi.org/10.48550/arXiv:2603.24755), acessado em 2026-08-10.

### Repositório externo avaliado

- [unlazy README](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/README.md), acessado em 2026-08-10.
- [unlazy SKILL.md](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/SKILL.md), acessado em 2026-08-10.
- [unlazy GitHub repository](https://github.com/Leonxlnx/unlazy), acessado em 2026-08-10.
