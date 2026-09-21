# Jev no my-llm-kit

## Protocol

- Question: Onde Jev, Jev Ultrafast, Cua, fast-jev-compaction e Foreman ajudam o harness existente, preferindo OpenRouter?
- Decision criterion: Integrar comportamento útil e verificável sem duplicar o coordenador, perder proveniência de checks ou sobrescrever configuração instalada.
- Falsifier: Falha no endpoint, ação incorreta no browser, perda de contexto obrigatório ou supervisão que interrompe trabalho útil invalida a adoção automática correspondente.
- Risk: material
- Credits used: 0

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Ler fontes oficiais conhecidas | HTTP direto e host web open | GitHub, TypeSafe, OpenRouter | READMEs, código e API lidos | 0 | Fontes oficiais conhecidas não exigem proxy |
| Ler índice TypeSafe | HTTP direto | docs.typesafe.ai/llms.txt | Sucesso após falha do leitor web | 0 | Erro no leitor web |
| Encontrar referência de decisões OpenRouter | HTTP direto e host web open | Páginas de documentação tentadas | Rotas tentadas indisponíveis; modelo público e chamada real confirmados | 0 | Não inferir o contrato de chat a partir do nome do modelo |
| Consultar Cloudflare | HTTP direto e host web open | Catálogo/modelo Workers AI | Acesso falhou nas rotas tentadas | 0 | Disponibilidade de Jev no Workers AI não confirmada |
| Validar OpenRouter | API autenticada | /api/alpha/decisions | Probe, browser e compaction sintéticos passaram | 0 | Não aplicável |

Zero significa créditos de coleta conhecidos, não custo total zero. Houve inferência
paga na OpenRouter. O teste de browser bem-sucedido reportou custo de 0.000388596
na soma do campo `usage.cost`, incluindo o helper de texto. O total da sessão não
foi medido: inclui probes, compaction e uma execução cujo screenshot falhou. Nenhuma
chave foi registrada. Nenhuma conversa real foi enviada ao experimento de compaction.

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| Jev usa perguntas tipadas e retorna decisões | https://docs.typesafe.ai/api.md | 2026-09-21 | API lida; sem cópia vendorizada | yes | yes | yes | no | accepted |
| OpenRouter disponibiliza Jev | https://openrouter.ai/typesafe/jev-1.13 | 2026-09-21 | Página lida e probe real | yes | yes | yes | yes | volatile |
| Ultrafast opera no DOM com conjunto limitado de ações | https://github.com/browser-use/jev-ultrafast | 2026-09-21 | Commit 1231850a0bf1a0c0341fe408ef1668dbbfdfac46 | yes | yes | yes | no | accepted |
| Foreman é experimental e tem runtime próprio | https://github.com/thruwire/foreman | 2026-09-21 | Commit a7d21d18d306a0cb9f3e15acefbdb5663521405c | yes | yes | yes | no | accepted |
| Compaction oferece biblioteca e hook específico de Claude | https://github.com/tamaratran/fast-jev-compaction | 2026-09-21 | Commit e3f262a7f4d42bd8dd32ced30d26176f7cb545b0 | yes | yes | yes | no | accepted |
| App Server expõe pedido de compactação nativa | https://learn.chatgpt.com/docs/app-server | 2026-09-21 | Docs e schema local Codex 0.155.1 | yes | yes | yes | no | accepted |
| Cua oferece driver, isolamento e avaliação separados | https://github.com/trycua/cua | 2026-09-21 | README lido; driver v0.28.2 testado | yes | yes | yes | no | accepted |

## Findings

**Adotar Jev no browser, via OpenRouter.** O kit agora distribui `computer-use`
como skill opcional, com runner fixado no commit testado. A integração instalada
pelo outro agente permanece intacta. `impl` encaminha tarefas web para a skill;
o Agent Graph explicita propriedade de browser, fallback e verificação independente.
A integração portátil não depende de modificar o checkout global do usuário.

Jev escolhe ações e alvos observados. Texto de campos continua vindo de um modelo
generativo separado. A rota de decisão é `https://openrouter.ai/api/alpha/decisions`;
não basta trocar o modelo em `chat/completions`. Preferir OpenRouter aqui é uma
decisão baseada na preferência do usuário e nos testes reais, não uma comparação
completa de provedores. Workers AI ficou sem confirmação de disponibilidade.

**Reaproveitar supervisão semântica do Foreman, mantendo o coordenador atual.** A demonstração prova seu
fluxo de execução, não superioridade ou precisão semântica. Seu runtime controla
workers, steering, retries e término, sobrepondo-se ao diário, geração do
coordenador e checks do kit. Recomendação futura: avaliar apenas julgamentos
consultivos sobre observações limitadas do runtime existente e comparar falsos
alarmes, intervenções úteis, custo e tempo total. Não usar probabilidades como
permissão, nota de aceitação ou prova de que os testes bastam.

**Compaction é um experimento de host, não uma alteração de cápsula.** A biblioteca
aceita `apiKey`, `baseUrl` e `model`, e funcionou na OpenRouter. O plugin depende
de function hooks early-access do Claude; não foi instalado nem validado no host.
`context_capsules.py` possui referências tipadas, hashes e exclusões de transcript;
comprimir conversas não equivale a preservar esses contratos. Além disso, o estado
usado para julgar retenção omite o conteúdo integral dos resultados de ferramentas:
uma decisão pode perder informação valiosa que só existia nesses resultados.

**Manter Cua como candidato para isolamento e avaliações de desktop.** Driver,
Fleets, Lume e Bench têm funções distintas. O driver básico foi exercitado localmente;
isso não valida fleets, VMs, captura, cliques, macOS ou Windows. O kit já dispõe de
Orca; não há evidência suficiente neste teste para substituir esse backend.

Outros usos plausíveis do Jev: ordenar fontes opcionais antes de compor uma cápsula,
classificar um erro para sugerir uma recuperação e apontar inconsistências entre
resultado e objetivo. São hipóteses, não funcionalidades implementadas. Regras
conhecidas, checks determinísticos e autorização continuam em código. Um avaliador
em toda tool call acrescentaria latência e outro modo de falha sem benefício medido.

## Local experiments

| Experimento | Evidência observada | Limite |
|---|---|---|
| Probe OpenRouter inicial | Decisão tipada em 0,626 s; modelo resolvido typesafe/jev-1.13-20260917 | Um input sintético |
| Probe do runner pinado | DONE em 1,254 s | Valida transporte e parsing, não conclusão de tarefa real |
| Browser Linux/Chrome isolado | Nome Ana, plano Pro, Save; três ações, quatro decisões, 2,201 s no relógio do agente | Um formulário; exclui setup, observação inicial, screenshot e cleanup |
| Verificação do browser | DOM retornou Saved: Ana / Pro; PNG inspecionado com vision | Não é benchmark contra Orca/Playwright |
| Foreman | 97 testes upstream passaram; demo com workers/modelo falsos chegou a FINISH | Sem worker real e sem avaliar precisão do Jev supervisor |
| Compaction | 29 testes passaram; build e typecheck passaram; chamada real em 605 ms removeu leitura explicitamente obsoleta, preservou texto, último par e pareamento | Fixture deliberadamente simples; redução em caracteres, não economia medida de tokens |
| Cua v0.28.2 | Doctor: X11 :99 e AT-SPI disponíveis; daemon temporário respondeu list_apps com apps/processes; encerrou | Apenas descoberta; nenhuma ação GUI validada |
| Kit | Quatro testes de roteamento/execução e seis testes existentes de instalador passaram; uvx ruff check . passou; três skills validadas | PowerShell nativo e macOS não executados |

O teste reproduzível está em `skills/computer-use/tests/smoke_browser.py`.
Evidência local: `.visual-evidence/jev-browser-integration/result.json`, `saved.png`
e `observations.md`. A execução final, após adicionar retenção de evidências ao runner, também passou: 3,097 s no relógio do agente; `final-run/final/page.json`, PNG e observações estão preservados. O primeiro screenshot expirou em uma aba headless de fundo;
a correção ativa somente a aba do perfil isolado antes da captura. A segunda
execução passou. Nenhuma preferência de foco do Chrome do usuário foi alterada.

O primeiro comando pytest do Foreman selecionou o diretório errado porque
`uv --project` não troca cwd; foi corrigido e a suíte upstream executada no checkout
correto. Não foi tratado como falha do projeto nem como evidência de aprovação.

Os checkouts externos ficaram em `/tmp/my-llm-kit-jev-research` para inspeção.
Os processos de teste foram encerrados. Nenhum instalador real do kit foi rodado.
`--full`/`-Full` já descobre skills vendorizadas; o perfil core não foi ampliado.
Instaladores preservam diretórios de skills pertencentes ao usuário, portanto a
skill global existente não é silenciosamente substituída pela versão do repositório.

## Follow-up: Codex dentro do Orca

A prioridade confirmada pelo usuário é Codex no Orca. Esta análise aprofunda a
comparação; não ativou outro runtime, hook ou supervisor.

### O que foi integrado antes

- `computer-use`: skill opcional e runner Jev/OpenRouter com evidências locais.
- `impl/SKILL.md`: encaminhamento de tarefas de browser para essa skill.
- `agent-graph/SKILL.md` e referência: limites de propriedade e verificação de browser.
- Nenhuma mudança em scheduler, reducer, journal, cápsulas, grades ou compactação.

### Compaction: valor real, encaixe incompleto no host prioritário

Versões locais observadas: Codex 0.155.1, Claude 2.1.246, OpenCode 1.18.30.
O plugin upstream de Claude declara function hooks de 2.1.274+; não basta instalar
esse plugin no Codex. Além disso, seu hook lê `TYPESAFE_API_KEY` e não expõe
`baseUrl` como a biblioteca. O sucesso da biblioteca na OpenRouter não prova
que o plugin use essa chave ou endpoint sem adaptação.

No checkout Orca `5bd9dcef5b`,
`src/main/codex/codex-structured-session-adapter.ts:224` chama
`thread/compact/start` com apenas `threadId`. O schema gerado pelo Codex instalado
confirma esse parâmetro único. A documentação oficial também descreve essa chamada
como solicitação de compactação nativa, não como callback para substituí-la:
https://learn.chatgpt.com/docs/app-server, accessed 2026-09-21.

Há `ThreadResumeParams.history`, mas sua descrição local diz
`[UNSTABLE] FOR CODEX CLOUD - DO NOT USE`. Ele não é um contrato suportado para
reescrever o histórico de uma sessão Orca ativa. `thread/inject_items` acrescenta
itens, portanto não remove os antigos nem substitui o contexto. Não alterei o
Orca nem arquivos de sessão para contornar essa limitação.

**Recomendação:** compaction seletiva merece investigação, especialmente em tarefas
com grandes resultados de ferramentas. Para Codex/Orca, falta primeiro uma
extensão suportada no host ou uma mudança deliberada no runtime Codex; não é uma
integração resolvida por skill ou configuração do my-llm-kit. Um fork do Codex
teria custo contínuo de manutenção que este experimento não demonstrou compensar.

A biblioteca preserva texto do usuário e assistente e conserva pares de chamada e
resultado, o que é útil. Porém, não reduz conversas dominadas por prosa e não
necessariamente evita compactação generativa posterior. Redução em caracteres
não mede tokens faturados, perda de cache nem custo de reler ferramentas.

Reproduzi um limite estrutural sem fazer inferência: dois históricos com a mesma
chamada de deploy, mas resultados diferentes de igual tamanho, produziram o mesmo
`fitState`. Um resultado continha um ID remoto irrecuperável; o outro era apenas
um preview descartável. A chamada não estava protegida por recência. Como o
modelo recebe entradas idênticas, ele não pode diferenciar o que precisa preservar.
Isso não demonstra que apagaria o ID em toda execução; demonstra que falta a
informação necessária para decidir corretamente nos dois casos.

Uma adaptação aceitável precisaria proteger operações com efeitos, IDs ativos,
permissões, falhas pendentes e evidências de aceitação; limitar candidatos a dados
recuperáveis; incluir conteúdo relevante dos candidatos na análise; manter pares
atômicos e oferecer fallback nativo. Antes de ativar, comparar continuação de
tarefas, releituras, erros e custo total, não somente tamanho do histórico.

### Foreman versus Agent Graph

| Capacidade | Agent Graph atual | Foreman | Decisão de reaproveitamento |
|---|---|---|---|
| Dependências e escrita concorrente | Grafo, caminhos, conflitos e grades | V1 com um worker por vez | Manter o agendamento do kit |
| Estado e recuperação | Journal canônico, geração do coordenador, attempts e receipts | Estado/eventos próprios e política de retries | Não importar segundo estado de execução |
| Aceitação | Checks vinculados à tentativa e verificação do coordenador | Thresholds de probabilidades e resultado do verifier | Manter gates existentes |
| Observação durante execução | Orca poll lê saída com cursor; Host poll lê resultado publicado | Loop independente lê saída, diff e instruções | Reaproveitar a ideia; disponibilidade de observação depende do driver |
| Detecção semântica | Não há classificador automático de looping ou desvio no caminho inspecionado | worker_stuck, work_off_track, agents_md_drift, meaningful_progress | Melhor contribuição incremental |
| Enviar orientação | Driver.send existe; Orca entrega mensagem; Host exige entrega pelo host | Steering no turno ativo via App Server | Reusar transporte atual e conferir capacidade/recibo, sem substituir dispatcher |
| Frequência e reação | Coordenador decide quando observar e orientar | Agrupa eventos, limita frequência e aguarda recuperação após orientação | Aproveitar debounce, cooldown e orçamento próprios, sem copiar thresholds |
| Compaction de contexto | Cápsulas limitadas e histórico do host separado | Não implementa a biblioteca de compaction | São propostas independentes |

Locadores locais: `graph_core.py:481` (conflitos), `agent_graph.py:3916`
(sync), `drivers/orca.py:1956` (poll), `drivers/orca.py:1998` (send),
`drivers/host.py:634` (entrega dependente do host), `run_progress.py:251`
(projeção determinística) e `context_capsules.py:672` (orçamento).
Todos sob `skills/agent-graph/scripts/`.

A observação padrão do Foreman popula `test_results=[]`; resultados de testes
podem aparecer como texto de stdout/diff ou relatos de verificação. Isso não tem
a força dos checks vinculados às tentativas que o kit já mantém. Sua política
pode concluir por scores altos e pode dispensar verifier se `needs_verification`
for baixo. Também escala e termina workers após repetidas falhas do supervisor.
Esses comportamentos não são melhorias demonstradas para o kit.

**O que vale pegar:** um avaliador consultivo pequeno, chamado pelo coordenador
existente, sobre observações novas e limitadas. Priorizar repetição improdutiva,
desvio do objetivo e descumprimento semântico de instruções. Violações exatas de
caminho e checks continuam determinísticas. Usar o `poll` e os receipts atuais,
associar o julgamento a run/attempt/generation/cursor e descartá-lo se a observação
ficou obsoleta. Começar sem interromper workers nem aprovar tarefas automaticamente.

Após o piloto, orientações podem usar `Driver.send`, com limite de intervenções e
intervalo de recuperação. A assinatura já existe, mas isso não prova suporte a
steering no turno ativo em todo host. Não há hoje um comando portátil completo de
supervisão semântica: observação, política e entrega precisam ser conectadas e
testadas. Copiar a ideia não exige adotar a dependência Foreman inteira.

### Probes de supervisão

Enviei seis observações sintéticas pela OpenRouter usando as dez perguntas
originais de Foreman, sem lançar workers reais ou enviar históricos privados.
Modelo resolvido: `typesafe/jev-1.13-20260917`; esforço não se aplica ao modelo de
decisões. Cada fixture foi avaliada uma vez. Registro completo em
`research/2026-09-21-jev-harness-probes.json`, incluindo estados, scores, latência,
usage e trechos do schema local.

| Cenário | Sinal observado |
|---|---|
| Implementação progredindo | meaningful_progress 0.91; worker_stuck 0.11 |
| Espera legítima por teste | worker_stuck 0.16; meaningful_progress 0.79 |
| Mesma falha repetida sem alteração | worker_stuck 0.92 |
| Trabalho fora do pedido | work_off_track 0.98 |
| Edição contra instrução explícita | agents_md_drift 0.96 |
| “Pronto” apesar de teste falhando | ready_to_finish 0.02; tests_sufficient 0.03 |

Latências observadas: 351–535 ms. Soma de `usage.cost`: 0.000208614.
São fixtures pequenas e explícitas, não precisão medida em projetos reais nem
calibração de thresholds. O resultado sustenta testar essa camada consultiva;
não sustenta automatizar interrupção, escalonamento ou aprovação.

Prioridade prática para o ambiente escolhido: browser já disponível; piloto de
supervisão consultiva no Agent Graph é viável no kit; substituição da compaction
no Codex/Orca depende de uma extensão real do host. Uma simples chamada Jev não
remove essa dependência.

## Disagreements

O relato anterior dizia que Browser Harness estava conectado. Nesta sessão,
`daemon_browser_ready()` para o daemon selecionado retornou falso. Isso pode ser
estado ou ambiente diferente; não invalida o teste anterior. O smoke usou conexão
isolada própria e a encerrou. O antigo `jev-agent --check` checa diretório, uv e
credenciais, portanto sua mensagem ready não comprova conexão de browser.

## Open questions

- Confiabilidade e custo em uma cesta real de tarefas do usuário, incluindo falhas e recuperação.
- Benefício da supervisão consultiva em tarefas reais; os probes sintéticos do follow-up foram promissores, mas não a calibram.
- Compatibilidade do hook de compaction com cada versão/host efetivamente usado.
- Ganhos do Cua sobre Orca em tarefas de desktop ou ambientes isolados.
- Disponibilidade e contrato de Jev no Workers AI; não confirmado nesta pesquisa.

## Council review

- Status: not run
- Reason: Fontes primárias e testes locais; nenhum disparador de council. Sem revisão delegada.
- Accepted findings: Não aplicável.
- Rejected findings: Não aplicável.

## Sources consulted

Todas acessadas em 2026-09-21:

- https://learn.chatgpt.com/docs/app-server, accessed 2026-09-21.
- https://docs.typesafe.ai/llms.txt, accessed 2026-09-21.
- https://docs.typesafe.ai/api.md, accessed 2026-09-21.
- https://docs.typesafe.ai/primitives/choice.md, accessed 2026-09-21.
- https://docs.typesafe.ai/patterns/fan-out.md, accessed 2026-09-21.
- https://openrouter.ai/typesafe/jev-1.13, accessed 2026-09-21.
- https://github.com/browser-use/jev-ultrafast, accessed 2026-09-21.
- https://github.com/thruwire/foreman, accessed 2026-09-21.
- https://github.com/tamaratran/fast-jev-compaction, accessed 2026-09-21.
- https://github.com/trycua/cua, accessed 2026-09-21.
- https://github.com/trycua/cua/blob/main/libs/cua-driver/docs/linux-desktop-validation.md, accessed 2026-09-21.
- https://github.com/trycua/cua/releases/tag/cua-driver-rs-v0.28.2, accessed 2026-09-21.

## Trial by fire

- Primary-source claims: Modelo, API, limitações e arquitetura conferidos nas fontes dos projetos; integração browser e biblioteca compaction exercitadas na OpenRouter.
- Secondary-only claims: Nenhuma conclusão material depende só de fonte secundária.
- Volatile claims: Disponibilidade de modelo, endpoint alpha, versões e compatibilidade de hooks exigem reconfirmação ao atualizar.
- Limitação principal: Testes sintéticos e suítes upstream não demonstram ganho geral de produtividade nem segurança de supervisão automática.

## Implementação posterior autorizada: avaliador consultivo

O comando `assess` agora usa o journal existente do Agent Graph e o Jev pela
OpenRouter para avaliar a observação mais recente de um worker. Não foi instalado
o scheduler Foreman. O resultado é consultivo, sem mensagens, interrupções ou
notas automáticas. Nenhum hook de compaction foi adicionado.

O smoke sintético da implementação, em 2026-09-21, retornou o modelo
`typesafe/jev-1.13-20260917`, 611 tokens de entrada, 100 de saída e custo informado
de US$ 0,000025662. A evidência recebeu 0,43, abaixo do limiar heurístico de 0,8,
e nenhuma orientação foi emitida. Isso verifica transporte e filtragem, não
calibração ou ganho de produtividade em sessões reais. O resultado está no
JSON de probes, em `implemented_evaluator_synthetic_smoke`.

As observações são extraídas dos formatos de transcript e terminal do Orca.
Ainda não houve validação ponta a ponta em um worker real Codex dentro do Orca.
As regressões usam fixtures desses contratos. Windows permanece não verificado.
