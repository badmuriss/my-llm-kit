# Research finding: contenção de testes e Markdown gerados por IA

## Protocol

- Question: Quais mecanismos reduzem testes e documentação redundantes gerados por agentes sem perder regressões importantes, e como isso deve mudar o harness do my-llm-kit?
- Decision criterion: Preferir gates que reduzam criação e execução redundantes, preservem testes de comportamento e contratos de alto risco, sejam observáveis no capsule/resultado e permitam exceção explícita quando a tarefa exigir.
- Falsifier: A recomendação falha se um conjunto representativo de tarefas do kit mostrar que o default mínimo perde regressões relevantes, aumenta retrabalho ou deixa contratos públicos sem verificação em comparação com a política atual.
- Risk: material
- Credits used: 0

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---:|---|
| Literatura sobre geração e manutenção de testes | paper-search local | buscas arXiv por redundância, diversidade, evolução e smells | Concluído; resultados foram triados e as fontes originais abertas quando disponíveis. | 0 | Rota local preferida para literatura científica; não houve chamada paga. |
| Artigos primários | Web público | abertura direta de páginas arXiv | Concluído; artigos aceitos foram consultados nas páginas oficiais. | 0 | Nenhum. |
| Práticas de teste e seleção de impacto | Web público | Fowler, Microsoft Learn e GitHub Docs | Concluído; documentação primária/oficial usada para operacionalizar os achados. | 0 | Nenhum. |
| Sinal de manutenção e documentação gerada | Web público | arXiv, páginas de preprint | Concluído; usado como evidência contextual, sem transformar amostras observacionais em regra universal. | 0 | Nenhum. |

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| Geração de JUnit avaliada em dois benchmarks produziu smells como asserts duplicados e testes vazios; nenhum modelo passou de 2% de cobertura no SF110 naquele estudo. | https://arxiv.org/abs/2305.00418 | 2026-08-26 | None | yes | yes | partial | unknown | limited |
| EvoGPT combina geração por LLM com otimização SBST e impõe diversidade explícita, reparo e geração guiada por cobertura. | https://arxiv.org/abs/2505.12424 | 2026-08-26 | None | yes | yes | yes | unknown | accepted |
| Sob evolução semântica, testes gerados perderam desempenho e modelos descartaram muitos testes baseline, mostrando sensibilidade a mudanças lexicais. | https://arxiv.org/abs/2603.23443 | 2026-08-26 | None | yes | yes | yes | unknown | accepted |
| HGEN trata documentação como pipeline em estágios e constrói hierarquias de documentos; isso mostra que geração de docs é uma transformação com custo de manutenção, não um subproduto gratuito. | https://arxiv.org/abs/2408.05829 | 2026-08-26 | None | yes | yes | yes | unknown | limited |
| Repositórios que sinalizam uso de GenAI apresentaram READMEs mais longos, com mais headers e blocos de código, e deslocamento de custo para verificação e manutenção. | https://arxiv.org/abs/2607.21079 | 2026-08-26 | None | yes | yes | yes | unknown | limited |
| Um estudo de PRs de documentação encontrou mais PRs desse tipo submetidos por agentes e pouca modificação posterior por humanos, levantando risco de QA documental. | https://arxiv.org/abs/2601.20171 | 2026-08-26 | None | yes | yes | yes | unknown | limited |
| A pirâmide recomenda menos testes em níveis mais altos e teste de comportamento observável; não recomenda uma cópia de cada cenário interno. | https://martinfowler.com/articles/practical-test-pyramid.html | 2026-08-26 | None | yes | yes | yes | yes | accepted |
| Test Impact Analysis reduz a quantidade de testes executados escolhendo os mais prováveis de detectar uma falha nova e separando checks rápidos de suites lentas. | https://martinfowler.com/articles/rise-test-impact-analysis.html | 2026-08-26 | None | yes | yes | yes | unknown | accepted |
| A documentação do Azure recomenda periodicidade configurável de todos os testes, fallback seguro para tipos desconhecidos e validação comparando seleção impactada com a suite completa. | https://learn.microsoft.com/da-dk/azure/devops/pipelines/test/test-impact-analysis?view=azure-devops-2022 | 2026-08-26 | None | yes | yes | yes | unknown | accepted |
| A documentação do GitHub mostra que o escopo do prompt determina os cenários gerados e recomenda revisar a saída antes de incorporá-la. | https://docs.github.com/en/copilot/tutorials/write-tests | 2026-08-26 | None | yes | yes | yes | yes | accepted |

## Findings

### O problema é real, mas a solução não é apagar cobertura por contagem

Há evidência direta de que geração automática cria testes com duplicação, testes vazios e baixa utilidade em alguns contextos, mas a força do resultado depende do benchmark e do modelo. O estudo de JUnit relata asserts duplicados e testes vazios, além de cobertura acima de 80% em um benchmark e abaixo de 2% em outro, acessado 2026-08-26: https://arxiv.org/abs/2305.00418. A consequência prática é revisar valor comportamental, não aceitar o volume produzido como evidência.

Os trabalhos mais promissores reduzem redundância por seleção, não por poda cega. EvoGPT impõe diversidade, usa reparo e gera asserts guiados por cobertura, acessado 2026-08-26: https://arxiv.org/abs/2505.12424. O estudo de evolução mostra que suites podem degradar mesmo quando o código muda sem alterar a semântica e que modelos descartam testes baseline diante de mudanças lexicais, acessado 2026-08-26: https://arxiv.org/abs/2603.23443. Portanto, preservar uma suite existente e adicionar somente uma regressão que refute o bug é mais seguro do que regenerar a suite inteira.

### A regra operacional recomendada para o harness

O default de desenvolvimento deve ser: nenhuma criação nova de teste ou Markdown suplementar. O agente primeiro tenta o check já declarado, o typecheck, o lint ou a inspeção direta mais barata. Um novo teste só entra quando cobre uma lacuna observável em bug reproduzível, segurança, integridade de dados ou contrato público; nesse caso, reutiliza o arquivo existente e cria no máximo um teste de regressão focado por defeito. Essa política é uma aplicação local dos princípios de testar comportamento observável, evitar testes triviais e manter poucos testes de níveis altos, acessados 2026-08-26: https://martinfowler.com/articles/practical-test-pyramid.html.

O mesmo gate vale para Markdown. O agente atualiza um documento existente apenas quando a mudança altera contrato, uso ou decisão que precisa ficar persistida. Não deve criar diário de status, README paralelo, plano duplicado ou relatório narrativo para provar que executou um check; o WorkerResult e os receipts já são a trilha estruturada. HGEN confirma que documentação gerada forma uma hierarquia que precisa ser mantida, acessado 2026-08-26: https://arxiv.org/abs/2408.05829. Evidência observacional recente também associa adoção de GenAI a READMEs mais longos e custo deslocado para verificação, acessado 2026-08-26: https://arxiv.org/abs/2607.21079.

O prompt importa. A documentação do GitHub mostra que pedir cada cenário explicitamente faz o agente gerar um caso para cada cenário e recomenda revisar a saída, acessado 2026-08-26: https://docs.github.com/en/copilot/tutorials/write-tests. O capsule do kit deve, portanto, declarar a política mínima antes da aceitação da tarefa, em vez de deixar o modelo inferir que “desenvolver” significa escrever uma suite completa.

### Executar menos testes sem perder segurança

Criação e execução são problemas diferentes. Para execução local, a política deve preferir o Check único da tarefa e seleção por impacto quando houver mapa confiável entre arquivos e testes. Test Impact Analysis foi proposto justamente para reduzir a quantidade executada, priorizar testes com maior chance de detectar a falha nova e deixar suites lentas para uma etapa posterior, acessado 2026-08-26: https://martinfowler.com/articles/rise-test-impact-analysis.html. A orientação oficial do Azure acrescenta duas salvaguardas: fallback para todos os testes quando o impacto é desconhecido e validação periódica comparando a seleção com a suite completa, acessado 2026-08-26: https://learn.microsoft.com/da-dk/azure/devops/pipelines/test/test-impact-analysis?view=azure-devops-2022.

No my-llm-kit, isso significa não inventar um segundo ou terceiro Check para cada pacote. O task graph conserva um Check declarativo; o coordenador pode rodá-lo e, em mudanças amplas ou de alto risco, executar uma suite adicional como decisão explícita. A política não transforma uma contagem de testes em score e não bloqueia uma regressão necessária, ela exige motivo observável.

### Limites da evidência

Os números e resultados acima pertencem a benchmarks, preprints ou amostras observacionais específicas. Eles não estabelecem uma taxa universal de defeitos nem um limite universal de testes por tarefa. A amostra de documentação sobre agentes é útil para sinalizar risco de manutenção, mas não mede causalidade no my-llm-kit. A política deve ser medida em shadow mode por tarefa: arquivos de teste e Markdown criados, regressões detectadas, retrabalho, tempo do Check e falsos positivos.

## Disagreements

- A pirâmide favorece muitos testes unitários rápidos e poucos testes de alto nível, enquanto a redução agressiva de artefatos pode ser perigosa quando uma mudança introduz um novo contrato. A síntese adotada é reduzir duplicação e testes de implementação, preservando testes que refutam comportamento de risco. https://martinfowler.com/articles/practical-test-pyramid.html, accessed 2026-08-26.
- EvoGPT melhora diversidade em um sistema de geração e busca, enquanto o estudo de evolução mostra instabilidade de suites sob mudanças lexicais e semânticas. Isso não é contradição: diversidade ajuda a geração inicial, mas não substitui manutenção e seleção incremental. https://arxiv.org/abs/2505.12424 e https://arxiv.org/abs/2603.23443, accessed 2026-08-26.
- HGEN reporta utilidade de hierarquias geradas, enquanto os estudos de manutenção e PRs alertam para volume e verificação humana. A conclusão limitada é gerar documentação sob demanda e atualizar uma fonte canônica, não proibir documentação automatizada. https://arxiv.org/abs/2408.05829, https://arxiv.org/abs/2607.21079 e https://arxiv.org/abs/2601.20171, accessed 2026-08-26.

## Open questions

- Qual conjunto pequeno de tarefas do kit mede se um teste adicional detecta uma regressão que o Check existente não detecta?
- O harness consegue construir um mapa confiável de impacto entre arquivos de produção e testes sem depender de heurística frágil?
- Quais documentos são fontes canônicas e quais são apenas artefatos temporários que podem ser substituídos por receipts?
- Qual exceção explícita deve autorizar mais de um teste de regressão quando o risco ou o contrato exigir?
- Como comparar a política mínima em Host, Orca e OpenCode sem confundir provider, modelo, cache e tarefa?

## Council review

- Status: not run
- Reason: não houve pedido de `--council`; as fontes primárias abertas sustentam uma política conservadora de seleção e validação, enquanto a eficácia quantitativa no kit ainda requer medição local.
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://arxiv.org/abs/2305.00418, accessed 2026-08-26.
- https://arxiv.org/abs/2505.12424, accessed 2026-08-26.
- https://arxiv.org/abs/2603.23443, accessed 2026-08-26.
- https://arxiv.org/abs/2408.05829, accessed 2026-08-26.
- https://arxiv.org/abs/2607.21079, accessed 2026-08-26.
- https://arxiv.org/abs/2601.20171, accessed 2026-08-26.
- https://martinfowler.com/articles/practical-test-pyramid.html, accessed 2026-08-26.
- https://martinfowler.com/articles/rise-test-impact-analysis.html, accessed 2026-08-26.
- https://learn.microsoft.com/da-dk/azure/devops/pipelines/test/test-impact-analysis?view=azure-devops-2022, accessed 2026-08-26.
- https://docs.github.com/en/copilot/tutorials/write-tests, accessed 2026-08-26.

## Trial by fire

- Primary-source claims: os seis preprints arXiv sustentam apenas os resultados dos próprios estudos; Fowler sustenta princípios de pirâmide e impacto; Microsoft sustenta seleção impactada com fallback e validação; GitHub sustenta a relação entre escopo do prompt e quantidade de cenários gerados.
- Secondary-only claims: None. Não usei snippets ou blogs como evidência final.
- Volatile claims: recomendações de ferramentas e comportamento de providers devem ser reconfirmados ao implementar integração específica; os resultados de preprints podem mudar em versões posteriores.
