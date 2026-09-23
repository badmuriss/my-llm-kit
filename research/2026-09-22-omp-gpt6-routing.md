# OMP: roteamento GPT-6, migração local e retomada

Registro de 2026-09-22, atualizado na retomada iniciada às 18h53, horário -03. Ambiente: Linux, OMP 18.2.9, terminal Orca. Este documento registra o estado observado, não declara concluídas as autenticações e verificações ainda pendentes.

Auditoria posterior: [repositório e harness](2026-09-22-omp-harness-audit.md). Ela confirma que `tiny:minimal` normaliza para low e que o sufixo medium de `@slow` prevalece sobre o frontmatter high. As incertezas anteriores abaixo ficam preservadas como histórico; não houve ensaio de contexto longo nem recibo de faturamento. Webshare não está configurado. A referência ScrapingDog em `~/AGENTS.md` foi corrigida para `endpoint-index.md`.

## Começar por aqui

- O harness principal é o **OMP**. Os modelos continuam pelo provider **`openai-codex`**, usando a assinatura ChatGPT/Codex. Trocar o harness não significa desativar seus modelos.
- `huggingface`, `openrouter` e `opencode-go` estão em `disabledProviders`. A última listagem executada mostrou somente `openai-codex`, com sete modelos de conversa.
- Todos os seletores de papel e fallback configurados apontam para `openai-codex`. Não há fallback de imagem para provider pago por uso.
- O problema anterior de sessões eliminadas pelo `agent-resource-guard` foi corrigido, testado e instalado. A saída posterior, às 18h40, foi registrada como desconexão do terminal e `SIGHUP`, não como nova poda do guard.
- O padrão **atual** é `openai-codex/gpt-6-astra:max`. A etapa anterior havia configurado Sol/medium; o arquivo mudou antes desta retomada e a mudança foi preservada. Não substituir o padrão atual só porque a recomendação de custo abaixo prefere Sol/medium.
- Seis MCPs conectaram; outros seis retornam HTTP 401 e exigem autenticação. Nenhuma conta foi cancelada, nenhuma credencial foi apagada e nenhum CLI foi desinstalado.
- No encerramento da primeira etapa ainda não havia commit nem push. A publicação posterior foi autorizada pelo usuário e é tratada na auditoria vinculada acima. Mudanças anteriores do usuário no kit devem ser preservadas.

## Protocol

- Question: Como usar OMP como harness principal com Astra, Sol e Luna via assinatura ChatGPT/Codex, esforço por complexidade, visão, imagem e integrações locais, sem depender de OpenRouter?
- Decision criterion: Seletores e fallbacks permanecem em openai-codex; ferramentas e agentes funcionam no runtime; sessões vivas não são eliminadas pelo guard; custos são comparados na unidade correta e pendências ficam explícitas.
- Falsifier: Um provider pago por uso aparecer no roteamento efetivo; o guard marcar OMP vivo como órfão; um teste alegadamente específico usar fallback não identificado; ou a documentação afirmar suporte que não foi exercitado.
- Risk: material
- Credits used: 0

O campo numérico acima contém apenas cobranças de pesquisa efetivamente medidas. **Não representa consumo total zero.** Houve duas buscas ScrapingDog sem medição de saldo antes/depois e chamadas OpenRouter antes da correção de escopo. Os totais não foram medidos. Nenhuma nova consulta paga foi feita para redigir esta retomada.

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Consultar modelos, raciocínio e preços oficiais | OpenAI | Leitura direta das URLs abaixo | Páginas oficiais lidas durante a sessão | 0 | URL conhecida; sem necessidade de proxy |
| Encontrar relatos comunitários | Busca do host | Busca web | Falha de quota e desafios anti-bot em caminhos alternativos | 0 | Não forneceu evidência utilizável |
| Localizar discussões recentes | ScrapingDog | Google SERP, duas consultas | HTTP 200; URLs de discussões encontradas; consumo não medido | 0 | Substituiu a busca indisponível; zero significa ausência de medição |
| Ler comparações comunitárias | Reddit | Leitura direta de dois tópicos | Shell/SVG anti-bot, sem conteúdo verificável | 0 | Tópicos não usados para sustentar recomendação |
| Testar modelos e ferramentas antes da correção do usuário | OpenRouter | Probes CLI e geração da imagem da maçã | Chamadas realizadas; custo não medido; rota removida depois | 0 | Foi um desvio de escopo, não uma necessidade técnica |
| Verificar o caminho autorizado após a correção | ChatGPT/Codex | OMP com seletores openai-codex | Respostas de conversa, visão, imagem e subagente observadas | 0 | Consumo da assinatura não medido; recibos de fallback não inspecionados |

## Claim ledger

As páginas oficiais abaixo são fontes primárias, mas não independentes entre si. Não houve snapshot web durável; as leituras ficaram no histórico da sessão. As evidências locais são preservadas separadamente.

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| Sol e Luna foram anunciados para Work/Codex com disponibilização gradual | https://openai.com/index/introducing-gpt-6-sol-and-luna/ | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | volatile |
| Sol aceita texto e imagem e oferece níveis de esforço para tarefas de código e agentes | https://developers.openai.com/api/docs/models/gpt-6-sol | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | accepted |
| Luna atende tarefas focadas e de alto volume com entrada de texto e imagem | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | accepted |
| Astra é posicionado para os problemas mais difíceis; seu esforço começa em low | https://developers.openai.com/api/docs/models/gpt-6-astra | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | accepted |
| Esforço menor favorece velocidade e economia; esforço maior exige justificativa pela tarefa | https://developers.openai.com/api/docs/guides/reasoning | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | accepted |
| Créditos Codex distinguem Astra, Sol e Luna; não equivalem diretamente a dólares da API | https://learn.chatgpt.com/docs/pricing | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | volatile |
| Modelos 5.6 permaneciam disponíveis durante a transição documentada | https://learn.chatgpt.com/docs/models | 2026-09-22 | Histórico da sessão; sem snapshot web | yes | yes | yes | no | volatile |

## Findings

### Recomendação operacional, não benchmark local

[INFERÊNCIA] Luna/low ou medium é a primeira opção para trabalho mecânico e bem delimitado; Sol/medium para implementação cotidiana; Sol/high para planejamento de múltiplos arquivos; Astra/medium para depuração difícil, arquitetura e decisões caras de errar. High, xhigh e max não devem subir automaticamente após uma falha. Base: posicionamento dos modelos e guia de raciocínio, não comparação controlada neste repositório. Fontes: https://developers.openai.com/api/docs/guides/reasoning e https://learn.chatgpt.com/docs/models, acessado 2026-09-22.

Sol/medium foi escolhido para o papel de visão porque aceita imagens e evita usar Astra em toda inspeção. Isso não demonstra superioridade visual sobre Luna ou Astra. A verificação realizada foi reconhecimento de um objeto, não uma avaliação de qualidade de revisão de UI. Fonte de capacidade: https://developers.openai.com/api/docs/models/gpt-6-sol, acessado 2026-09-22.

Geração de imagem usa a ferramenta `generate_image` do OMP com o papel `image`; não deve ser confundida com a entrada visual dos modelos de conversa. A documentação Codex diz que geração compartilha a franquia da assinatura; não se inferiu custo fixo por imagem. Fonte: https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22.

### Unidade correta para comparar custo

Créditos Codex por milhão de tokens, na consulta de 2026-09-22:

| Modelo | Entrada | Entrada em cache | Saída | Fonte |
|---|---:|---:|---:|---|
| Astra | 250 | 25 | 1250 | https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22 |
| Sol | 50 | 5 | 250 | https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22 |
| Luna | 2,5 | 0,25 | 12,5 | https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22 |

As taxas acima tornam Astra cinco vezes Sol e cem vezes Luna por token nas categorias listadas; isso não mede o custo de concluir uma tarefa nem determina quantas mensagens cabem na franquia. Fonte: https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22.

Os preços de API registrados nos metadados dos modelos são referências do catálogo, não ativação de cobrança por API. O endpoint configurado continua ChatGPT OAuth. Preço API, créditos Codex e percentuais de franquia não são unidades intercambiáveis. Fontes: https://developers.openai.com/api/docs/models/gpt-6-sol, https://developers.openai.com/api/docs/models/gpt-6-luna e https://learn.chatgpt.com/docs/pricing, acessado 2026-09-22.

## Estado local efetivo

### Configuração principal

Fonte de verdade: `~/.omp/agent/config.yml`, relido nesta retomada. Configurações de aparência existentes foram preservadas.

| Papel | Seletor atual |
|---|---|
| default | `openai-codex/gpt-6-astra:max` |
| smol | `openai-codex/gpt-6-luna:medium` |
| slow | `openai-codex/gpt-6-astra:medium` |
| plan | `openai-codex/gpt-6-sol:high` |
| vision | `openai-codex/gpt-6-sol:medium` |
| tiny | `openai-codex/gpt-6-luna:minimal` |
| task | `openai-codex/gpt-6-sol:medium` |
| commit | `openai-codex/gpt-6-luna:low` |
| advisor | `openai-codex/gpt-6-astra:low` |
| image | `openai-codex/gpt-image-1` |

Fallbacks em ordem, todos com prefixo `openai-codex/`:

| Papel | Cadeia |
|---|---|
| default | `gpt-6-astra:medium`, `gpt-5.6-sol:medium` |
| slow | `gpt-6-sol:high`, `gpt-5.6-sol:high` |
| plan | `gpt-6-astra:medium`, `gpt-5.6-sol:high` |
| smol | `gpt-5.6-luna:medium` |
| tiny | `gpt-5.6-luna:low` |
| commit | `gpt-5.6-luna:low` |
| task | `gpt-6-luna:medium`, `gpt-5.6-sol:medium` |
| vision | `gpt-6-astra:low`, `gpt-6-luna:medium` |
| advisor | `gpt-6-sol:medium` |
| image | vazia |

```yaml
disabledProviders:
  - huggingface
  - opencode-go
  - openrouter
generate_image:
  enabled: true
```

`disabledProviders` foi verificado na seleção/listagem de modelos. Não significa cancelamento de assinatura nem remoção de credenciais. O log de inicialização ainda consultou uso de uma credencial `opencode-go`; não se comprovou bloqueio de toda comunicação de fundo com providers desativados.

### Catálogo complementar e limites não certificados

`~/.omp/agent/models.yml` adiciona Sol 6 e Luna 6 ao provider existente:

- `baseUrl: https://chatgpt.com/backend-api`
- `api: openai-codex-responses`
- `auth: oauth`
- entrada `[text, image]`; `reasoning: true`
- `contextWindow: 1050000`; `maxTokens: 128000`
- esforços `[low, medium, high, xhigh, max]`; padrão medium
- metadados de custo de Sol: entrada 2, saída 10, cacheRead 0.2, cacheWrite 2.5; Luna: 0.1, 0.5, 0.01, 0.125, respectivamente, em valores de catálogo API.

Motivo: o catálogo OMP 18.2.9, mesmo após refresh, tinha Astra 6, mas ainda usava Sol/Luna 5.6. O cache local Codex posteriormente listou os três modelos GPT-6.

**Limites:** a janela complementar foi tomada da documentação API. O cache Codex local indicava contexto padrão 272000 e máximo 872000. Não foi validado que o endpoint da assinatura aceite a janela de 1050000 configurada. O log de Astra da sessão anterior usou 272000 para manutenção de contexto. Não usar este registro como prova de contexto longo funcional.

`tiny` permanece configurado com `minimal`, que não aparece na lista de esforços dos modelos complementares. Uma resposta bem-sucedida não prova que esse esforço foi transmitido sem normalização. O esforço efetivo precisa de recibo do runtime se isso afetar uma decisão.

### Agentes

- `~/.omp/agent/agents/deep-reasoner.md`: modelo `@slow`, mas frontmatter `thinking-level: high`. Não se verificou a precedência entre isso e `@slow:medium`; não afirmar esforço efetivo medium.
- `~/.omp/agent/agents/fast-worker.md`: modelo `@smol`, `thinking-level: medium`.
- Descoberta real listou ambos e os agentes bundled `scout`, `reviewer`, `security-reviewer`, `task`, `sonic`.
- Dispatch real de `fast-worker` retornou `pong`. Não foi inspecionado o recibo do modelo filho; isso comprova execução, não o modelo exato faturado.
- Não foram adicionados overrides dos agentes bundled. Os arquivos originais em `my-llm-kit/agents/` não foram convertidos; as cópias de runtime são específicas do OMP.

## Sessões encerradas: duas ocorrências diferentes

### Guard eliminava OMP vivo: corrigido

O timer `~/.config/systemd/user/agent-resource-guard.timer` executa o serviço de poda. O serviço chama `~/.local/bin/agent-resource-guard prune --quiet`.

OMP rodava como `bun .../.bun/bin/omp`. O guard reconhecia `bun` como workload gerenciado, mas sua lista `AGENT_EXECUTABLES` não continha `omp`. Por isso podia marcar a própria sessão como órfã após 300 segundos e enviar SIGTERM, seguido de SIGKILL se necessário.

Evidência anterior à correção:

- Journal registrou `pruned 1 stale agent-owned process(es)` às 18h11min08s e 18h17min44s de 2026-09-22.
- A última atividade dos logs `omp.2026-09-22.587305.log` e `omp.2026-09-22.606777.log` coincidiu com esses horários.
- Simulação com limiar zero marcou o OMP vivo PID 636150 como `agent=False`, `managed=True` e candidato a poda.

Correção e instalação:

1. Incluído `omp` em `scripts/agent_resource_guard.py::AGENT_EXECUTABLES`.
2. Adicionado `scripts/tests/test_agent_resource_guard.py`, com quatro regressões: binário direto, execução via Bun, workload de sessão OMP viva e Bun órfão realmente antigo.
3. Instalado o script corrigido em `~/.local/bin/agent-resource-guard`.
4. Backup anterior: `~/.local/bin/agent-resource-guard.bak-20260922-182505`.
5. Simulação do instalado reconheceu o agente e retornou zero candidatos, inclusive com limiar zero.

Fonte e instalado tiveram MD5 `f46f7b386226bb8564bf1969ecbd6605`. Nesta retomada, `cmp` confirmou novamente que são idênticos. O timer continua ativo e habilitado; não foi desativado para esconder a falha. Consulta do journal desde 18h30 não encontrou mensagens `pruned`, `Failed` ou `Killing` até a checagem desta retomada.

### Saída às 18h40: terminal desconectado

O log `~/.omp/logs/omp.2026-09-22.636150.log` registrou:

```text
2026-09-22T18:40:55.681-03:00 terminal disconnected; stopping interactive rendering
reason: stdin ended
2026-09-22T18:40:55.707-03:00 Session exit recorded
reason: sighup; kind: signal; pendingToolCalls: 0
```

Isso identifica a condição imediata de encerramento, mas não determina quem fechou a PTY ou por quê. Não há evidência suficiente para atribuir esse evento ao guard, a falta de memória ou a bug específico do Orca. Não foi aplicado workaround para ignorar SIGHUP e deixar uma sessão interativa órfã.

Recorte sanitizado preservado em [terminal-exit.json](evidence/2026-09-22-omp/terminal-exit.json), sem conta, email, credencial ou identificador de sessão.

## MCPs, hooks e skills

### MCPs

Configuração consolidada em `~/.omp/agent/mcp.json`, permissão **600**, usando fontes locais anteriores. Credenciais existentes foram preservadas; seus valores não devem entrar neste documento ou no git.

| Servidor | Transporte | Último estado observado |
|---|---|---|
| code-review-graph | `code-review-graph serve` | Ferramentas carregadas |
| paper-search | `paper-search-mcp` | Ferramentas carregadas |
| refero | HTTP | Ferramentas carregadas |
| scrapingdog | Node local, chave por variável de ambiente | Ferramentas carregadas |
| shadcn | `npx shadcn@latest mcp` | Ferramentas carregadas; resources/list não implementado |
| stock-images-mcp | `uvx` | Ferramentas carregadas |
| higgsfield | HTTP | 401, autenticação pendente |
| posthog | HTTP, read-only | 401, token ausente |
| supabase | HTTP | 401, token ausente |
| tally | HTTP | 401, autenticação pendente |
| magnific | HTTP | 401, autenticação pendente |
| lupaleads | HTTP | 401, token ausente ou inválido |

A configuração temporária `~/Documents/outis/.omp/mcp.json` foi removida porque não era herdada ao abrir uma sessão dentro de um repositório mais profundo. Esses servidores agora são de escopo **usuário**, inclusive fora de Outis. Paper-search ficou habilitado conforme a configuração Claude, embora estivesse desabilitado na configuração Codex anterior. Isso não demonstra equivalência exata entre as configurações antigas.

Não houve migração automática dos tokens OAuth. `/mcp reauth <nome>` é o ponto de entrada para servidores com OAuth; alguns podem exigir token/API key. Validar com `/mcp reload`, `/mcp list` e `/mcp test <nome>`. Um retorno 401 não foi tratado como servidor funcional.

Playwright MCP não foi portado; foi mantido o browser nativo do OMP. Não se instalou um sandbox novo.

### Hooks nativos

`~/.omp/agent/hooks/pre/dcg.ts`:

- Intercepta chamadas `bash`, envia o comando ao `dcg hook --batch --quiet` e bloqueia decisões de negação.
- Smoke real bloqueou `rm -rf ~/omp-guard-probe-nonexistent` pela regra `core.filesystem:rm-rf-root-home`; um `echo` seguro passou.
- Falhas do hook liberam a chamada: comportamento **fail-open**. Não cobre execuções por `eval`, `hub`, browser ou todas as outras ferramentas. Não é sandbox. Um timeout pode deixar arquivo temporário.

`~/.omp/agent/hooks/post/code-review-graph.ts`:

- Após `edit`/`write` bem-sucedido, executa `code-review-graph update --skip-flows` no diretório da sessão.
- Intervalo mínimo por sessão: 60 segundos; timeout do comando: 30 segundos; falhas não bloqueiam edição.
- Smoke com escrita real fez o `lastUpdated` do grafo avançar de 2026-08-22 para 2026-09-22 às 18h32min51s. O arquivo temporário `.omp-hook-probe.txt` foi removido.
- Não observa toda edição feita por shell e não agenda uma atualização final para alterações dentro do intervalo. Não prometer grafo sempre atualizado.

Pipelock não estava instalado e não foi portado.

### Skills compartilhadas

Foram movidos de `~/.codex/skills/` para `~/.agents/skills/` os diretórios:

- `agents-sdk`
- `cloudflare-email-service`
- `criativos-outis-codex`
- `durable-objects`
- `gerar-criativos`
- `sandbox-sdk`
- `soymi-imagegen`
- `workers-best-practices`

`.system` permaneceu no Codex. `gerar-conteudo` e `soymi-estampas` já eram symlinks para a pasta compartilhada. Não foi confirmada a existência de `SKILL.md` em `criativos-outis-codex`, nem sua remoção posterior. A lista de skills desabilitadas do Codex não foi transportada.

A skill `image-gen` ainda instrui uso de subprocesso Codex CLI; não foi reescrita. O smoke de imagem deste trabalho exercitou a ferramenta nativa OMP, não todas as skills de geração.

## Inventário de alterações e limites de instalação

| Local | Alteração |
|---|---|
| `~/Documents/my-llm-kit/scripts/agent_resource_guard.py` | Reconhecimento de OMP como agente vivo |
| `~/Documents/my-llm-kit/scripts/tests/test_agent_resource_guard.py` | Regressões focadas da classificação e poda |
| `~/Documents/my-llm-kit/instructions/AGENTS.md` | OMP como harness principal, papéis, caminhos e assinatura Codex |
| `~/Documents/my-llm-kit/setup.sh` | Inclusão do link `~/.omp/agent/AGENTS.md` no instalador Unix |
| `~/.omp/agent/config.yml` | Papéis, fallbacks, providers desativados e geração de imagem |
| `~/.omp/agent/models.yml` | Definições complementares de Sol 6 e Luna 6 via OAuth |
| `~/.omp/agent/mcp.json` | Consolidação dos doze MCPs no escopo usuário |
| `~/.omp/agent/agents/{deep-reasoner,fast-worker}.md` | Agentes nativos OMP |
| `~/.omp/agent/hooks/pre/dcg.ts` | Hook de proteção de comandos bash |
| `~/.omp/agent/hooks/post/code-review-graph.ts` | Atualização do grafo após edição/escrita |
| `~/.omp/agent/AGENTS.md` | Link para `~/.agents/AGENTS.md`, que aponta para as instruções do kit |
| `~/AGENTS.md` | Referências ao diretório compartilhado de skills e ao hook/MCP OMP |
| `~/Documents/outis/CLAUDE.md` | Roteamento de orquestração com agentes OMP e modelos Codex |
| `~/.agents/skills/` | Movimentações listadas acima |
| `~/.local/bin/agent-resource-guard` | Cópia instalada da correção |
| `research/2026-09-22-omp-gpt6-routing.md` e `research/evidence/2026-09-22-omp/` | Este registro e as evidências duráveis |

Os arquivos nativos em `~/.omp/agent/` não foram integrados ao instalador do kit; o ajuste em `setup.sh` instala apenas o link de instruções. Não afirmar que uma instalação limpa reproduz toda esta migração. `setup.ps1` e o README não foram atualizados. Os agentes originais do kit ainda têm frontmatter do host anterior. `~/AGENTS.md` pode conter referência antiga a `references/endpoints.md` da skill ScrapingDog; o índice observado na skill era `references/endpoint-index.md`.

Mudanças do usuário já presentes antes da tarefa, não pertencentes a esta migração:

- `skills/spec/SKILL.md`
- `skills/spec/references/plan-validation.md`
- `skills/spec/tools/package-lock.json`

Não fazer reset, limpeza ou commit em massa desses arquivos. Nenhum segredo foi removido de seus locais originais. Houve exposição de valores de credenciais em saídas da etapa anterior; este documento não os reproduz. Caso o histórico tenha sido compartilhado, avaliar rotação pelos provedores. Rotação não foi executada.

## Evidências de verificação

| Verificação executada | Resultado observado | Limite |
|---|---|---|
| `python3 -m unittest scripts.tests.test_agent_resource_guard -v` | Quatro testes passaram | Regressões focadas; não é a suíte completa do kit |
| `uvx ruff check scripts/agent_resource_guard.py scripts/tests/test_agent_resource_guard.py` | Passou | `python3 -m ruff` inicialmente indisponível; usou-se uvx |
| Simulação do guard instalado com limiar zero | OMP reconhecido, zero candidatos a poda | Fotografia do estado dos processos naquele momento |
| `cmp` da fonte e do binário instalado | Iguais | Conferido novamente na retomada |
| `systemctl --user status agent-resource-guard.timer --no-pager` | Ativo, aguardando, habilitado | Não foi desabilitado como workaround |
| `bash -n setup.sh` | Exit 0 nesta retomada | Instalador completo não foi executado |
| `omp config get disabledProviders` | HuggingFace, OpenCode Go e OpenRouter | Seleção; não cancelamento ou apagamento de credenciais |
| `omp models` | Somente grupo openai-codex, sete modelos de conversa | Geração de imagem é caminho próprio |
| Probes de `@default`, `@smol`, `@tiny`, `@slow` e seletores explícitos GPT-6 | Respostas OK | Fallback estava habilitado; recibos efetivos não foram inspecionados |
| `omp -p --model @vision --tools read ...` sobre imagem de maçã | Respondeu `Apple` | Reconhecimento simples; não avaliação geral de visão |
| `omp -p --model @smol --tools generate_image ...` | Gerou círculo azul em fundo branco | Papel image sem fallback externo; sem medição de quota |
| Dispatch CLI de `fast-worker` | Respondeu `pong` | Sem recibo independente do modelo/esforço do filho |
| Smoke DCG | Bloqueio destrutivo e permissão para echo | Somente caminho bash exercitado |
| Smoke de escrita e grafo | Timestamp do grafo avançou | Não cobre alterações por todas as ferramentas |
| MCP no diretório outis-central | Seis servidores com ferramentas; seis 401 | Auth pendente não é sucesso |

Primeiros probes Codex falharam com `model is not supported` para Sol/Luna e `usage_limit_reached` para outros seletores. Probes posteriores responderam. Não foi demonstrado se houve mudança de disponibilidade, quota ou uso de fallback; não atribuir causalidade sem recibos.

A imagem gerada após a correção para assinatura foi copiada de `/tmp/omp-image-158a10537ff1f764.webp` para [subscription-image.webp](evidence/2026-09-22-omp/subscription-image.webp). Inspeção visual confirmou o círculo azul sobre branco. Arquivo: 461960 bytes; SHA-256 `9dbf8c6ef57e5faf3dc3b1fc5ef6891d0335956ee6999fc6c2aa1b70ed225e5a`.

A imagem da maçã usada no teste de visão foi gerada antes, no caminho OpenRouter. Não apresentá-la como evidência de geração pela assinatura. Não é possível desfazer consumo já ocorrido; custo não foi medido.

## Disagreements

- Catálogo OMP atrasado em relação ao anúncio e ao cache Codex: foram usados modelos complementares, sem alterar o banco de cache manualmente.
- O default atual Astra/max difere da recomendação Sol/medium e da configuração feita anteriormente. O arquivo atual foi preservado; recomendação não substitui escolha do usuário.
- Esforços declarados não garantem esforço efetivo: `tiny:minimal` não consta na lista complementar; `deep-reasoner` tem `thinking-level: high` além do alias medium.
- Contexto API e contexto Codex não coincidiram nos valores locais. Contexto longo não foi certificado.
- As primeiras falhas e respostas posteriores não provam rollout ou reset de quota. Fallback não identificado permanece uma explicação possível.
- Documentação OMP sobre requisito de chave em modelos personalizados não coincidiu com o erro runtime, que aceitava `auth: oauth`. A configuração foi validada pelo runtime com OAuth; não foi adicionada chave paga por uso.

## Open questions

### Bloqueios concretos para a próxima sessão

1. Autenticar `higgsfield`, `posthog`, `supabase`, `tally`, `magnific` e `lupaleads`, com interação do usuário ou credencial apropriada. Os valores existentes não devem ser impressos. Depois executar `/mcp test <nome>`.
2. Se for necessária recomendação apoiada na comunidade, obter o conteúdo das discussões por um caminho acessível. Busca retornou URLs, mas leitura não trouxe conteúdo. Não existe consenso comunitário verificado neste registro.

### Verificações não realizadas, sem ampliar o escopo automaticamente

- Identificar nos recibos o modelo e esforço efetivos dos probes e subagentes antes de chamar a política de custo de validada.
- Confirmar ou limitar a janela de contexto conforme o endpoint da assinatura, antes de depender dos valores do catálogo API.
- Se houver nova saída com `stdin ended`/`SIGHUP` sem fechamento intencional, correlacionar horário com o terminal/host; a condição de saída foi registrada, a causa do fechamento da PTY não.
- Se a migração precisar ser reproduzível em outra máquina, versionar fontes seguras de agentes/hooks e estender o instalador; nunca versionar MCP com credenciais. Isso não foi implementado nesta sessão.
- Se solicitado, alinhar a skill `image-gen` e as referências antigas do kit ao runtime escolhido. Não confundir pendência de documentação antiga com falha do smoke nativo.

Comando inicial seguro para a próxima sessão: ler este arquivo e conferir apenas os arquivos que mudaram depois dele. Não repetir geração de imagem, buscas pagas ou todos os testes sem mudança relevante.

## Council review

- Status: not run
- Reason: Não houve pedido de council nem conclusão material apoiada somente em fonte secundária. O roteamento proposto é uma inferência operacional explicitada; não foi certificado por votação de agentes.
- Accepted findings: Nenhum parecer de council utilizado.
- Rejected findings: Nenhum parecer de council utilizado.

## Sources consulted

- https://openai.com/index/introducing-gpt-6-sol-and-luna/, accessed 2026-09-22.
- https://developers.openai.com/api/docs/models/gpt-6-sol, accessed 2026-09-22.
- https://developers.openai.com/api/docs/models/gpt-6-luna, accessed 2026-09-22.
- https://developers.openai.com/api/docs/models/gpt-6-astra, accessed 2026-09-22.
- https://developers.openai.com/api/docs/guides/reasoning, accessed 2026-09-22.
- https://learn.chatgpt.com/docs/models, accessed 2026-09-22.
- https://learn.chatgpt.com/docs/pricing, accessed 2026-09-22.
- https://developers.openai.com/api/docs/models/gpt-image-2.5-flare, accessed 2026-09-22; consultada para distinguir modelos de geração, não configurada como rota paga.
- https://developers.openai.com/api/docs/pricing, accessed 2026-09-22.

Documentação local OMP 18.2.9 consultada: `omp://models.md`, `omp://settings.md`, `omp://config-usage.md`, `omp://skills.md`, `omp://hooks.md`, `omp://context-files.md`, `omp://mcp-config.md`, `omp://task-agent-discovery.md`, `omp://tools/generate_image.md`, `omp://skills/authoring-hooks.md` e `omp://rulebook-matching-pipeline.md`.

Pesquisa local anterior reutilizada: `research/2026-09-06-codex-model-value.md`; refere-se à geração 5.6 e início de Astra, não substitui comparação controlada da família 6.

URLs comunitárias apenas localizadas, não usadas como evidência de desempenho: `reddit.com/r/codex/comments/1wnh5j8/gpt_6_sol_and_luna/`, `reddit.com/r/codex/comments/1wiea5j/so_concretely_is_astra_better_at_coding_than_sol/` e `reddit.com/r/codex/comments/1wmh2h1/gpt_6_astra_low_vs_gpt_56_sol_high/`.

## Trial by fire

- Primary-source claims: Modalidades, esforços documentados, posicionamento e taxas oficiais. São fatos do fornecedor na data de acesso; não são benchmarks independentes.
- Secondary-only claims: Nenhuma recomendação depende de comentários comunitários não lidos.
- Volatile claims: Disponibilidade da conta, quotas, créditos, catálogo, configuração atual e estado de autenticação dos MCPs.
- Limites de evidência: Sem comparação A/B local de qualidade, sem recibos completos de fallback/esforço, sem ensaio de contexto longo e sem medição de consumo total. A imagem e o recorte de saída do terminal têm arquivos duráveis; as páginas externas não têm snapshots locais.
