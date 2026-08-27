# Orca Maestro: Canvas operacional por worktree, orquestração e lifecycle

## Protocol

- Question: Como integrar ao Orca e ao my-llm-kit um Canvas operacional inspirado no Open-Maestri, com notas, conexões, terminais visíveis e delegação entre agentes, sem misturar worktrees, inflar o contexto do coordenador ou agravar vazamentos de processos e memória?
- Decision criterion: A proposta precisa funcionar como superfície embutida por worktree, manter o journal/runtime como fonte de verdade, suportar agent/model/effort e current/child/cloud placement, possuir mutações concorrentes com receipts, encerrar a árvore de processos no host correto e continuar útil sem Orca por meio do mesmo schema de projeção.
- Falsifier: Rejeitar a proposta se o Canvas virar a fonte canônica da execução, depender de `cwd` ou do workspace visual ativo, importar nós de vários worktrees, montar um renderer pesado por card, criar agente sem receipt do runtime, perder intenção de cleanup após restart ou exigir copiar código GPL para o Orca MIT.
- Risk: material

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Fallback reason |
|---|---|---|---|---|
| Descobrir o projeto Maestri aberto e suas fontes | ScrapingDog | Google Search API `/google` | Encontrou `zlh-428/open-maestri`; a conclusão foi verificada no repositório primário | None |
| Consultar implementação e licença em revisão estável | GitHub e git local | clone + arquivos no commit `6db452e5d1663bfdd4666f757987b0a1affe073d` | Código, README e GPL-3.0 inspecionados diretamente | None |
| Auditar os seams reais do Orca | GitHub e git local | clone + arquivos no commit `4e058d4a52ea4653a5cf86fac271c8010334361e` | Renderer, runtime, CLI, PTY, SSH, worktree e skills mapeados | None |
| Verificar problemas e propostas já abertas no Orca | GitHub CLI | `gh issue view` e `gh pr view` | Issues e PRs relevantes abertos foram comparados com o HEAD auditado | None |
| Produzir fontes navegáveis dos repositórios | Repomix via ingest | extração Markdown orientada por áreas | Cinco recortes estruturados gerados e verificados | None |
| Fazer a busca ampla anterior sobre Canvas de agentes | Firecrawl | search | Falhou por créditos insuficientes | ScrapingDog foi usado nesta rodada; a busca nativa anterior ficou apenas como lead |

## Claim ledger

| Claim | Source | Accessed | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|
| Open-Maestri é GPL-3.0 e Orca é MIT; copiar a implementação Swift para o Orca criaria incompatibilidade de distribuição sem uma decisão jurídica/licenciamento | https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/LICENSE<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/LICENSE | 2026-08-20 | yes | yes | yes | yes | accepted |
| Open-Maestri implementa Canvas infinito com terminal, note, file tree, portal, text, drawing e links entre terminais | https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/README.md | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O menu de Canvas vazio do Open-Maestri cria nós na posição do cursor | https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/Sources/Canvas/Core/CanvasViewportView%2BContextMenu.swift | 2026-08-20 | yes | yes | yes | unknown | accepted |
| `recruit` cria um terminal e conecta automaticamente o agente chamador ao novo agente | https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/Sources/InterAgent/Handlers/MaestroHandlers.swift | 2026-08-20 | yes | yes | yes | unknown | accepted |
| A implementação de recruit/connect/dismiss do Open-Maestri usa workspace ativo e registries globais, não uma identidade de workspace carregada no request | https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/Sources/InterAgent/Handlers/MaestroHandlers.swift<br>https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/Sources/Connection/ConnectionManager.swift | 2026-08-20 | yes | yes | yes | unknown | accepted |
| Orca já possui pan, zoom, SVG, layout, menus e cena de agentes que podem ser reutilizados para uma superfície Maestro | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/AgentMapCanvas.tsx<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/AgentMapScene.tsx | 2026-08-20 | yes | yes | yes | unknown | accepted |
| `WorkspaceKey` distingue `worktree:` de `folder:` e `ExecutionHostId` distingue `local`, `ssh:` e `runtime:`; `cwd` sozinho não identifica um Canvas de forma segura | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/folder-workspace-types.ts<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/execution-host.ts | 2026-08-20 | yes | yes | yes | unknown | accepted |
| `worker-start` exige um handle `from`, cerca esse terminal ao Run coordenado e só aceita uma Task pertencente ao mesmo Run; para worktree novo, o Dispatch é persistido no Run home antes da criação do workspace executor | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-start-schema.ts<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-workers.ts | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O placement atual separa `--on` de `--worktree`; remoto rejeita `current` e `new-child`, enquanto `new-top-level` remoto exige nome e repositório explícitos | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/cli/specs/orchestration-worker-specs.ts<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-start-validation.ts | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O catálogo Codex auditado contém Sol, Terra e Luna | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/agent-session-option-catalog-claude-codex.ts | 2026-08-20 | yes | yes | partial | unknown | volatile |
| Orca já possui preview de terminal com snapshot, output stream e input reutilizável | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/AgentTerminalPreview.tsx<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/ipc/terminal-preview-output-stream.ts | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O PR do Orca sobre renderer isolado relata aproximadamente 30 a 60 MB por pane; isto sustenta um único preview completo selecionado, não um renderer por nó | https://github.com/stablyai/orca/pull/10412 | 2026-08-20 | yes | yes | partial | unknown | limited |
| `worker_done` conclui o estado lógico, mas não cria uma intenção de release do terminal | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/orchestration/db/dispatch-context/worker-report-settlement.ts<br>https://github.com/stablyai/orca/issues/13047 | 2026-08-20 | yes | yes | yes | yes | accepted |
| Workers supervisionados já possuem o ledger durável `worker_terminal_resources`, com ownership, estados de release e archive; o tombstone de terminal comum permanece memory-only, e ainda faltam auto-release e release federado | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/orchestration/db/schema/create-core-tables-sql.ts<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-release.ts<br>https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/daemon/terminal-host-tombstones.ts | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O HEAD auditado não usa Windows Job Objects para conter a árvore de cada PTY | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/windows-process-tree-kill.ts<br>https://github.com/stablyai/orca/issues/14998 | 2026-08-20 | yes | yes | yes | yes | accepted |
| Em SSH direto, processos e arquivos ficam no host remoto, mas UI, transporte, Run/Task/Dispatch e o control plane ficam no cliente; no runtime pareado, o peer possui o próprio control plane. Ambos preservam `live`, `unverifiable` e `exited` como estados distintos | https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/docs/reference/ssh-execution-boundary.md | 2026-08-20 | yes | yes | yes | unknown | accepted |
| No my-llm-kit, `events.jsonl` é o journal canônico do Agent Graph e somente o coordenador vigente escreve; o OrcaDriver cria um Run/Tasks externos e mantém o mapeamento local para Orca | https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/SKILL.md<br>https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/drivers/orca.py | 2026-08-20 | yes | yes | yes | unknown | accepted |
| No my-llm-kit, `Isolation: worktree` é parseado, mas o OrcaDriver despacha sempre para o worktree corrente do driver | https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/graph_core.py<br>https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/drivers/orca.py | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O run do my-llm-kit não persiste a identidade exata do worktree selecionado e pode redetectar outro checkout ao retomar | https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/agent_graph.py<br>https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/drivers/orca.py | 2026-08-20 | yes | yes | yes | unknown | accepted |
| O `status --watch` atual do my-llm-kit acumula snapshots antes de retornar, e o journal usa lock apenas dentro do processo | https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/agent_graph.py<br>https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/graph_core.py | 2026-08-20 | yes | yes | yes | unknown | accepted |
| Tasks marcadas como concluídas na spec podem iniciar como pending em um novo run, pois `checked` é parseado mas não aplicado na inicialização | https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/graph_core.py | 2026-08-20 | yes | yes | yes | unknown | accepted |

## Findings

### Recomendação

Construir o Maestro como uma superfície embutida e operacional de um único workspace. No Orca, a identidade canônica deve ser:

```text
MaestroWorkspaceId = (ExecutionHostId, WorkspaceKey)
```

O Canvas não deve repetir tabs, sidebar de worktrees ou status bar. O Orca já fornece esse chrome. Dentro da superfície, basta um resumo compacto do workspace recebido, a toolbar do Canvas, o grafo e um inspector contextual. Esta correção foi aplicada ao mock depois que a composição inicial revelou o problema de “Orca dentro do Orca”.

Um child worktree ou workspace remoto recebe outro `MaestroWorkspaceId` e outro Canvas, mas isto não transfere automaticamente o Run. É necessário separar:

```text
orchestration_home = Run + coordinator lease/generation + canonical journal
execution_workspace = ExecutionHostId + WorkspaceKey + terminal/process owner
```

Quando um worker do Run de origem executa em um child, o Canvas do parent mantém a Task e um nó de Dispatch que aponta para o portal do workspace executor. O Canvas do child mostra o terminal/agent local com uma referência de volta ao `orchestration_home`. Nenhum dos dois importa o grafo inteiro do outro. Transferir a Task ou o Run para o child exigiria uma transação explícita de novo Run/journal; placement sozinho não faz isso.

Um mapa global de frota pode continuar existindo fora do Maestro, mas não deve fundir autoria de notas, posições e terminais de vários workspaces em um único documento editável.

### Fronteira arquitetural

```text
┌──────────────────────────────────────────────────────────────┐
│ Orca tab/browser chrome                                      │
│  └─ Maestro surface: viewport, notes, cards, edges, inspector│
└──────────────────────────────┬───────────────────────────────┘
                               │ snapshot + ordered deltas
┌──────────────────────────────▼───────────────────────────────┐
│ Maestro document store, keyed by host + WorkspaceKey         │
│ visual writer: revision, receipts, positions, notes, edges   │
└──────────────────────────────┬───────────────────────────────┘
                               │ authenticated operational intent
┌──────────────────────────────▼───────────────────────────────┐
│ Agent Graph coordinator, fenced by run + generation          │
│ canonical: contract, readiness, checks, grades, local journal│
└──────────────────────────────┬───────────────────────────────┘
                               │ reserve, call driver, persist receipt
┌──────────────────────────────▼───────────────────────────────┐
│ Orca orchestration                                            │
│ canonical for its Run/Task/Dispatch and worker lifecycle     │
└──────────────────────────────┬───────────────────────────────┘
                               │ supervised process action
┌──────────────────────────────▼───────────────────────────────┐
│ Execution host: terminal, PTY, process tree, resources       │
└──────────────────────────────────────────────────────────────┘
```

O store do Maestro é durável, mas não é a fonte de verdade da execução. Ele guarda autoria visual e semântica do Canvas: posição, tamanho, viewport, Markdown, grupos, arestas explícitas, referências e tombstones. Status de task, worker, terminal, grade, check e cleanup são projeções das duas fontes operacionais, sem fingir que existe uma transação distribuída entre elas.

No my-llm-kit, `events.jsonl` continua canônico para contrato/readiness/check/grade e somente a geração atual do coordenador o escreve. O OrcaDriver reserva a ação local, cria a entidade externa no Orca, persiste o receipt e reconcilia incerteza por retry identity; Orca não escreve o journal local. No Orca, seu banco continua canônico para transporte e lifecycle do worker. O Maestro apenas agrega as projeções.

Mutações puramente visuais passam pelo writer único do Maestro e carregam `maestro_workspace_id`, `expected_revision` e `mutation_id`. A identidade do ator é derivada do transporte autenticado, nunca aceita como string confiável do cliente. Um intent operacional também carrega `run_id`, coordinator lease/generation e capability; UI, coordenador e worker possuem permissões distintas. A resposta é um receipt compacto com a nova revisão e os deltas aceitos.

### Modelo do Canvas

Nós propostos:

- `note`: Markdown editável, armazenado por conteúdo ou por referência a path + hash + revisão.
- `task`: projeção de contrato, dependências, check e grade do Agent Graph.
- `agent`: execução supervisionada, com agent, model, effort, task, dispatch, owner e state.
- `terminal`: terminal não supervisionado, explicitamente diferente de worker.
- `artifact`: arquivo, diff, relatório, check, PR ou evidence receipt.
- `gate`: pergunta, aprovação ou condição bloqueante.
- `portal`: navegação para outro `MaestroWorkspaceId` sem copiar seus nós; não substitui a Task/Dispatch que permanece no `orchestration_home`.
- `group`: organização visual sem semântica de execução por padrão.

Arestas precisam ser tipadas. `context`, `depends_on`, `dispatch`, `spawned`, `produced`, `message` e `portal` não são equivalentes. Somente `depends_on` controla readiness. Uma seta visual genérica não pode virar dependência por inferência.

Open-Maestri oferece a dinâmica correta de pan, zoom, mover nós, menu no cursor, notas e conexão automática, mas seus links são principalmente comunicação/contexto. A versão Orca precisa preservar semântica operacional, receipts e isolamento. O comportamento pode ser reimplementado; o source GPL não deve ser copiado para o Orca MIT sem resolução de licença.

### Contexto sem encher a sessão

Uma nota ligada a uma task entra no próximo capsule como referência compacta, não como transcrição do Canvas. O capsule resolve apenas:

- a task atual e seus paths autorizados;
- as notas conectadas, por path/hash/revisão;
- um tail limitado do terminal quando necessário;
- evidence refs e decisões diretamente ligadas;
- um orçamento explícito de bytes/tokens e detecção de ciclo.

Ligar uma nota a um attempt já em execução não injeta texto silenciosamente. Deve existir `context_send_requested` e um receipt do terminal/worker. Assim, mover ou conectar cards não reenvia o histórico inteiro ao coordenador.

O CLI do Agent Graph também precisa deixar de retornar o state completo após toda mutação. O default deve ser `{receipt, revision, changed_refs, projection_path}`; `--include-state` fica reservado a diagnóstico. `status --watch` deve produzir NDJSON ou subscription incremental com memória limitada.

### Delegação de agente e modelo

O Canvas não inicia `codex`, `claude`, OpenCode ou Gemini diretamente. Ele envia um intent ao coordenador vigente:

1. UI ou worker envia `delegation_requested` com `MaestroWorkspaceId`, revisão, parent, task/brief, context refs, `ExecutionProfile`, placement, `run_id` e coordinator generation. O ator vem da sessão/pane autenticada.
2. O coordenador vigente valida identidade, capability, permissões, dependências, paths, isolamento e orçamento de recursos. Um worker só pode solicitar; ele não recebe autoridade de writer.
3. O coordenador reserva o intent no Agent Graph. Se for uma task nova, ele materializa o contrato local antes de qualquer provider mutation.
4. O OrcaDriver cria ou seleciona a Task/Dispatch espelhada no Run Orca e chama `orchestration worker-start` usando o `from` do coordenador vinculado àquele Run.
5. Placement é uma união tipada: `local-current`, `local-existing(selector)`, `local-new-child(name, ...)`, `local-new-top-level(name, ...)`, `remote-existing(environment, selector)` ou `remote-new-top-level(environment, repo, name, ...)`. Remoto não aceita `current` nem `new-child` no contrato auditado.
6. Somente após receber e persistir o worker/terminal receipt, o Maestro projeta o nó local ou o Dispatch stub + portal e cria `spawned` e `context`.
7. Falha, timeout ou outcome desconhecido produz receipt recuperável; nunca um agente visual “fantasma”.

Workers do my-llm-kit continuam proibidos de escrever diretamente no journal ou coordenar outros agentes. Um agente pode pedir outro agente, mas o pedido atravessa o coordenador cercado por generation. Isso preserva o modelo de autoridade e permite mostrar a conexão automática desejada.

No Orca auditado, Sol, Terra e Luna já existem no catálogo Codex e o `worker-start` já carrega model e effort. Essa disponibilidade é volátil e deve ser lida do catálogo/capability do host em runtime, não hardcoded no Canvas. OpenCode e Gemini só aparecem como opções executáveis se a instalação e o adapter forem detectados.

### Terminal visível sem multiplicar memória

Cards recebem apenas um tail de output com tamanho e frequência limitados. O terminal completo, com input, replay e resize, é montado apenas no nó selecionado ou em um pequeno orçamento explícito de previews. Nós fora do viewport são virtualizados/cullados.

Isto aproveita o preview já existente no Orca e evita repetir o custo de um renderer isolado para cada card. O relato de aproximadamente 30 a 60 MB por pane está no [PR #10412, consultado em 2026-08-20](https://github.com/stablyai/orca/pull/10412); é uma medição do autor do PR, não um benchmark reproduzido nesta pesquisa.

### Lifecycle, processos e memória

O Maestro só será seguro se lifecycle for parte do mesmo programa, sem criar outro ledger concorrente:

1. **Estender o ledger que já existe para workers.** `worker_terminal_resources` já persiste ownership, release state, process incarnation, host scope e archive. Auto-release e replay devem reutilizar essa tabela e o fluxo de `workerRelease`, não criar um segundo ledger Maestro.
2. **Durabilizar o fechamento comum.** Para terminais fora de orchestration, o tombstone do daemon continua apenas em memória. Se o Canvas puder fechá-los, a intenção precisa ser persistida antes da remoção visual com terminal/PTY incarnation, workspace, owner, reason e policy.
3. **Archive before release.** O fluxo de worker já preserva archive; o Canvas projeta esse artefato antes de remover o processo e mantém o card histórico.
4. **Auto-release conservador.** Ao aceitar `worker_done`, uma nova transição atômica no ledger existente pode solicitar release somente para worker `owned` e `succeeded|failed`. Excluir `retained`, `user_owned`, `external`, `transferred` e qualquer identidade incerta. Não reutilizar uma operação explícita que remova a retenção do usuário.
5. **Árvore de processos comprovada.** POSIX usa process group/descendant verification e proteção contra PID reuse. Windows precisa de Job Object por PTY, mantendo graceful shutdown antes de force kill.
6. **SSH direto.** O control plane e o ledger de orchestration ficam no cliente; PTY e filesystem ficam remotos. Stop/release envia comando idempotente ao relay e aguarda acknowledgement. Sem cliente ou ack, o estado é `unverifiable`, nunca `exited`.
7. **Runtime pareado.** O peer possui seu próprio control plane e ledger. Release federado precisa de opcode capability-gated, replay e receipt do peer; hoje `worker-release` retorna `federation_unsupported` e não executa ação de processo.
8. **Daemons por geração.** Inventariar todas as gerações, owners, endpoints, idade e sessões. Retirar apenas uma geração comprovadamente vazia, sem pendência e sem endpoint canônico.
9. **Worktree GC em lote.** Um scan autoritativo, uma prova, uma mutação persistida e uma notificação, tanto local quanto SSH. Worktree sujo bloqueia remoção para revisão.
10. **Snapshot agregado de recursos.** Um collector por host associa PTY/process incarnation a worker/dispatch/task e publica CPU, RSS, uptime, ownership e release state. O Canvas não faz poll por nó.

As ações do inspector devem chamar `worker-stop`, `worker-release`, `worker-retain` ou fechamento comum conforme ownership. O botão genérico “kill PID” não é lifecycle de worker.

Issues do Orca que corroboram a necessidade, todas abertas quando consultadas em 2026-08-20:

| Área | Evidência primária | Implicação para Maestro |
|---|---|---|
| Memória do daemon | [#12728](https://github.com/stablyai/orca/issues/12728) | Medir daemon/generation e não apenas o terminal visível. |
| Daemon e PTY stale | [#11342](https://github.com/stablyai/orca/issues/11342) | Reconciliation precisa atravessar gerações. |
| Kill fire-and-forget | [#11904](https://github.com/stablyai/orca/issues/11904) | Persistir close intent antes de remover UI. |
| Worker settled retido | [#13047](https://github.com/stablyai/orca/issues/13047) | Criar auto-release policy conservadora. |
| Gerações antigas | [#9138](https://github.com/stablyai/orca/issues/9138) | Inventário e retirement com prova. |
| CPU e worktrees stale | [#15412](https://github.com/stablyai/orca/issues/15412) | Forget autoritativo e batch. |
| Windows process tree | [#14998](https://github.com/stablyai/orca/issues/14998) | Kernel containment por PTY. |
| Saúde via CLI | [#10609](https://github.com/stablyai/orca/issues/10609) | Expor snapshot headless e ownership. |

PRs relevantes, também abertos quando consultados em 2026-08-20:

| PR | O que aproveitar | O que não resolve sozinho |
|---|---|---|
| [#7806](https://github.com/stablyai/orca/pull/7806) | Status/stop-all como escape hatch | Não substitui ledger nem ownership por worker. |
| [#10412](https://github.com/stablyai/orca/pull/10412) | Isolamento e custo do renderer | Não define virtualização do Canvas. |
| [#12740](https://github.com/stablyai/orca/pull/12740) | Reap de worktrees/daemons | Draft; não entrega inventário completo no HEAD auditado. |
| [#14726](https://github.com/stablyai/orca/pull/14726) | Fallback de close por PTY | Ainda há lacuna headless. |
| [#8926](https://github.com/stablyai/orca/pull/8926) | Handles estáveis e grids de terminal | Grid físico não é Canvas semântico. |
| [#4385](https://github.com/stablyai/orca/pull/4385) | Notas ligadas a terminal | Não cobre notas arbitrárias e contexto tipado. |
| [#10764](https://github.com/stablyai/orca/pull/10764) | Memória durável de projeto | O Canvas deve referenciar, não duplicar, essa memória. |
| [#15501](https://github.com/stablyai/orca/pull/15501) | Folder instances no mesmo checkout | Reforça `WorkspaceKey`, não `cwd`. |
| [#14972](https://github.com/stablyai/orca/pull/14972) | Componentes de CPU/RSS/uptime | Falta identidade de orchestration e lifecycle. |

### Seams no Orca

| Camada | Arquivos de entrada | Mudança recomendada |
|---|---|---|
| Tab/sessão | [`tab-types.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/tab-types.ts), [`workspace-session-schema.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/workspace-session-schema.ts) | Novo content type Maestro, sem duplicar o chrome dentro da superfície. |
| Canvas | [`AgentMapCanvas.tsx`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/AgentMapCanvas.tsx), [`agent-map-layout.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/agent-map-layout.ts) | Separar auto-layout de posições manuais duráveis; adicionar notes, explicit edges e portals. |
| Terminal | [`AgentTerminalPreview.tsx`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/renderer/src/components/dashboard-popout/AgentTerminalPreview.tsx) | Reusar somente para seleção/foco; cards ficam com tails. |
| Identidade | [`workspace-scope.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/workspace-scope.ts), [`execution-host.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/execution-host.ts) | Chave composta host + WorkspaceKey em todo snapshot/mutation. |
| Delegação | [`orchestration-worker-specs.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/cli/specs/orchestration-worker-specs.ts), [`orchestration-workers.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-workers.ts) | Projetar o receipt do worker existente; não criar launcher paralelo. |
| Persistência | [`orchestration-db.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/orchestration/db/orchestration-db.ts) | Store runtime-owned com WAL, revisão e deltas; banco separado ou extensão isolada. Nunca consultar SQLite por frame. |
| Cleanup | [`terminal-host-tombstones.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/daemon/terminal-host-tombstones.ts), [`orchestration-worker-release.ts`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-release.ts) | Estender o ledger existente de worker para auto-release/federação e durabilizar separadamente a intenção de close de terminal comum. |
| Skills | [`orca-cli.md`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/skill-guides/orca-cli.md), [`generate-bundled-skill-guides.mjs`](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/config/scripts/generate-bundled-skill-guides.mjs) | Editar guides canônicos e regenerar bundle; nunca editar o arquivo gerado diretamente. |

Orca possui usuários e contratos CLI/RPC versionados. Portanto, novos opcodes devem ser aditivos e capability-gated; ausência do campo não pode significar `null`. Esta pesquisa não recomenda remover compatibilidade existente.

### CLI proposto

O CLI Maestro manipula o documento/projeção. Lifecycle de worker continua no namespace orchestration:

```text
orca maestro show --execution-host <local|ssh:id|runtime:id> --workspace <worktree:id|folder:id> --json
orca maestro watch --execution-host <id> --workspace <key> --since-revision <rev> --ndjson
orca maestro apply --execution-host <id> --workspace <key> --expected-revision <rev> --mutation-id <uuid> --ops <json>
orca maestro node create|update|delete ...
orca maestro edge create|delete ...
orca maestro open|focus ...

orca maestro intent delegate --run <id> --coordinator-generation <n> --parent <attempt> --profile <json> --placement <json>

orca orchestration worker-start --task <id> --run <id> --from <coordinator-handle> --worktree <current|selector|new-child|new-top-level> --agent <id> --model <id> --effort <id>
orca orchestration worker-start --task <id> --run <id> --from <coordinator-handle> --on <environment> --worktree new-top-level --name <name> --repo <selector> --agent <id> --model <id> --effort <id>
orca orchestration worker-stop|worker-retain|worker-release ...
```

`--execution-host` e `--workspace` formam o mesmo endereço em snapshot, watch, mutation e focus, inclusive para folder workspaces. A identidade do ator não vem de uma flag: o runtime a deriva do terminal/pane ou sessão autenticada. `maestro intent delegate` entrega o pedido ao coordenador cercado; somente ele chama orchestration e devolve o receipt local mais o receipt externo. Não deve surgir um segundo lifecycle de worker sob `maestro worker spawn`.

### Mudanças necessárias no my-llm-kit

| Gap atual | Risco | Correção antes de escrever no Canvas |
|---|---|---|
| `Isolation: worktree` é parse-only | Task pode rodar no checkout errado | Criar/selecionar worktree por attempt e persistir host, WorkspaceKey e canonical path no run. |
| Resume redetecta o checkout corrente | Run copiado pode religar no workspace errado | Falhar fechado se a identidade pinada não estiver disponível. |
| Driver fixa `codex`; dispatch não tem profile | Canvas promete modelo que runtime ignora | Persistir `ExecutionProfile` resolvido e receipt do provider. |
| Não há note/context/task-added/delegation events | UI vira estado paralelo | Separar mutações do Canvas de intents operacionais; somente a geração atual do coordenador escreve o journal local. |
| Mutações devolvem state completo | Coordenador reincorpora reports e contexto | Resposta compacta + refs; state completo sob flag. |
| `status --watch` acumula snapshots | Memória cresce sem stream útil | NDJSON/subscription incremental com cursor e cap. |
| `threading.RLock` protege apenas um processo | UI e CLI podem escrever a mesma geração | Writer único ou lock interprocess com sequence CAS. |
| `run-check` não limita tempo/output/process tree | Check pode ficar órfão e consumir memória | Timeout, cap de output, process group e receipt de término. |
| `checked` não inicializa status | Spec concluída reaparece pending | Materializar estado inicial coerente ou rejeitar ambiguidade. |
| Uma mudança frontend criada depois do bootstrap não pode ganhar task/Visual contract na geração ativa | `complete pass` bloqueia mesmo quando o Canvas possui screenshots revisadas fora do contrato | Adicionar amendment event versionado para task/Visual-Scope, ou exigir que o mock visual seja materializado antes de iniciar o run. |
| Resource guard não conhece run/worktree/attempt | Prune pode matar sem reconciliar journal | Owner estruturado e evento observável; guard continua opcional. |

### Skills e harness

- `agent-graph`: adicionar `AgentGraphView`, `orchestration_home` versus `execution_workspace`, identidade pinada, execution profiles, context refs, delegation requests, fencing e process-tree receipts.
- `impl`: sempre abrir coordenador fresh, inclusive quando chamado de uma sessão cheia; mostrar esse coordenador como nó; usar capsules e respostas compactas. A sessão chamadora fica como observadora/controladora, não herda o contexto inteiro.
- `research`: collectors continuam read-only. Conectar uma fonte a um agente cria lead/context ref; o pesquisador principal ainda abre e adjudica a fonte.
- `spec`: o Canvas pode editar um draft de graph, mas `$spec` materializa e valida o OpenSpec. Um agente em `$impl` não amplia silenciosamente a spec aprovada.
- `orca-cli`: ensinar full workspace IDs, revisions, receipts, watch incremental, spawn supervisionado e lifecycle seguro.
- `resource discipline`: admission antes de waves pesadas e cleanup ao final. `agent-resource-guard` permanece melhoria opcional Linux, nunca requisito do fluxo normal.

Sem Orca, o my-llm-kit usa o mesmo `CanvasDocument` e `AgentGraphView` versionados em um adapter local, servidos como página embutível/standalone. O adapter pode operar o HostDriver e abrir o Canvas no browser, mas não simula APIs remotas ou ownership que não consegue provar. Ele também não desenha um shell falso de Orca ao redor do Canvas.

### Entrega em camadas

Isto é uma sequência de pesquisa, não uma spec aprovada:

1. Endurecer Agent Graph: identidade, writer único, deltas, profiles, cancelamento e checks limitados.
2. Adicionar tab/surface Maestro read-only por `(ExecutionHostId, WorkspaceKey)`, mostrando Dispatch stubs do Run home para execuções externas.
3. Persistir layout, notes e typed edges com revisão e receipts.
4. Delegar no worktree corrente através de `worker-start` e projetar apenas após receipt.
5. Adicionar child/remote portals e `delegation_requested` cercado por ator, Run e generation.
6. Estender o ledger existente de workers, entregar auto-release conservador, release federado, Job Objects, reconciliation e resource snapshot; durabilizar o close comum em um corte separado.
7. Atualizar CLI, guides e skills; regenerar os bundles.
8. Entregar o adapter portátil do my-llm-kit e validar sem Orca.

Cada camada precisa funcionar end to end antes da próxima. O primeiro PR no Orca não deve misturar Canvas editável, novo banco, delegação, GC de daemons e Windows containment em um único diff.

### O que o mock prova

O [mock funcional](./mocks/orca-agent-graph/index.html) foi executado dentro do browser do Orca e validado em três viewports. Ele demonstra:

- Canvas embutido sem duplicar o chrome do Orca;
- pan, zoom, drag e persistência local de posição;
- Markdown note, criação no cursor e typed links;
- seleção de Codex/Claude, Luna/Terra/Sol, effort e placement;
- criação automática de `spawned` e `context` após uma delegação simulada;
- portal para child/remote workspace sem misturar documentos; a implementação real ainda deverá manter o Dispatch stub no Run home;
- terminal focado, input simulado, inspector de recursos e release com arquivo preservado.

As evidências e observações estão no [manifest visual](../.visual-evidence/orca-maestro-canvas-v2/manifest.md). O mock não prova IPC/RPC, concorrência, SQLite, execução real de modelo, árvore de processos, SSH, Job Objects ou cleanup após crash. Todos os valores de runtime são marcados como simulados.

## Disagreements

- O finding anterior tratava Fleet/Task Graph como a principal resposta visual. A conclusão foi refinada: Fleet continua sendo visão global; Maestro é o Canvas operacional de um único worktree. Não é seguro fundir os dois escopos.
- Open-Maestri privilegia conveniência ao usar o workspace ativo e managers globais em recruit/connect/dismiss. Orca exige identidade exata do host e do `WorkspaceKey`; o comportamento visual é referência, o boundary técnico não é.
- A hipótese inicial de que mover a execução para um child também moveria Task/Run foi rejeitada pelo contrato real de `worker-start`: o Run permanece no orchestration home, com Dispatch no parent, enquanto terminal e processo pertencem ao execution workspace.
- A hipótese de um único “runtime Maestro” também foi rejeitada. Agent Graph e Orca mantêm autoridades distintas e não possuem transação distribuída: o coordenador reserva intent, chama o driver, persiste receipt e reconcilia; o Canvas apenas agrega projeções.
- Criar um novo ledger Maestro para todo cleanup duplicaria o ledger durável que Orca já mantém para workers. A recomendação passou a estender `worker_terminal_resources` e tratar separadamente apenas o fechamento de terminais comuns.
- O Orca atual deixa release explícito ao coordenador. O issue #13047 pede evitar terminais settled esquecidos. A recomendação concilia ambos com auto-release apenas para ownership e estados comprovados, preservando `retain` e owners externos.
- Um collector limitado do run de pesquisa não encontrou todos os issues/PRs relevantes. A auditoria principal do repositório e GitHub encontrou evidência adicional; não houve conflito factual entre fontes, apenas cobertura incompleta do collector.

## Open questions

- O store Maestro deve ser um `maestro.db` separado ou uma extensão isolada do banco de orchestration? A escolha depende de testes de lock, migração e frequência de snapshot.
- Notes devem persistir inline, como arquivos Markdown, ou nos dois formatos? A recomendação é suportar ambos com hash/revisão, mas a spec precisa escolher o default.
- A política default após `worker_done` será auto-release, grace period ou retain até o coordenador decidir? Precisa de decisão explícita antes da implementação.
- A primeira entrega suporta edição multiwindow em tempo real ou apenas writer único com optimistic concurrency e refresh? O contrato de revisão deve existir de qualquer forma.
- Windows Job Objects entra no mesmo programa Maestro ou em PR independente de lifecycle? A dependência é real, mas o diff provavelmente deve ser separado.
- No Canvas executor, a primeira versão projeta apenas terminal/agente + referência ao orchestration home ou também um espelho read-only da Task? Em ambos os casos, o Dispatch canônico continua no Canvas parent.
- Como representar uma operação cujo Agent Graph registrou a reserva, mas cujo receipt Orca se perdeu após timeout? A spec precisa definir retry identity, reconciliation e estados de incerteza sem criar Dispatch duplicado.

## Council review

- Status: not run
- Reason: O usuário pediu a stack de research, não `--council`; as conclusões foram sustentadas por código primário em commits pinados, issues/PRs oficiais, execução do mock e dois audits independentes de Orca e my-llm-kit.
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://github.com/zlh-428/open-maestri/tree/6db452e5d1663bfdd4666f757987b0a1affe073d, accessed 2026-08-20.
- https://github.com/zlh-428/open-maestri/blob/6db452e5d1663bfdd4666f757987b0a1affe073d/LICENSE, accessed 2026-08-20.
- https://github.com/stablyai/orca/tree/4e058d4a52ea4653a5cf86fac271c8010334361e, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/LICENSE, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/docs/STYLEGUIDE.md, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/docs/reference/ssh-execution-boundary.md, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/docs/reference/remote-wire-compatibility.md, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-start-schema.ts, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-workers.ts, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-start-validation.ts, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/orchestration/db/schema/create-core-tables-sql.ts, accessed 2026-08-20.
- https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/main/runtime/rpc/methods/orchestration-worker-release.ts, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/12728, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/11342, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/11904, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/13047, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/9138, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/15412, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/14998, accessed 2026-08-20.
- https://github.com/stablyai/orca/issues/10609, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/7806, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/10412, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/12740, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/14726, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/8926, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/4385, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/10764, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/15501, accessed 2026-08-20.
- https://github.com/stablyai/orca/pull/14972, accessed 2026-08-20.
- https://github.com/badmuriss/my-llm-kit/tree/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph, accessed 2026-08-20.
- https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/SKILL.md, accessed 2026-08-20.
- https://github.com/badmuriss/my-llm-kit/blob/f98903664c1836ce7959d3b1bbfbbaa2b007b868/skills/agent-graph/scripts/drivers/orca.py, accessed 2026-08-20.

## Trial by fire

- Primary-source claims: Interaction behavior, licensing, Orca UI/runtime seams, CLI contracts, lifecycle, worktree identity, remote boundary and my-llm-kit gaps were checked against source at pinned commits. Issue and PR status was checked through GitHub on the access date.
- Secondary-only claims: None used for the recommendation. The user's report of leaks was treated as a lead and corroborated with Orca source plus official issues.
- Volatile claims: Issue/PR open state, available model IDs, CLI flags and runtime capabilities can change after 2026-08-20. Recheck them at spec/implementation time. The per-pane memory figure is limited to the measurement reported by PR #10412 and was not reproduced.
- Adversarial checks: Rejeitados um Canvas global cross-worktree, identidade por `cwd`, Canvas-as-journal, spawn direto worker-to-worker, renderer por card, fire-and-forget kill, cópia de source GPL no Orca MIT, portal como substituto do Dispatch parent, transferência implícita de Run para child e um segundo ledger de cleanup concorrente.
- Runtime trial: The mock ran inside Orca; note creation/edit, typed connection, node drag, delegation with model/effort, automatic simulated edges, terminal input, pan/zoom and release/archive flow were exercised. Visual review covered overview, context menu, delegation, link mode, terminal and cleanup at the three declared desktop profiles.
