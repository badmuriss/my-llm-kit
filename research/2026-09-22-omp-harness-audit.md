# Auditoria do repositório e do harness OMP

Data: 2026-09-22. Baseline do repositório: `471bbed` mais as alterações locais da migração. Escopo autorizado: auditar o kit e a configuração efetiva do harness, explicar as pendências e publicar somente as alterações desta migração. O usuário não autorizou uma refatoração geral de todas as features preexistentes.

## Resultado

- Não foi identificado defeito bloqueador introduzido pelo reconhecimento de OMP no resource guard ou pelo alias de instruções.
- Foram corrigidas afirmações imprecisas da documentação: recomendações de modelo não representam a configuração atual; OMP lê o diretório compartilhado nativamente; setup não reproduz os agentes/hooks/MCP/modelos locais; o hook do grafo não observa todas as escritas.
- O default efetivo `openai-codex/gpt-6-astra:max` foi preservado. Nenhum modelo, segredo, conta ou assinatura foi removido.
- **Webshare não está configurado.** Não foram encontrados endpoint, credencial ou variáveis de proxy nos locais verificados. Nenhum tráfego foi redirecionado.
- Não houve segredo real confirmado nos arquivos publicáveis inspecionados. Configurações privadas do OMP não serão incluídas no commit.
- Existem defeitos preexistentes, listados abaixo. Auditoria concluída não significa que o repositório inteiro ficou livre de defeitos.

O [registro da migração](2026-09-22-omp-gpt6-routing.md) conserva a cronologia, os testes anteriores de imagem/visão/agentes e o diagnóstico dos encerramentos de sessão. As duas saídas por poda do guard e a saída posterior por desconexão de terminal não foram confundidas.

## O que falta exatamente

| Item | Estado | O que falta para concluir |
|---|---|---|
| MCP Higgsfield | HTTP 401 na última inicialização observada | OAuth/autenticação válida e `/mcp test higgsfield` |
| MCP PostHog | HTTP 401, token ausente | Token apropriado ou fluxo de autenticação suportado; testar servidor |
| MCP Supabase | HTTP 401 | Autorizar a sessão OMP e testar |
| MCP Tally | HTTP 401 | Autorizar a sessão OMP e testar |
| MCP Magnific | HTTP 401 | Autorizar a sessão OMP e testar |
| MCP LupaLeads | HTTP 401, token ausente/inválido | Autenticação válida e teste |
| Webshare | Não configurado | Se o usuário quiser usá-lo, obter endpoint/credencial e definir se o proxy é só para coleta web ou também para outras requisições; não redirecionar OAuth silenciosamente |
| Reprodução da instalação OMP em outra máquina | Configuração funcional local, não provisionada pelo setup | Versionar fontes sem segredos e criar instalação preservadora, caso essa portabilidade seja solicitada |
| Modelo/esforço efetivamente servido | Regras do resolver confirmadas por leitura; probes anteriores responderam | Inspecionar recibos do runtime/servidor, sem confundir resposta OK com prova de ausência de fallback |
| Contexto longo Sol/Luna pela assinatura | Não exercitado | Confirmar capacidade do endpoint e corrigir o limite local conforme a evidência antes de depender dele |
| Comparação comunitária dos modelos | URLs encontradas, conteúdo bloqueado | Ler fontes acessíveis se esse apoio comunitário ainda for necessário; não afirmar consenso |
| Falhas preexistentes abaixo | Auditadas, algumas reproduzidas com fixtures | Correções próprias e regressões por problema; não foram misturadas à migração |

A primeira coluna de seis MCPs não implica seis contas novas: são autorizações pendentes no host OMP. Não houve nova tentativa de login ou exposição de tokens. `reauth` só se aplica quando o servidor suporta esse fluxo; token de API não pode ser inventado.

## Cobertura

Foram inventariados os 270 arquivos rastreados do baseline e os novos arquivos da migração. A inspeção de segredos percorreu 272 textos e quatro binários publicáveis naquele momento. As evidências adicionais produzidas nesta auditoria usam apenas fixtures sintéticas e ambiente sem credenciais.

| Subsistema | Cobertura realizada |
|---|---|
| Instalação | `setup.sh`, `setup.ps1`, `install.sh`, manifesto, configuração DCG, systemd, scripts auxiliares, testes e CI |
| Guard | Classificação de processos, árvore de ownership, regressões OMP, fonte versus cópia instalada e evidência anterior do timer |
| Agent Graph e impl | Módulos de journal/ownership, adapters Host/Orca, snapshots, checks/singleflight, recovery, artefatos/quarentena, grade/complete, browser surfaces, roteamento, orçamento, progresso, cápsulas e aprendizado; testes críticos associados |
| Skills próprias | Coleções `computer-use`, `spec`, `research`, `scrapingdog`, `remove-ai-marks`, `rule-curator`, `writing`, `ingest`, `grill-*`, `readme-pass`, `trim-code-comments`, `frontend-visual-validation`, `thermo-nuclear-code-quality-review`; foco nos executáveis e contratos ativos |
| Documentação e instruções | README, política compartilhada, agentes distribuídos, caminhos de instalação e referências da migração; documentos históricos não tratados como política ativa |
| OMP instalado | `config.yml`, `models.yml`, agentes, hooks, descoberta de skills/instruções e módulos upstream responsáveis por resolução, precedência, fallback e eventos |
| MCP | Inventário, transportes, escopo, permissões e presença de credenciais de forma sanitizada; validade dos seis servidores pendentes não certificada |
| Providers/proxy | Variáveis do processo, arquivos `.env` previstos pelo OMP, configuração OMP/Codex, perfis de shell, configurações Claude/OpenCode e locais usuais Webshare |
| Publicação | Escopo dos arquivos, busca de segredos, remoto `badmuriss/my-llm-kit`, branch `main`, repositório público e permissão administrativa |

Limites da palavra “total”: todos os subsistemas próprios e as fronteiras operacionais do harness foram cobertos; não houve leitura linha a linha de todos os módulos grandes, schemas, testes, pesquisas históricas ou bibliotecas externas. Não foram auditados integralmente o código upstream do OMP, o aplicativo Orca, suas extensões próprias ou todos os pacotes externos instalados em `~/.agents/skills`. O inventário dessas skills não equivale a certificar sua implementação. Não foram executados serviços externos pagos, login OAuth, full setup na máquina real ou testes nativos macOS/Windows.

## Achados preexistentes confirmados

P1: risco alto para dados ou uma plataforma anunciada. P2: falha real de contrato, proteção ou automação com alcance mais restrito. Nenhum dos problemas desta tabela foi introduzido pelo patch de migração.

| ID | Prioridade | Evidência | Consequência e correção mínima | Verificação |
|---|---|---|---|---|
| A01 | P1 | `skills/remove-ai-marks/scripts/clean_file.py:36-49,79-96` | Binário desconhecido vira texto; com `--in-place`, a falha de encoding ocorre depois de abrir o original para escrita. Recusar formato desconhecido antes de escrever e exigir override explícito. | Reproduzido com arquivo sintético: nove bytes viraram zero, exit 1, backup preservou o original. |
| A02 | P1 | `skills/agent-graph/scripts/validation.py:213-222,927-947`; `graph_core.py:3456-3460` | A identidade de início POSIX depende de `/proc`; sem ela, o journal rejeita publicação do check. macOS não tem esse caminho. Implementar identidade nativa sem relaxar a proteção contra reutilização de PID. | Evidência estática de produtor/consumidor; execução nativa macOS não realizada. |
| A03 | P1 | `scripts/configure_opencode_mcp.py:61-67` | Remoção de vírgulas JSONC altera também strings JSON. Tornar a transformação consciente de strings/escapes. | Reproduzido: uma string sintética com vírgula antes de `]` perdeu a vírgula ao registrar MCP. |
| A04 | P2 | `scripts/configure_opencode_mcp.py:112-121` | Backup de configuração privada não preserva permissões. Criar backup privado atomicamente e preservar modo seguro. | Reproduzido com umask 022: original 0600, backup 0644. |
| A05 | P2 | `skills/agent-graph/scripts/validation.py:1033`; `graph_core.py:3620-3627` | Processo morto por sinal retorna código negativo, mas o journal só aceita não negativo. Normalizar a convenção ou ajustar produtor e contrato de forma consistente. | Runner real retornou -15 sem timeout; a rejeição do consumidor foi confirmada por leitura. |
| A06 | P2 | `skills/agent-graph/scripts/agent_graph.py:6181-6186,7523-7525,7561`; `runtime_pin.py:302-306` | `complete` remove o runtime fixado que a entrada CLI exige nas consultas seguintes. Preservar a capacidade de leitura de estado terminal e a idempotência sem executar runtime inválido. | Evidência estática; cenário completo pós-finalização não executado nesta auditoria. |
| A07 | P2 | `skills/remove-ai-marks/scripts/clean_file.py:122-131,139-153` | Modo JSON retorna sucesso mesmo quando a saída informa resíduos; modo textual avalia os resíduos. Calcular o resultado uma vez, independente do formato de saída. | Evidência estática; não se afirma limpeza real defeituosa em arquivo do usuário. |
| A08 | P2 | `setup.sh:525-539,683-689` | Backups usam somente a data e podem substituir um backup anterior do mesmo dia. Usar destino sem colisão antes de modificar dados. | Evidência estática; não se sobrescreveu backup real. |
| A09 | P2 | `setup.sh:695-696` | Falha de `dcg install` pode ser ocultada pelo último comando da função. Propagar a falha de instalação, mantendo diagnóstico do doctor separado. | Evidência estática de status de retorno. |
| A10 | P2 | `skills/scrapingdog/scripts/account_summary.sh:17-18` | A chave é expandida em argv do curl. Entregá-la por stdin ou cliente que leia ambiente internamente; testar com chave sintética. | Evidência estática; nenhum segredo real foi colocado em argv durante esta auditoria. |
| A11 | P2 | `.github/workflows/runtime.yml:5-20,41-47` | Alterações de setup/scripts não disparam o workflow e `scripts/tests` não roda no CI. A regressão nova do guard foi executada localmente, não está protegida pelo CI atual. | Workflow lido e suítes locais executadas separadamente. |

Reproduções duráveis: [audit-reproductions.json](evidence/2026-09-22-omp/audit-reproductions.json). Todos os arquivos e processos usados nesses quatro probes eram temporários e sintéticos. Nenhum comando foi executado contra dados do usuário.

### Endurecimento recomendado, sem defeito de publicação comprovado

`skills/research/scripts/collect_sources.py:37-50,67-84` aceita e encaminha a URL inteira. Se um operador lhe entregar URL com credencial, ela pode ser enviada ao provedor e persistida no registro. A skill exige conteúdo público, mas o helper não reforça esse contrato. Rejeitar userinfo e evitar persistência de credenciais conhecidas seria útil. Não foi demonstrada entrada sensível real, exploração ou segredo no Git; não foi classificado como exfiltração observada.

## Harness: contratos confirmados e riscos residuais

### Modelos e esforço

- `tiny:minimal` é normalizado a low, porque low é o primeiro esforço suportado pelos modelos complementares. Evidência: `pi-tui/src/thinking.ts:122-132` e `pi-catalog/src/model-thinking.ts:35-64` da instalação OMP.
- `deep-reasoner` usa o medium explícito do alias `@slow` antes do `thinking-level: high` do frontmatter. Evidência: `pi-coding-agent/src/task/executor.ts:3608-3612`. O frontmatter não foi confundido com o valor efetivo.
- Os fallbacks declarados continuam exclusivamente em `openai-codex`. `image: []` não herda a cadeia de chat.
- Os modelos complementares ainda declaram contexto 1050000. O cache Codex lido nesta auditoria informava padrão 272000 e máximo 872000 para Astra/Sol/Luna. Isso é divergência de metadados, não prova de que uma chamada de contexto longo funcionou. Não foi alterado o limite silenciosamente.
- Os agentes auditores informaram `openai-codex/gpt-6-astra` no contexto do harness. A API de task usada não expôs recibos suficientes para certificar esforço/faturamento individual; não se declarou que cada auditor usou o modelo mais barato possível.

### Instruções, skills e segurança

OMP lê `~/.agents/skills` e `~/.agents/AGENTS.md` diretamente, confirmado em `src/discovery/agents.ts:158-170,276-291`. O alias específico ausente no instalador Windows, portanto, não é defeito funcional de descoberta. Isso não certifica execução nativa no Windows.

A política compartilhada agora distingue recomendações de modelo da configuração efetiva e proíbe inferência paga por scripts opcionais sem autorização explícita. `disabledProviders` filtra o catálogo, mas não é firewall. Credenciais antigas foram preservadas, não revogadas.

O hook DCG é real, mas só cobre `bash` e falha aberto conforme sua política declarada. O hook de grafo é por sessão, com intervalo mínimo e sem atualização final agendada. Esses limites já eram documentados e não foram transformados em alegação de sandbox ou sincronização completa. A documentação local foi corrigida para não prometer isso.

O diretório `criativos-outis-codex` movido na migração contém `.tmp`, não um `SKILL.md` de raiz. Não foi apresentado como skill funcional nem apagado. `resume-tailoring` é uma coleção aninhada; outras coleções externas usam nomes de arquivo distintos. A presença de diretório sozinha não prova descoberta no OMP.

### MCP e permissões

Metadados observados: diretório `~/.omp/agent` 0700, `config.yml` e `mcp.json` 0600; `models.yml` 0664 fica protegido pelo diretório ancestral 0700. Remotos MCP usam HTTPS, sem usuário/senha ou query nas URLs inspecionadas. Valores de credenciais ficaram fora da saída e do repositório.

O escopo de usuário dos MCPs é intencional e está documentado. Não se demonstrou encaminhamento indevido por esse escopo. As seis respostas 401 continuam pendências; ferramentas carregadas nos outros seis servidores não certificam todos os seus endpoints.

### Webshare

Não apareceu nas variáveis de ambiente do processo; configs OMP/Codex/Claude/OpenCode; perfis de shell; `.env` do projeto; arquivos de ambiente globais previstos pelo OMP; MCP; ou diretórios locais usuais do produto.

OMP documenta `PI_PROXY_<PROVIDER>`, `PI_PROXY`, `HTTPS_PROXY`/`HTTP_PROXY` e `ALL_PROXY`. O proxy global pode atingir login, refresh e outros fetches, enquanto o específico do provider tem escopo menor. Por isso não se improvisou um proxy global só para marcar a integração como concluída. Referência local: `omp://environment-variables.md`, seção Outbound proxy routing, OMP 18.2.9.

## Achados considerados e rejeitados

- **“Ausência de alias OMP no Windows quebra instruções”**: rejeitado; descoberta compartilhada nativa foi localizada no consumidor.
- **“minimal e frontmatter high quebram as chamadas”**: rejeitado; o runtime normaliza/resolve esses valores. A configuração é pouco clara, mas não foi demonstrado erro de execução.
- **“Qualquer suporte OpenRouter/Ollama no kit viola a migração”**: rejeitado como conclusão geral. Integrações opcionais e backends explicitamente selecionados continuam features do kit. Não foram removidos por uma preferência do harness local. A preferência automática de Jev merece cuidado: a política superior agora exige autorização para inferência externa paga. Nenhum probe pago foi feito nesta auditoria.
- **“A skill de remoção de marcas promete que a CLI aceita diretórios diretamente”**: não confirmado; a instrução manda processar cada arquivo, o que pode ser feito pelo operador. Não se abriu uma feature de batch por inferência.
- **“Todo fallback ou provider desativado deixa de fazer qualquer rede”**: rejeitado; seleção de modelos e controle de rede são contratos diferentes.
- **“Há credencial real no Git porque o scanner encontrou um padrão”**: rejeitado nos dois casos classificados: eram fixtures sintéticas. Busca por padrões não prova ausência universal de segredos.

## Verificação

A primeira rodada das suítes Python usou HOME, XDG e Git global temporários, sem credenciais do ambiente. Não foi executado o instalador completo na máquina real. A saída original, inclusive falhas de invocação, fica em [audit-checks.json](evidence/2026-09-22-omp/audit-checks.json); os resultados complementares estão em [audit-additional-checks.json](evidence/2026-09-22-omp/audit-additional-checks.json).

| Verificação | Resultado |
|---|---|
| `unittest discover -s scripts/tests` | 36 testes passaram |
| `unittest discover -s skills/computer-use/tests` | 4 testes passaram |
| `unittest discover -s skills/spec/tests` | 18 testes passaram |
| `uvx --from pytest pytest -q skills/research/scripts/tests/test_audit_finding.py` | 7 casos passaram na invocação que também incluiu o arquivo standalone do ScrapingDog |
| `python3 skills/scrapingdog/scripts/test_account_summary.py` | Smoke CLI passou: `account_summary: ok` |
| `bash -n setup.sh install.sh` | Passou |
| Agent Graph completo | 388 testes passaram em 669,570 segundos na rodada detalhada |

A primeira invocação de research por unittest falhou por ausência de pytest; o teste ScrapingDog não foi coletado porque é um script standalone. Esses erros de invocação foram corrigidos, sem mudar o código testado. Zero testes coletados não foi contado como gate aprovado. Não restaram processos pertencentes à primeira rodada isolada na reconciliação realizada após o timeout.

O limite inicial de 300 segundos interrompeu a primeira rodada do graph. A rodada detalhada usou limite de 900 segundos, concluiu com exit 0 e preservou a saída em [graph-audit-check.json](evidence/2026-09-22-omp/graph-audit-check.json). Total: **453 testes passaram**, além do smoke standalone ScrapingDog. Nenhum dos defeitos estáticos listados foi descartado só porque a suíte existente passou. A reconciliação final não encontrou processos remanescentes das duas execuções isoladas; os três scripts temporários desta auditoria foram removidos.

- `uvx --from ruff==0.16.5 ruff check .`: passou, sem relaxar a configuração de complexidade.
- `npm audit --omit=dev --ignore-scripts --json` em `skills/spec/tools`: zero vulnerabilidades reportadas; 200 dependências no inventário. Isso não prova ausência de vulnerabilidades desconhecidas.
- `omp --version`: 18.2.9.
- Links de instruções OMP e compartilhadas resolvem para `my-llm-kit/instructions/AGENTS.md`.
- Os quatro probes sintéticos produziram os resultados descritos em A01, A03, A04 e A05.
- Execução nativa macOS/Windows, contexto longo, OAuth pendente e recebimento de modelo no servidor continuam não observados.

## Alterações e publicação

Entram no commit: correção do guard e regressões, alias OMP, política compartilhada corrigida, README com limites de instalação, registro de migração, este relatório e evidências sanitizadas. Configuração privada OMP, tokens e arquivos de sessão não entram.

A correção de `~/AGENTS.md` existe apenas no ambiente local: referência para `endpoint-index.md` e descrição honesta da atualização do grafo. Não faz parte do repositório e não será apresentada como conteúdo publicado.

Permanecem fora do commit por serem trabalho anterior do usuário:

- `skills/spec/SKILL.md`
- `skills/spec/references/plan-validation.md`
- `skills/spec/tools/package-lock.json`

O push autorizado é para `origin/main`, sem force. O hash e o resultado remoto serão informados na resposta final, após execução. Este relatório não afirma publicação antes de ocorrer.
