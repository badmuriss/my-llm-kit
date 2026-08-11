# Auditoria de aprendizado por trajetórias de agentes

Data de acesso: 2026-08-10.

## Pergunta

Uma camada automática melhora execuções futuras quando registra evidências de trajetórias, extrai observações, cria candidatas por recorrência e exige revisão humana ou gate executável antes de ativar uma regra ou skill?

## Critério de decisão

A hipótese recebe apoio forte somente se fontes primárias mostrarem, em avaliações comparáveis, que memória ou experiência recuperada reduz falhas ou retrabalho contra uma condição sem recuperação, e se o mecanismo separar observação, candidata e ativação. Resultados em menos de cinco casos independentes serão marcados como amostra fraca. Ganho em um benchmark não autoriza promoção permanente em outro domínio.

A arquitetura será recomendada apenas se a evidência sustentar estes limites:

```text
estado e checks observados
→ observações automáticas
→ candidatas recorrentes
→ revisão ou gate executável
→ regra/skill ativa
```

O aprendizado não pode bloquear o encerramento normal do `impl`. Texto gerado não se torna regra ativa por contagem baixa. Skills geradas permanecem drafts até revisão.

## Falsificador

A hipótese falha se regras recuperadas não reduzirem falhas ou retrabalho, introduzirem regressões, aumentarem custo sem ganho, propagarem aprendizados incorretos ou se o benefício desaparecer em uma ablação sem recuperação. Falta de avaliação sobre contaminação, conflito e esquecimento impede ativação automática, mesmo quando a memória melhora um benchmark.

## Protocolo

- Priorizar papers, repositórios oficiais e documentação dos sistemas avaliados.
- Procurar ablações com e sem memória, experiência, skill ou workflow recuperado.
- Separar memória episódica, regras textuais, skills executáveis e atualização de pesos.
- Registrar resultados favoráveis e negativos sem comparar percentuais de benchmarks diferentes como ranking global.
- Tratar Reflexion como evidência de reflexão com feedback, não como validação isolada de regras permanentes.
- Manter a remoção de `learning.py` congelada até o fim desta auditoria.

Cada sistema será classificado em quatro tipos de aprendizado:

| Tipo | Unidade persistida | Risco principal |
| --- | --- | --- |
| Episódico | trajetória, tentativa, feedback e resultado | recuperar um episódio irrelevante ou contaminado |
| Semântico | insight, regra ou reflexão textual extraída | transformar hipótese em verdade permanente |
| Procedural | workflow, programa, teste ou skill executável | reutilizar um procedimento fora do seu contrato |
| Paramétrico | pesos atualizados por treino ou reforço | esquecer capacidades e dificultar auditoria ou reversão |

Para cada fonte, a análise registrará: origem da observação, extração, recuperação, condição de ativação, validação, conflito, esquecimento, ablação sem memória e custo medido.

## Fontes candidatas

Foram triadas fontes primárias de todas as famílias do protocolo. A síntese
abaixo usa as que responderam diretamente à hipótese ou ao falsificador. Papers que tratam apenas de memória
conversacional ou skill discovery robótica entram como limites de
generalização, não como validação direta de um harness de engenharia de
software.

## Achados

### 1. Memória ajuda quando a escrita e a recuperação estão ancoradas em resultado

| Sistema | O que persiste | Validação ou ablação relevante | Leitura para o harness |
| --- | --- | --- | --- |
| Reflexion | Reflexões textuais de uma tentativa, em janela de 1 a 3 itens | No recorte difícil de HumanEval Rust, reflexão sem testes ficou em 52%, abaixo do baseline de 60%; testes e reflexão juntos chegaram a 68%. [Paper](https://arxiv.org/html/2303.11366v4), acesso em 2026-08-10. | Evidência para reflexão episódica entre tentativas quando existe feedback externo. É evidência contra transformar reflexão não verificada em regra permanente. |
| ExpeL | Trajetórias bem-sucedidas e insights extraídos de pares sucesso/falha | Em HotpotQA, ExpeL chegou a 39,0% contra 28,0% do ReAct. Adicionar reflexões à extração reduziu o resultado para 29,0%. Em ALFWorld, recuperar por similaridade de tarefa chegou a 59,0%, enquanto recuperação aleatória ficou em 42,5% e ReAct em 40,0%. [Paper](https://arxiv.org/html/2308.10144v3), acesso em 2026-08-10. | É o análogo mais próximo da hipótese. Suporta evidência, comparação sucesso/falha, voto positivo/negativo e remoção. Também mostra que reflexão adicional e recuperação ruim podem destruir o ganho. |
| Agent Workflow Memory | Workflows induzidos de trajetórias avaliadas como corretas | Em WebArena, AWM obteve 35,5% contra 15,0% do BrowserGym com a mesma representação; no subconjunto sem templates repetidos, 33,2% contra 20,5%. O próprio paper relata que workflows às vezes induzem ações inadequadas ao estado atual. [Paper](https://arxiv.org/html/2409.07429), acesso em 2026-08-10. | Suporta abstrair sub-rotinas e avaliar contra memória desligada. O modo online promove a partir de uma única trajetória julgada por LLM, portanto não valida a política conservadora pedida aqui. |
| Voyager | Skills de código executável, recuperadas por similaridade | Sem skill library o agente estagna; com a biblioteca, resolveu quatro tarefas não vistas em todas as três tentativas, enquanto os baselines não resolveram nenhuma dentro do orçamento. A avaliação usou somente três tentativas por tarefa, uma amostra fraca pelo protocolo desta auditoria. [Paper](https://arxiv.org/abs/2305.16291), acesso em 2026-08-10. | Suporta skills executáveis, composição e self-verification. Não sustenta promoção textual genérica nem transferência para software sem avaliação própria. |
| Agentic Skill Discovery | Políticas, funções de recompensa e de sucesso geradas por LLM | O sistema usa um verificador visual independente antes de aceitar skills e identifica falso positivo como mais perigoso porque contamina a biblioteca. [Paper](https://arxiv.org/html/2405.15019v2), acesso em 2026-08-10. | Suporta transformar uma candidata em artefato executável e exigir um segundo sensor independente antes de registrá-la como habilidade. |
| A-MEM | Notas atômicas, links e reescrita de memórias vizinhas | A ablação sem links e evolução piorou todas as categorias avaliadas; aumentar a recuperação eventualmente estabilizou ou reduziu desempenho por introduzir ruído. [Paper](https://arxiv.org/html/2502.12110v11), acesso em 2026-08-10. | Suporta provenance e atualização explícita. A reescrita autônoma de memórias antigas sem histórico imutável é inadequada para regras do harness. |

Reflexion não é uma validação de regras permanentes. O método trabalha com
reflexões episódicas de poucas tentativas sobre a mesma tarefa, limita a
memória por janela e admite feedback interno. Sua própria ablação mostra dano
quando a reflexão de código não é fundamentada por testes.

### 2. Continual learning de agentes de código funciona como busca com arquivo, não como promoção cega

O Self-Improving Coding Agent mantém versões e resultados de benchmark, escolhe
o melhor agente observado e só então usa essa versão para a próxima mutação.
Durante uma execução, SWE-Bench Verified variou para cima e para baixo entre
iterações; os autores também relatam dependência de trajetória, ideias ruins
influenciando ideias posteriores e custo aproximado de USD 7.000 para 15
iterações. [Paper](https://arxiv.org/html/2504.15228v2), acesso em 2026-08-10.

O Darwin Gödel Machine também preserva um arquivo de candidatos em vez de
substituir a versão corrente. Depois de 80 iterações, o melhor agente passou de
20,0% para 50,0% no subconjunto de SWE-Bench usado; somente 51,3% dos agentes
gerados mantiveram funcionalidade básica de edição. O custo estimado da
execução foi de USD 22.000. [Paper](https://arxiv.org/html/2505.22954), acesso
em 2026-08-10. Esses resultados apoiam drafts, arquivo imutável, avaliação e
rollback. Não apoiam aplicar toda mutação ou todo aprendizado ao agente ativo.

### 3. Esquecer, contradizer e desativar são capacidades obrigatórias

ExpeL é a fonte mais direta para recorrência: uma candidata pode receber
`ADD`, `EDIT`, `UPVOTE` e `DOWNVOTE`; seu contador diminui com evidência
contrária e a candidata é removida ao chegar a zero. O valor inicial de dois é
uma escolha daquele experimento, não um limiar universal validado. Para o
`my-llm-kit`, nenhuma contagem baixa autoriza ativação.

MemoryAgentBench define recuperação, aprendizado em test-time, compreensão de
longo alcance e esquecimento seletivo como competências separadas e conclui
que os sistemas avaliados não dominam as quatro. [Paper](https://arxiv.org/abs/2507.05257),
acesso em 2026-08-10. LongMemEval separa indexação, recuperação e leitura e
testa atualização de conhecimento e abstenção, o que impede tratar “foi
recuperado” como “continua válido”. [Paper](https://arxiv.org/abs/2410.10813),
acesso em 2026-08-10.

STALE avalia conflitos implícitos, quando uma observação nova invalida uma
memória anterior sem negá-la literalmente. O melhor sistema avaliado alcançou
55,2% no agregado de resolução de estado, resistência a premissa e adaptação de
política. [Paper](https://arxiv.org/abs/2605.06527), acesso em 2026-08-10. Isso
refuta um registro somente aditivo de regras ativas. Toda candidata precisa de
proveniência, oposição, estado `stale`/`rejected` e revisão de substituição.

### 4. A fronteira de escrita é uma superfície de segurança

AgentPoison mostrou ataques a três agentes reais por envenenamento de memória
ou base de conhecimento, com taxa média de recuperação maliciosa de 81,2% e
degradação benigna média de 0,74%. [Paper](https://arxiv.org/html/2407.12784v1),
acesso em 2026-08-10. Um estudo posterior de dois agentes com memória
persistente encontrou influência entre sessões e observou que agentes que leem
e escrevem memória mais agressivamente são mais exploráveis. [Paper](https://arxiv.org/html/2606.04329v2),
acesso em 2026-08-10.

PASB testa agentes que decidem o que gravar. A falha posterior passou de 45,0%
em episódios restritos à sessão para 71,9% depois de conteúdo ser persistido;
repetição reforçou a promoção indevida, a perda de atribuição e o alargamento de
escopo. [Paper](https://arxiv.org/abs/2607.10526), acesso em 2026-08-10. Logo,
recorrência sem independência de fonte não é confirmação: pode ser apenas o
mesmo erro ou ataque repetido.

### 5. Texto pode virar gate, mas o gate precisa de oráculo independente

Há evidência primária para três níveis:

1. Reflexion gera testes, compila e usa os resultados como feedback, mas mostra
   que testes incorretos podem produzir falso positivo ou falso negativo.
2. Agentic Skill Discovery gera funções executáveis de recompensa e sucesso,
   faz checagem de conduta e usa um modelo visual independente antes de aceitar
   uma policy.
3. SEVerA mantém um pool de programas candidatos, elimina os que não verificam
   e só otimiza entre os verificados. Nos quatro domínios avaliados, o paper
   reporta zero violações nos testes retidos, com overhead de 1,9 a 2,5 vezes
   em dois dos domínios. [Paper](https://arxiv.org/html/2603.25111v2), acesso em
   2026-08-10.

A inferência de engenharia é restrita: uma observação textual recorrente pode
originar um draft de teste, linter ou guard. O texto não é o gate. O artefato
executável precisa falhar no caso negativo, passar no positivo e sobreviver à
validação completa do repositório antes de revisão.

## Discordâncias e limites

- ExpeL e AWM mostram transferência, mas usam benchmarks textuais/web e modelos
  específicos. O efeito não pode ser assumido em mudanças reais de software.
- AWM online aceita uma única trajetória classificada por avaliador neural;
  PASB, STALE e AgentPoison mostram por que esse limiar é inseguro para estado
  persistente.
- Voyager e vários trabalhos de skill discovery têm poucas repetições e
  ambientes fechados. São evidência de mecanismo, não de taxa esperada no
  `my-llm-kit`.
- A-MEM e sistemas comerciais de memória medem principalmente QA e lembrança,
  não redução de retrabalho de coding agents.
- Os resultados favoráveis de SICA e DGM vêm com busca cara sobre benchmarks e
  regressões intermediárias. Eles sustentam arquivo e seleção, não mutação
  automática do harness em cada execução.
- Não foi encontrado paper primário que valide “duas ocorrências textuais
  idênticas em mudanças distintas” como critério suficiente para tornar uma
  regra ativa.
- O `unlazy` traz duas práticas compatíveis com a evidência, gates de aceitação
  e verificação observável. O Depth Tree que entrega o orçamento completo a
  cada folha, a continuação forçada e a multiplicação exponencial de esforço
  não vêm acompanhados de experimento ou referência verificável no repositório
  da skill. Não devem entrar no harness como política.

## Decisão para o harness

**Veredito: hipótese parcialmente corroborada; ativação automática, refutada.**

Vale restaurar uma versão menor e desacoplada de `learning.py`, limitada a
estado sombra:

```text
estado e checks observados
→ observações automáticas com proveniência
→ candidatas draft agrupadas por recorrência independente
→ revisão humana ou gate executável validado
→ ativação feita por mudança normal e revisada
```

A versão anterior não deve voltar sem alterações:

- `PROMOTION_MIN_DISTINCT_CHANGES = 2` convertia recorrência em regra ativa sem
  avaliação com memória desligada;
- `ACTIVE_RULES.md` era carregado automaticamente pelo `impl`;
- skills eram materializadas como `SKILL.md`, embora ainda não revisadas;
- exportar e compilar learning fazia parte da condição de encerramento;
- não havia voto negativo, conflito, expiração, origem confiável nem medição de
  regressão causada pela recuperação.

A versão restaurada deve apenas validar registros, preservar evidência
imutável e compilar `DRAFT_CANDIDATES.md`. Cinco mudanças independentes são o
mínimo local para chamar um padrão de recorrente, conforme o protocolo desta
auditoria, mas não são aprovação nem evidência causal. Regras e skills nunca
são geradas ou carregadas por esse compilador. O `impl` termina mesmo que a
etapa de learning não seja executada ou falhe.

## Trial by fire

Antes de ativar a primeira candidata, executar um experimento pareado:

1. Congelar modelo, prompt, ferramentas, orçamento e conjunto de tarefas.
2. Separar tarefas de construção da memória e tarefas retidas de avaliação.
3. Rodar cada tarefa retida em duas condições, `memory_off` e `memory_on`, com
   ordem aleatória e o mesmo orçamento.
4. Medir sucesso do check final, hipóteses/reparos, duração, tokens/custo e
   regressão na suíte completa.
5. Registrar também recuperação sem uso e uso de candidata que piorou o
   resultado. Somente taxa de retrieval não mede benefício.
6. Rejeitar ou marcar `stale` quando a condição com memória não reduzir falha
   ou retrabalho, aumentar custo sem ganho, falhar fora do escopo, introduzir
   regressão ou depender de uma observação depois contradita.
7. Para gates executáveis, provar o negativo, restaurar o alvo e rodar a suíte
   completa. Para regras textuais, exigir revisão humana e um experimento
   `memory_off`/`memory_on`; contagem de ocorrências não substitui esse teste.

O primeiro ciclo deve permanecer em shadow mode. Sem dados pareados do próprio
`my-llm-kit`, a pesquisa autoriza construir o instrumento de avaliação, não
afirmar que a camada já melhora este harness.

## Fontes consultadas

- [Reflexion](https://arxiv.org/html/2303.11366v4), paper e [repositório oficial](https://github.com/noahshinn024/reflexion), acesso em 2026-08-10.
- [ExpeL](https://arxiv.org/html/2308.10144v3) e [repositório oficial](https://github.com/LeapLabTHU/ExpeL), acesso em 2026-08-10.
- [Voyager](https://arxiv.org/abs/2305.16291) e [repositório oficial](https://github.com/MineDojo/Voyager), acesso em 2026-08-10.
- [Agent Workflow Memory](https://arxiv.org/html/2409.07429) e [repositório oficial](https://github.com/zorazrw/agent-workflow-memory), acesso em 2026-08-10.
- [Agentic Skill Discovery](https://arxiv.org/html/2405.15019v2), acesso em 2026-08-10.
- [A-MEM](https://arxiv.org/html/2502.12110v11) e [repositório oficial](https://github.com/agiresearch/A-mem), acesso em 2026-08-10.
- [MemoryAgentBench](https://arxiv.org/abs/2507.05257) e [repositório oficial](https://github.com/HUST-AI-HYZ/MemoryAgentBench), acesso em 2026-08-10.
- [LongMemEval](https://arxiv.org/abs/2410.10813) e [repositório oficial](https://github.com/xiaowu0162/LongMemEval), acesso em 2026-08-10.
- [STALE](https://arxiv.org/abs/2605.06527), acesso em 2026-08-10.
- [AgentPoison](https://arxiv.org/html/2407.12784v1) e [repositório oficial](https://github.com/BillChan226/AgentPoison), acesso em 2026-08-10.
- [From Untrusted Input to Trusted Memory](https://arxiv.org/html/2606.04329v2), acesso em 2026-08-10.
- [Persistent Sycophancy Benchmark](https://arxiv.org/abs/2607.10526) e [repositório oficial](https://github.com/henrymao2004/agent-sycophancy), acesso em 2026-08-10.
- [A Self-Improving Coding Agent](https://arxiv.org/html/2504.15228v2) e [repositório oficial](https://github.com/MaximeRobeyns/self_improving_coding_agent), acesso em 2026-08-10.
- [Darwin Gödel Machine](https://arxiv.org/html/2505.22954), acesso em 2026-08-10.
- [SEVerA](https://arxiv.org/html/2603.25111v2), acesso em 2026-08-10.
- [Memp](https://aclanthology.org/2026.findings-acl.866/), acesso em 2026-08-10.
- [MemGPT](https://arxiv.org/abs/2310.08560) e [Letta](https://docs.letta.com/), acesso em 2026-08-10.
- [Mem0](https://arxiv.org/abs/2504.19413) e [repositório oficial](https://github.com/mem0ai/mem0), acesso em 2026-08-10.
- [unlazy](https://github.com/Leonxlnx/unlazy), fonte da skill, acesso em 2026-08-10.
