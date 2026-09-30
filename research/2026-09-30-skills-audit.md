# Auditoria de skills compartilhadas e my-llm-kit

## Instalação por prompt solicitada

- [x] Substituir os instaladores do kit por um prompt e um contrato de instalação no README.
- [x] Manter a base pequena, o catálogo opcional e a descoberta adaptada ao harness ativo.
- [x] Preservar skills próprias, configuração nativa, credenciais e recursos de graph/PDF.
- [x] Retirar helpers e testes exclusivos dos instaladores e corrigir referências ativas.
- [x] Verificar os pacotes instalados em diretórios temporários e registrar os limites observados.
- [x] Retirar todos os GitHub Actions, suítes de testes, fixtures exclusivos e dependências de desenvolvimento conforme a instrução posterior.

Esta mudança altera a distribuição do kit. A instalação local existente continua
preservada; os registros anteriores descrevem os instaladores usados na época.
O catálogo está no README, com duas skills de base e os mesmos sete pacotes
externos opcionais. Saíram os instaladores Bash/PowerShell, o manifest e os
helpers exclusivos de instalação e configuração automática por host. Stagehand
usa as dependências travadas no próprio pacote; a extensão OMP é uma escolha
explícita.

Antes da instrução posterior para retirar os testes, os 38 testes restantes dos
helpers passaram. A verificação em diretórios temporários também confirmou o uso
do research por link e por cópia, a partir de outro projeto e sem credenciais,
os recursos de policy e runtime de graph e o acesso ao CLI de PDF. A descoberta
numa instalação nova de cada harness e os sistemas Windows/macOS nativos continuam
não observados. Suítes de testes e automação GitHub Actions não fazem parte do
modelo de distribuição solicitado.
Os workflows, diretórios de testes, scripts de smoke, fixtures e dependências de
desenvolvimento saíram do checkout. A regra específica deste repositório impede
que essa infraestrutura seja recriada; a política compartilhada para projetos
consumidores mantém seu escopo próprio.
Evidência: [instalação por prompt](evidence/2026-09-30-skills-audit/prompt-installation.json).

## Publicação solicitada

- [x] Conferir os repositórios, remotes e mudanças pendentes, incluindo trabalho anterior autorizado pelo usuário.
- [x] Verificar os helpers de research/Webshare e os scripts afetados antes de publicar.
- [x] Criar commits e publicar os três repositórios com origin, preservando mudanças novas do remoto.
- [x] Criar commit local em .agents.
- [ ] Publicar .agents quando houver um destino remoto informado.

O repositório local .agents não tinha remote configurado na conferência. Seus
backups de recuperação, caches e clones upstream ficam fora dos commits.
Os pushes de `my-llm-kit`, `incredibly-pretty-websites` e `site-audit` foram
confirmados pelo hash da branch remota. O commit local de `.agents` é `9259e6b`;
a URL necessária para o push foi solicitada e continua pendente.
Evidência: [publicação e checks adicionais](evidence/2026-09-30-skills-audit/publication.json).

**Limpeza aplicada: 47 retiradas e 9 consolidações das 95 entradas originais.**
A raiz compartilhada agora tem 40 skills: o núcleo de 5, as 34 opções preservadas
e `agent-graph`, instalado como recurso opcional. A família HyperFrames/Remotion
inteira saiu do catálogo, assim como `gerar-criativos`. Nas skills de código,
o corte se justifica principalmente pela repetição das instruções globais
e de outras skills, e pela imposição de preferências fora do contexto do projeto.

O critério principal é **portabilidade entre harnesses**. OMP é a preferência
atual, não uma dependência da base compartilhada. Conhecimento de domínio,
contratos e utilidades continuam úteis quando o usuário troca de agente;
integrações específicas precisam declarar o host e continuar opcionais.
A preferência por Playwright para vídeos também foi fornecida pelo usuário.
Não houve comparação da qualidade dos renderizadores ou benchmark de
modelos com e sem skills: os destinos abaixo são julgamentos sobre o corpus local
e sua adequação ao uso declarado, não provas de superioridade de um modelo.

Data de inspeção e acesso às fontes locais: **2026-09-30**. O inventário registra
o estado anterior à retirada do Refero. As tabelas individuais preservam os
pareceres desse inventário; a seção de aplicação registra o resultado autorizado
depois da auditoria.

## Ajuste de portabilidade solicitado

OMP é a preferência atual, e o conjunto compartilhado deve continuar útil quando
o usuário trocar de harness. A revisão abaixo aplica esse critério; fatos do
scanner OMP continuam evidência daquele host, sem definir o contrato das skills.

- [x] Tornar a política compartilhada independente do harness, preservando configuração nativa.
- [x] Tornar a escolha de browser e os scripts Stagehand independentes da extensão OMP.
- [x] Atualizar os dois setups para AGENTS.md e proteger instruções CLAUDE.md exclusivas.
- [x] Retirar os CLAUDE.md globais redundantes na máquina e conferir os aliases AGENTS.md.
- [x] Rever as recomendações da auditoria e verificar instalação em diretório temporário.

A política em AGENTS.md agora usa capacidades e configuração do harness ativo.
As escolhas nativas de modelos, roles, MCP e hooks foram preservadas. O arquivo
duplicado `~/.claude/CLAUDE.md` saiu e `~/.claude/AGENTS.md` aponta para a política
compartilhada; o `~/CLAUDE.md` vazio também saiu. Os dois setups usam AGENTS.md
e só retiram CLAUDE.md vazio ou equivalente à política gerenciada. Instruções
exclusivas permanecem para migração explícita.

Os nove testes do módulo de instaladores passaram em Linux, com homes temporários,
incluindo preview sem escrita, reinstalação, preservação de instruções próprias
e Stagehand sem criar configuração OMP. Ruff, sintaxe Bash/JavaScript e os dois
validadores de skills passaram. PowerShell não estava disponível; Windows e
macOS nativos, assim como descoberta efetiva de instruções em cada versão de host,
continuam não verificados. Fixtures CLAUDE.md e caches de plugins são fontes de
teste/upstream e não foram tratados como instruções globais duplicadas.
Evidência: [portabilidade aplicada](evidence/2026-09-30-skills-audit/harness-portability.json).

## Aplicação dos cortes autorizada

- [x] Arquivar as 47 retiradas e as 9 entradas consolidadas, preservando fontes e mudanças locais.
- [x] Integrar referências Cloudflare, design e performance e preservar os recursos opcionais de graph/PDF.
- [x] Enxugar os entrypoints mantidos e reconciliar computer-use por capacidade e autorização.
- [x] Ajustar instalação padrão/full em shell, PowerShell e installer legado, sem reinstalar entradas retiradas.
- [x] Verificar catálogo, links, arquivos preservados e instalação em diretório temporário.

As versões retiradas e os arquivos anteriores às edições ficam em
[skills-disabled/2026-09-30-cleanup](../../../.agents/skills-disabled/2026-09-30-cleanup/),
fora da descoberta ativa. O kit passou de 17 para 8 entrypoints. Sua instalação
padrão contém só `research` e `frontend-visual-validation`; os outros 6 são opcionais.
Os aliases retirados nos hosts e as entradas correspondentes do lock também foram
arquivados. A assinatura encerrada do Refero já havia motivado seu corte.

Cloudflare recebeu os quatro conjuntos de referências especializadas; websites
recebeu design engineering, e site-audit recebeu o diagnóstico por traces.
Os entrypoints Cloudflare, websites e skill-creator foram reduzidos a roteadores
com referências condicionais. Computer-use tem um único dono portátil; Orca,
Stagehand e Jev dependem da capacidade e autorização efetivas. O fluxo de mídia
usa a capacidade da sessão e Playwright para vídeos autorados, sem abrir outro
agente para obter ferramentas.

Os recursos de graph/PDF continuam nos caminhos existentes, sem SKILL.md próprios
em spec/impl. Novos handoffs passam por `agent-graph`; runtimes congelados antigos
mantêm seus contratos. A política comum e os critérios de manutenção ficam em
AGENTS.md, com a licença upstream preservada. Shell e PowerShell só instalam a
dependência e verificam o runtime de graph no perfil full. Firecrawl setup instala
apenas Research Index, evitando recolocar seus quatro roteadores genéricos.

Evidência da aplicação: [skills-cleanup.json](evidence/2026-09-30-skills-audit/skills-cleanup.json).

O scanner real do OMP encontrou **40 entradas, zero avisos** e exatamente os
nomes esperados. Passaram 10 testes de instaladores, 13 do driver de host e 6 de
runtime congelado, além de Ruff, sintaxe Bash e 17 validadores de skills. O perfil
full foi conferido por preview em HOME temporário, sem escrita; a instalação real
das integrações não foi executada. O runtime opcional carregou de um alias
instalado em um projeto separado, e o renderer PDF manteve sua CLI. Isso não
certifica uma nova renderização PDF, inferência ou todos os workflows.

Foram conferidos 91 hashes de arquivos arquivados e versões anteriores às edições,
os 69 aliases de host retirados, as entradas restantes do lock e quatro hashes de
configuração OMP. Os 25 checks de conteúdo/link preexistentes do kit e os 466 da
árvore compartilhada não tiveram alterações sem explicação. Windows/PowerShell
e macOS nativos permanecem não verificados. Fontes: [scanner final](evidence/2026-09-30-skills-audit/omp-root-scan-after-cleanup.json),
[checks da aplicação](evidence/2026-09-30-skills-audit/cleanup-checks.json) e
[preservação](evidence/2026-09-30-skills-audit/cleanup-preservation.json).

## Cobertura e verificação

| Conjunto inspecionado | Quantidade | O que o número representa |
|---|---:|---|
| Raiz `~/.agents/skills/<nome>/SKILL.md` | 95 | Entrada direta do provider `agents` do OMP |
| Skills sincronizadas em `synced/` | 14 | Fontes de outro host, fora desse scanner padrão |
| Coleção `resume-tailoring` aninhada | 1 | Entrypoint existente, fora desse scanner padrão |
| Snapshot `impeccable` dentro de pesquisa de websites | 1 | Fonte documental, não uma instalação global |
| Entrypoints em `my-llm-kit/skills` | 17 | 15 já ligados à raiz compartilhada, 2 fontes adicionais |
| Total de ocorrências `SKILL.md` | 128 | Inclui aliases entre kit e instalação |
| Arquivos distintos por caminho resolvido | 113 | Remove os 15 aliases, não cópias independentes |
| Entrypoints em backups/desabilitadas | 12 | Arquivo histórico, fora dos totais anteriores |
| Diretórios sem `SKILL.md` | 3 | `contract-review`, `copywriting`, `criativos-outis-codex` |

O scanner real da instalação local do OMP 18.4.4 foi executado isoladamente sobre a raiz
compartilhada: **95 skills, zero warnings**, sem iniciar uma sessão de inferência.
Ele busca filhos diretos e respeita `enabled: false`; não percorre automaticamente
`synced/`, coleções ou snapshots. Isso confirma descoberta por esse provider,
não funcionamento de todas as skills ou equivalência entre hosts. Fontes:
[resultado do scanner](evidence/2026-09-30-skills-audit/omp-root-scan.json),
[implementação local](../../../.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent/src/discovery/helpers.ts).

Foram inspecionados metadados de todos os entrypoints e os corpos/trechos que
fundamentam os destinos. A leitura foi mais detalhada no kit, nas instruções de
código e nas fronteiras de ferramentas, instalação e host. Para pacotes
explicitamente abandonados, o vínculo com o framework e suas dependências bastam
para o parecer; não foi revisada linha a linha toda sua implementação. Foram
inspecionados recursos dirigidos, como os scripts de avaliação de `skill-creator`
e os contratos de graph e resumo visual. A auditoria cobre o catálogo inteiro,
mas não certifica a segurança de todos os scripts, assets e dependências.

O inventário registra paths, destinos dos links, origem conhecida, descrições,
hashes e recursos presentes. Contagens de palavras são tamanho de conteúdo,
não tokens carregados por sessão. O OMP apresenta descrições e manda ler a skill
correspondente; um corpo grande pesa quando selecionado. Não foram medidos
latência, consumo efetivo de contexto, frequência de uso ou ganho de qualidade.
Fontes: [inventário](evidence/2026-09-30-skills-audit/inventory.json) e
[prompt local do OMP](../../../.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent/src/prompts/system/system-prompt.md).

## Critério de corte

Uma skill permanece quando acrescenta uma ferramenta, um contrato operacional,
conhecimento privado de domínio ou uma preferência recorrente que realmente
altera decisões. Uma instrução genérica como usar nomes claros, verificar o
resultado ou evitar abstrações não ganha valor só por estar em outro arquivo.
O critério segue `skill-creator` e o [rule-curator do kit](../skills/rule-curator/SKILL.md).

Por esse mesmo critério, `ingest` também sai: é um entrypoint curto, mas sem
helper próprio, e seus cuidados já estão em AGENTS e research. Isso não remove
conversores ou ferramentas de PDF/Office. O corte avalia informação adicional,
não apenas tamanho.

| Destino | Significado da recomendação |
|---|---|
| Remover | Retirar a entrada e o fluxo do catálogo; preservar trabalho e ativos do usuário |
| Consolidar | Retirar a entrada depois de transferir conteúdo ou código exclusivo para seu dono |
| Sob demanda | Fora do núcleo; usar apenas no domínio, formato ou runtime correspondente |
| Manter | Uma entrada útil no núcleo, enxugada onde indicado |
| Host de origem | Deixar a cópia sob gestão do host/sincronização correspondente |
| Fonte arquivada | Material de pesquisa, sem instalação global |

“Sob demanda” não é uma alegação de inutilidade, nem prova de que o usuário nunca
usa a capacidade. É a escolha conservadora quando não há motivo demonstrado para
mantê-la no núcleo compartilhado. Não se propõe alterar silenciosamente a política de
invocação das skills: a futura limpeza precisa escolher as fontes instaladas,
preservando autorização e configuração do usuário.

## Achados que mais mudam a decisão

### A família de vídeo pode sair inteira

Há **20 skills com origem registrada `heygen-com/hyperframes` e uma de Remotion**.
Não basta remover diretórios cujo nome começa com `hyperframes`: `media-use`,
`general-video`, `embedded-captions`, `slideshow`, os explainers e os vídeos de
produto continuam roteando, instalando ou usando o mesmo framework. A skill de
entrada se declara obrigatória para uma faixa ampla de vídeo, animação e decks;
os workflows chamam `npx hyperframes skills update` e remetem à composição core.
Fontes: [entrada HyperFrames](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes/SKILL.md),
[general-video](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/general-video/SKILL.md),
[legendas](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/embedded-captions/SKILL.md) e o inventário.

Esses 21 entrypoints somam **56.491 palavras**. É material destinado a uma stack
que o usuário decidiu abandonar. A retirada é justificada pelo uso declarado,
mesmo que os contratos façam sentido para quem continua usando HyperFrames.
Os scripts de áudio, transcrição, composição e assets não devem ser transplantados
em bloco para criar uma nova dependência sobre o fluxo Playwright.

Não recomendo criar imediatamente outro pacote grande de vídeo. Se o fluxo
Playwright já entrega, conservar seus scripts de projeto e critérios concretos
de captura, duração, áudio e inspeção de frames. Uma skill pequena só se justifica
quando houver um procedimento recorrente e não óbvio a preservar.

`frontend-slides` é outra decisão: produz apresentações HTML e não exige
HyperFrames. Vai para sob demanda, sem inferir que o usuário abandonou slides.

### As cinco skills genéricas de código têm pouco valor adicional

`coding-guidelines`, `typescript`, `react`, `software-engineering` e
`review-changes` repetem tipos, nomes, organização, testes e controle de fluxo.
São **1.824 palavras**, sem helpers exclusivos. Há regras como proibir constantes
ou funções em componentes, sempre preferir early return, preferir hash-lists a
switch e tratar comentários como desnecessários em 98% dos casos. O problema
observado é transformar preferências em requisitos universais, sem demonstrar
sua relação com a mudança pedida. Fontes:
[coding-guidelines](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/coding-guidelines/SKILL.md),
[react](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/react/SKILL.md),
[typescript](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/typescript/SKILL.md),
[software-engineering](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/software-engineering/SKILL.md) e
[review-changes](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/review-changes/SKILL.md).

Removeria as cinco. Preferências realmente pessoais devem permanecer uma vez
nas instruções aplicáveis do projeto ou no estilo já demonstrado pelo código.
O catálogo `vercel-react-best-practices` tem regras específicas de performance
e referências separadas, então pode continuar como recurso sob demanda,
restrito ao problema e à versão do projeto. Não é justificativa para carregar
um manual de otimização em toda edição React.

### Spec e impl repetem a política compartilhada, mas têm recursos portáveis

As instruções compartilhadas já definem escopo, aceite, verificação, testes
proporcionais, resumption e cleanup. `spec` e `impl` acrescentam outro roteamento
para direct, verified_single, light_spec e graph. Consolidaria a política comum
em AGENTS.md, preservando planejamento e execução portáveis, o renderer visual
e os contratos de graph em recursos opcionais. Um modo nativo de planejamento
ou uma ferramenta de tarefas em um host não demonstra substituição dessas
capacidades em todos os harnesses e não basta como motivo de remoção.
Fontes: [spec](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/spec/SKILL.md), [impl](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/impl/SKILL.md),
[instruções compartilhadas](../instructions/AGENTS.md).

O renderer `render_visual_brief.py` produz HTML/PDF e diagramas locais; é uma
utilidade concreta. Pode permanecer opcional para pedidos de resumo visual,
sem obrigar PDF em todo planejamento substancial. O journal, ownership,
geração do coordenador, proveniência de checks e recuperação de `agent-graph`
também são funcionalidade real. Não foram demonstradas capacidades equivalentes
em ferramentas nativas de tarefas dos hosts, portanto não se recomenda trocar
uma pela outra por nome. Fontes: [visual brief](../skills/spec/references/visual-brief.md) e
[contrato do graph](../skills/agent-graph/SKILL.md).

**Há uma lacuna de instalação atual:** `agent-graph` existe no kit e no manifesto
core, mas não existe em `~/.agents/skills/agent-graph`. Os aliases de `spec` e
`impl` estão presentes. Trabalho leve continua independente do runtime, mas
não se deve anunciar o caminho graph global como instalado. Isso foi observado
por inspeção de paths; não foi executado um graph.

### Algumas skills continuam orientadas a outro host

`image-gen` manda chamar `codex exec`, com pressupostos sobre Claude e paths
locais Outis. Removeria esse wrapper do catálogo compartilhado por obrigar um
segundo coding agent. A geração usa uma capacidade disponível e configurada
no host ativo; se não existir, sua ausência deve ser reportada. Requisitos de
marca permanecem no projeto. O OMP possui `generate_image` na instalação
inspecionada; isso é um exemplo local, não o contrato comum.
Isso não certifica uma geração de imagem atual: nenhuma foi executada.
Fontes: [image-gen](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/image-gen/SKILL.md) e
[ferramenta OMP](../../../.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent/src/tools/image-gen.ts).

Os loops de avaliação da `skill-creator` global escrevem em `.claude/commands`
e executam `claude -p`. Vale manter uma única capacidade de autoria/validação,
com avaliação condicionada às ferramentas do host ativo. Os loops específicos
de Claude ficam fora do caminho comum. Não é necessário construir agora uma
nova plataforma de evals.
Fonte: [run_eval.py](../../../.agents/skills/skill-creator/scripts/run_eval.py).

As 14 cópias em `synced/` já ficam fora do scanner compartilhado padrão OMP.
Não contam como 14 economias de contexto nessa rota. `computer-use`,
`built-in-browser` e `chrome-browser` desse bucket dependem de ferramentas
Claude; `docs`, `import-memory` e `morning` também trazem contexto daquele host.
As ferramentas de formatos e de MCP podem ter conteúdo portável. Para usar
isso em outro harness, selecionar uma versão portável por capacidade e instalar sob demanda,
em vez de copiar o bucket inteiro ou apagar a fonte gerida pela sincronização.

### Existem dois computer-use diferentes e vários roteadores de browser

A skill global `computer-use` é um diretório real com um stub Orca que carrega
o guia da versão do executável. A do kit contém runner Jev, preferência por
esse backend quando autorizado, Stagehand e Orca. Como `setup` preserva um
diretório real do usuário, a alteração do kit não atualiza automaticamente
a cópia global. Fontes: [cópia global](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/computer-use-before-consolidation/SKILL.md),
[cópia do kit](../skills/computer-use/SKILL.md) e [setup](../setup.sh).

O browser disponível no host, scripts Stagehand e suites Playwright existentes
devem ser avaliados pelo contrato da tarefa; desktop pode precisar de Orca. Jev e
TypeSafe permanecem ferramentas de outro modelo/serviço, dependentes de
autorização própria. A assinatura do coding agent não autoriza usar esses
serviços. `agent-browser`, `firecrawl-interact` e ferramentas Claude são
outros contextos, não a mesma sessão autenticada.

A preferência Playwright para vídeo **não revoga** a migração Stagehand de
automação documentada em setembro. Não foi desfeita nem testada novamente.
Fonte: [registro da migração](2026-09-23-stagehand-migration.md).

A correção de portabilidade alterou a skill Stagehand para descrever primeiro
os scripts locais. Sua extensão OMP é opcional e só se instala quando o diretório
do host existe. A validação visual escolhe um backend disponível com os engines
exigidos, sem impor uma ferramenta OMP. Isso não certifica browser ou visão em
todos os hosts; a verificação dessa alteração foi de instalação e contrato.

### Pesquisa e Cloudflare pedem consolidação de rotas

O `research` atual e as instruções globais escolhem Scrapinho para descoberta
e aquisição pública genéricas. `firecrawl`, `firecrawl-search` e
`firecrawl-scrape` ainda se apresentam como padrão amplo. Removeria essas
entradas globais, preservando o CLI e os métodos especializados. A retirada
de uma skill genérica não autoriza mudar provedores sem paridade ou contornar
recusa, quota ou autenticação. Fontes: [research](../skills/research/SKILL.md),
[Firecrawl](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/firecrawl/SKILL.md) e
[política compartilhada](../instructions/AGENTS.md).

Research Index, Developer Index, crawl, monitor e outros métodos especializados
vão para sob demanda. Monitoramento é um serviço real; apagar sua skill não
cancela monitores. O setup atual instala o conjunto core do Firecrawl quando
falta a skill Research Index, portanto a limpeza precisa ajustar essa origem
de reinstalação. Fontes: [setup](../setup.sh) e
[monitor](../../../.agents/skills/firecrawl-monitor/SKILL.md).

No stack Cloudflare, manteria um único roteador `cloudflare`, com referências
para Agents SDK, Durable Objects, Workers e email. Essas referências contêm
contratos úteis; o corte é de entradas concorrentes, não dos contratos.
Várias ainda orientam Wrangler amplamente, enquanto a política do usuário
seleciona `cf` em projetos novos e preserva Wrangler nos existentes. A
consolidação precisa respeitar essa diferença e a versão real do projeto.
Fonte: [instruções compartilhadas](../instructions/AGENTS.md).

### Design também tem excesso de processo

`incredibly-pretty-websites` tinha **14.990 palavras no entrypoint** na inspeção
inicial, além de recursos próprios. Mandava carregar `refero-design` primeiro
quando disponível. Refero cobre quase toda UI/design, e `emil-design-eng` mais três
skills de motion acrescentam formatos e passos próprios. Manteria um único
fluxo de design do usuário e referências condicionais para pesquisa, motion
e implementação. O tamanho sozinho não prova inutilidade; a concorrência de
roteamento e obrigações globais justifica o corte. Fontes:
[websites](../../incredibly-pretty-websites/SKILL.md),
[fonte Refero preservada](../../../.agents/community-skills/refero-design/skills/refero-design/SKILL.md) e o inventário.

O usuário confirmou depois que não tem mais assinatura do Refero. Seu destino
passa de consolidar para remover; o fluxo de websites deve usar a pesquisa
gratuita já disponível, sem depender da skill ou do MCP Refero.

Refero e Chrome DevTools não aparecem entre os servidores de
`~/.omp/agent/mcp.json` inspecionados. Isso não prova indisponibilidade em
qualquer host, mas impede tratá-los como pré-requisitos locais já garantidos.
`web-perf` exige Chrome DevTools MCP e manda parar sem ele. Seu diagnóstico
por traces pode virar um modo opcional de `site-audit`, com ferramenta
realmente disponível. Preservar a coleta e medição; não carregar outra
auditoria sobre toda alteração de frontend.

### Retirada do Refero aplicada

O pedido adicional autorizou a retirada pontual de `refero-design`. Seus aliases
saíram de `~/.agents/skills` e `~/.codex/skills` e foram arquivados em
`~/.agents/skills-disabled/2026-09-30/`. Claude compartilha o diretório de
`.agents`, portanto a mesma retirada cobre esse host. A fonte em
`community-skills` permanece preservada. A entrada Refero também saiu do lock
local de instalação, sem alterar os demais registros.

O entrypoint de `incredibly-pretty-websites` deixou de chamar a skill e as
ferramentas Refero. A pesquisa passa pelas referências gratuitas existentes;
README e referência de pesquisa acompanham esse fluxo. A menção que alerta
que Refero não é uma fonte gratuita permanece na lista de serviços pagos.

Verificação observada: **94 skills no scanner real do OMP, zero warnings e
somente `refero-design` ausente em relação às 95 anteriores**. A skill de websites
passou no validador de `skill-creator`. A retirada não executou os demais cortes
propostos. Evidências: [registro da retirada](evidence/2026-09-30-skills-audit/refero-removal.json)
e [scanner após Refero](evidence/2026-09-30-skills-audit/omp-root-scan-after-refero.json).

## Núcleo recomendado

| Skill | O que precisa permanecer |
|---|---|
| `research` | Provedores configurados, escopo, idempotência, proveniência e leitura completa das fontes |
| `frontend-visual-validation` | Estados relevantes, capturas reproduzíveis e julgamento visual |
| `cloudflare` | Um roteador do stack, fontes atuais e referências específicas sob demanda |
| `incredibly-pretty-websites` | Preferências reais de design e helpers, com entrypoint menor |
| `skill-creator` | Autoria/validação portáveis, com integrações de avaliação condicionais |

O conjunto é uma recomendação para a máquina e rotina do usuário, não uma
obrigação para todo consumidor do kit. As três últimas dependem da origem
externa/local correspondente; não devem virar instalação compulsória no
kit público. `spec`, `impl`, `writing` e os checklists genéricos não precisam
permanecer como entradas adicionais. Preferências de escrita ficam uma vez
nas instruções; prosa autoral pode usar `unslop` quando o trabalho a pede.

Os 34 itens sob demanda têm capacidades ou domínios mais específicos.
Mantê-los no núcleo por precaução recompõe o problema. Emprego, Soymi,
NotebookLM, publicação em X e formatos de arquivo devem acompanhar os
projetos que os usam. Não se inferiu abandono de Soymi ou de todo marketing
a partir do abandono de `gerar-criativos`.

## Base histórica dos ajustes de distribuição

Os achados abaixo descrevem o estado inicial. A aplicação e seus limites estão
registrados acima; plugins e fontes sincronizadas seguem sob seu próprio dono.

1. **Preservar trabalho antes de retirar fontes.** `~/.agents` é um repositório
   com 268 registros modificados, 273 removidos e 204 não rastreados no status
   capturado. O kit também já tinha 26 registros alterados/não rastreados.
   A retirada futura precisa preservar essas mudanças, inclusive as da família
   de vídeo. Não apagar projetos, mídia, perfis ou dados de cliente junto com
   as instruções globais.
2. **Ajustar os dois instaladores.** O core atual declara `spec`, `impl`,
   `agent-graph`, `writing` e validação visual. A instalação/validação Python
   do graph é incondicional em shell e PowerShell. Tornar graph opcional
   exige alterar esses passos e mover seus contratos; editar só a lista do
   manifesto deixa instalação e verificação incoerentes.
3. **Controlar as fontes do full.** `--full` enumera todos os diretórios do
   kit com `SKILL.md`, instala os repositórios declarados e faz fan-out de
   todo o diretório compartilhado. Skills retiradas devem sair das fontes
   de instalação aplicáveis, ou voltarão. A preservação de diretórios reais
   do usuário precisa continuar intacta.
4. **Tratar instaladores upstream e plugins.** O lock local registra origem
   HyperFrames, Firecrawl, Remotion e outras; não é telemetria de uso nem
   prova de atualização automática. Não basta apagar uma pasta se outro
   instalador a repõe. Firecrawl também está exposto por plugin nesta sessão
   Codex, fora do escopo de arquivos do OMP: retirar sua cópia de `.agents`
   não certifica sua retirada de todos os catálogos.
5. **Consolidar antes de excluir código útil.** Mover referências Cloudflare,
   design e perf, o lifecycle de graph e o renderer visual para os donos
   finais. Atualizar caminhos/callers e preservar licenças. Tirar Jev do
   roteamento genérico não exige apagar seu runner opcional.
6. **Limpar aliases e resíduos pelo dono correto.** Há três links quebrados
   nas raízes de hosts inspecionadas: `gerar-conteudo`, `soymi-estampas` e
   `llm-council`. As duas skills com `skill.md` minúsculo, o diretório
   `.tmp` de criativos, backups e snapshots não entram no scanner padrão.
   Sua limpeza é de organização, sem contar como redução de 95 entradas.
7. **Verificar o resultado nos hosts em uso.** Repetir descoberta real em cada
   harness efetivamente exercitado, conferir cada capacidade mantida com seu menor check útil e exercitar
   instalação em HOME temporário. Shell e PowerShell precisam continuar
   alinhados; comportamento nativo Windows/macOS fica não verificado até
   teste nessas plataformas. Não instalar na máquina real como teste.

Fontes da distribuição: [manifesto](../install-manifest.json),
[setup shell](../setup.sh), [setup PowerShell](../setup.ps1),
[README](../README.md) e [inventário dos links](evidence/2026-09-30-skills-audit/inventory.json).

## Aceitação da auditoria

- [x] Inventariar entrypoints, origem, links, cópias sincronizadas e arquivos históricos.
- [x] Inspecionar conteúdos e recursos que alteram a decisão, com limites declarados.
- [x] Dar destino e justificativa a todas as 128 ocorrências do escopo ativo/documental.
- [x] Conferir dependências, distribuição e risco de reinstalação nos dois setups.
- [x] Conferir cobertura final dos pareceres e preservação das mudanças preexistentes.
- [x] Aplicar a retirada adicional do Refero e verificar descoberta OMP e o fluxo de websites.

A conferência encontrou 128 ocorrências com parecer, 95 linhas na tabela da raiz,
17 na do kit e 14 na de sincronização. Os links locais foram conferidos.
Na auditoria inicial, os hashes dos entrypoints continuaram iguais e o status
preexistente dos dois repositórios foi preservado, além dos 25 checks de conteúdo/link no kit
e 466 na árvore compartilhada; diretórios não rastreados e arquivos já ausentes
têm evidência de status, não hash integral de seu conteúdo. Detalhes em
[verification.json](evidence/2026-09-30-skills-audit/verification.json).

Não houve benchmark de modelos, execução completa dos workflows, probes pagos
ou certificação nativa de outros sistemas. Testes locais de installer e contratos
preservados fazem parte da aplicação posterior; não provam ganhos de qualidade
ou equivalência entre harnesses.

As tabelas seguintes são o parecer individual. A mesma recomendação existe em
[recommendations.json](evidence/2026-09-30-skills-audit/recommendations.json),
ligada aos paths e hashes do inventário.


## Parecer das 95 skills da raiz compartilhada

### 47 para remover

| Skill | Justificativa |
|---|---|
| [ingest](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/ingest/SKILL.md) | Sem helper exclusivo; os cuidados de conversão e leitura/tabelas já estão em AGENTS e research. Preservar ferramentas de formatos sob demanda. |
| [coding-guidelines](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/coding-guidelines/SKILL.md) | Repetem tipos, nomes, organização e testes; impõem preferências universais. Não acrescentam scripts, contratos ou dados exclusivos. |
| [embedded-captions](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/embedded-captions/SKILL.md) | Legendas, transcrição e matting com render ligado a HyperFrames; não presumir portabilidade do pipeline. |
| [faceless-explainer](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/faceless-explainer/SKILL.md) | Explainers de texto produzidos pelo workflow HyperFrames. |
| [find-animation-opportunities](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/find-animation-opportunities/SKILL.md) | Três entradas para o mesmo domínio de motion. Usar o fluxo de design e visão; recuperar apenas referências que sustentem decisões concretas. |
| [find-skills](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/find-skills/SKILL.md) | Descoberta/instalação genérica já disponível por CLI; gatilhos amplos incentivam instalar novas skills para pedidos comuns. |
| [firecrawl](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/firecrawl/SKILL.md) | Roteamento genérico para Firecrawl disputa com a decisão já vigente de usar Scrapinho. Preservar CLI e rotas especializadas, sem substituir recusa por fallback. |
| [firecrawl-instruct](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/firecrawl-instruct/SKILL.md) | Sobrepõe firecrawl-interact e documenta variantes distintas do mesmo comando; conferir --help só quando a rota especializada for escolhida. |
| [firecrawl-scrape](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/firecrawl-scrape/SKILL.md) | Roteamento genérico para Firecrawl disputa com a decisão já vigente de usar Scrapinho. Preservar CLI e rotas especializadas, sem substituir recusa por fallback. |
| [firecrawl-search](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/firecrawl-search/SKILL.md) | Roteamento genérico para Firecrawl disputa com a decisão já vigente de usar Scrapinho. Preservar CLI e rotas especializadas, sem substituir recusa por fallback. |
| [general-video](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/general-video/SKILL.md) | Composição e edição customizadas explicitamente em HyperFrames. |
| [gerar-criativos](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/gerar-criativos/SKILL.md) | Pipeline Outis/Central com upload R2 e registros Supabase abandonado pelo usuário; retirar o fluxo global e preservar ativos de clientes. |
| [grill-me](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/grill-me/SKILL.md) | Entrevista e confronto com docs podem ser pedidos diretamente ao agente; retirar os dois gatilhos. Preserve decisões de domínio já escritas nos projetos. |
| [grill-with-docs](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/grill-with-docs/SKILL.md) | Entrevista e confronto com docs podem ser pedidos diretamente ao agente; retirar os dois gatilhos. Preserve decisões de domínio já escritas nos projetos. |
| [hyperframes](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes/SKILL.md) | Roteador obrigatório e instalador de workflows para o framework abandonado. |
| [hyperframes-animation](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-animation/SKILL.md) | Motion adaptado ao contrato seek-safe e à timeline HyperFrames. |
| [hyperframes-audio](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-audio/SKILL.md) | Mixagem sobre elementos/atributos de áudio específicos de HyperFrames. |
| [hyperframes-cli](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-cli/SKILL.md) | Comandos e lifecycle do CLI que deixou de ser o renderer escolhido. |
| [hyperframes-core](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-core/SKILL.md) | Contrato de composição, clips, timing e reprodução do framework. |
| [hyperframes-creative](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-creative/SKILL.md) | Direção criativa e briefs acoplados aos projetos HyperFrames. |
| [hyperframes-keyframes](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-keyframes/SKILL.md) | Animação/diagnóstico ligados ao modelo de captura e keyframes HyperFrames. |
| [hyperframes-registry](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-registry/SKILL.md) | Descoberta e instalação de blocos no registry HyperFrames. |
| [hyperframes-studio](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/hyperframes-studio/SKILL.md) | Interação com Studio e estado de um projeto HyperFrames. |
| [image-gen](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/image-gen/SKILL.md) | Wrapper que exige Codex CLI como segundo agente. Usar a capacidade de geração disponível no host ativo, reportar sua ausência e preservar regras de marca no projeto. |
| [improve](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/improve/SKILL.md) | Outro planejador de auditorias com planos e etapas próprias; pedido direto e política compartilhada cobrem o fluxo comum independentemente do harness. |
| [improve-animations](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/improve-animations/SKILL.md) | Três entradas para o mesmo domínio de motion. Usar o fluxo de design e visão; recuperar apenas referências que sustentem decisões concretas. |
| [law-irac](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/law-irac/SKILL.md) | Templates e resumos jurídicos estáticos não são uma integração local. Consultar fontes atuais quando houver trabalho jurídico; não tratar memória do modelo como lei vigente. |
| [lgpd-brasil](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/lgpd-brasil/SKILL.md) | Templates e resumos jurídicos estáticos não são uma integração local. Consultar fontes atuais quando houver trabalho jurídico; não tratar memória do modelo como lei vigente. |
| [media-use](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/media-use/SKILL.md) | Media OS do projeto HyperFrames/HeyGen; preservar assets já produzidos, sem manter a orquestração global. |
| [motion-graphics](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/motion-graphics/SKILL.md) | Unidades curtas com o contrato e renderer HyperFrames. |
| [music-to-video](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/music-to-video/SKILL.md) | Vídeo sincronizado a beats pelo pipeline HyperFrames. |
| [on-page-seo-auditor](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/on-page-seo-auditor/SKILL.md) | Sobrepõe site-audit e acrescenta pontuação, diretórios de memória e handoffs próprios; manter uma única auditoria de site. |
| [pr-to-video](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/pr-to-video/SKILL.md) | Explicação de PR com composição e render HyperFrames. |
| [product-launch-video](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/product-launch-video/SKILL.md) | Promo de produto/site pelo pipeline HyperFrames. |
| [react](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/react/SKILL.md) | Repetem tipos, nomes, organização e testes; impõem preferências universais. Não acrescentam scripts, contratos ou dados exclusivos. |
| [readme-pass](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/readme-pass/SKILL.md) | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |
| [refero-design](../../../.agents/community-skills/refero-design/skills/refero-design/SKILL.md) | Assinatura encerrada pelo usuário. Retirada do catálogo aplicada; usar as referências gratuitas do fluxo de websites. |
| [remotion-best-practices](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/remotion-best-practices/SKILL.md) | Referências do renderer Remotion, também abandonado pelo usuário. |
| [remotion-to-hyperframes](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/remotion-to-hyperframes/SKILL.md) | Port de Remotion para outro framework abandonado. |
| [review-animations](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/review-animations/SKILL.md) | Três entradas para o mesmo domínio de motion. Usar o fluxo de design e visão; recuperar apenas referências que sustentem decisões concretas. |
| [review-changes](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/review-changes/SKILL.md) | Repetem tipos, nomes, organização e testes; impõem preferências universais. Não acrescentam scripts, contratos ou dados exclusivos. |
| [slideshow](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/slideshow/SKILL.md) | Deck interativo que exige o contrato HyperFrames core; não confundir com frontend-slides. |
| [software-engineering](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/software-engineering/SKILL.md) | Repetem tipos, nomes, organização e testes; impõem preferências universais. Não acrescentam scripts, contratos ou dados exclusivos. |
| [talking-head-recut](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/talking-head-recut/SKILL.md) | Overlays de vídeo existentes renderizados pelo pipeline HyperFrames. |
| [trim-code-comments](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/trim-code-comments/SKILL.md) | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |
| [typescript](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/typescript/SKILL.md) | Repetem tipos, nomes, organização e testes; impõem preferências universais. Não acrescentam scripts, contratos ou dados exclusivos. |
| [writing](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/writing/SKILL.md) | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |

### 9 para consolidar

| Skill | Justificativa |
|---|---|
| [agents-sdk](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/agents-sdk/SKILL.md) | Preservar os contratos específicos como referências do único roteador Cloudflare. Retirar entrypoints concorrentes; conferir API e versão do projeto quando usados. |
| [cloudflare-email-service](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/cloudflare-email-service/SKILL.md) | Preservar os contratos específicos como referências do único roteador Cloudflare. Retirar entrypoints concorrentes; conferir API e versão do projeto quando usados. |
| [durable-objects](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/durable-objects/SKILL.md) | Preservar os contratos específicos como referências do único roteador Cloudflare. Retirar entrypoints concorrentes; conferir API e versão do projeto quando usados. |
| [emil-design-eng](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/emil-design-eng/SKILL.md) | Preservar critérios e pesquisas úteis no fluxo de design escolhido; remover a disputa de roteadores e os rituais globais de referência/formatação. |
| [impl](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/impl/SKILL.md) | Consolidar escopo, aceite, checks e cleanup em AGENTS.md. Preservar execução portável e mover o protocolo específico de graph para agent-graph antes de retirar o entrypoint. |
| [spec](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/spec/SKILL.md) | Consolidar política comum em AGENTS.md; preservar planejamento portável, render_visual_brief e contratos de graph como recursos opcionais. Um modo nativo de um host não basta para descartá-los. |
| [thermo-nuclear-code-quality-review](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/thermo-nuclear-code-quality-review/SKILL.md) | Transferir preferências de complexidade e economia de testes para instruções e revisão portáveis; remover outro gatilho global de revisão. |
| [web-perf](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/web-perf/SKILL.md) | Preservar diagnóstico por traces como modo de site-audit. O entrypoint atual exige Chrome DevTools MCP, ausente da configuração OMP inspecionada. |
| [workers-best-practices](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/workers-best-practices/SKILL.md) | Preservar os contratos específicos como referências do único roteador Cloudflare. Retirar entrypoints concorrentes; conferir API e versão do projeto quando usados. |

### 34 sob demanda

| Skill | Justificativa |
|---|---|
| [agent-browser](../../../.agents/skills/agent-browser/SKILL.md) | CLI real, útil em diferentes harnesses quando instalado. Selecionar pelo contrato da tarefa e contexto autenticado; não deve reivindicar toda tarefa web/desktop. |
| [computer-use](../../../.agents/skills-disabled/2026-09-30-cleanup/agents/computer-use-before-consolidation/SKILL.md) | A cópia global é o stub Orca para GUI; integração específica de desktop, fora do núcleo compartilhado. Há uma implementação diferente no kit que precisa ser reconciliada. |
| [content-strategy](../../../.agents/skills/content-strategy/SKILL.md) | Fluxo de marketing fora do núcleo de código; ativar por trabalho real, sem inferir abandono de todo marketing. |
| [docx](../../../.agents/skills/docx/SKILL.md) | Ferramentas e contratos de formatos Office têm valor próprio; um pacote por formato e sem duplicação sincronizada no mesmo host. |
| [drawio-skill](../../../.agents/community-skills/drawio-skill/skills/drawio-skill/SKILL.md) | Exportação/editabilidade .drawio e scripts de import/layout são capacidade concreta; Mermaid atende diagramas simples quando o host consegue renderizá-los. |
| [firecrawl-agent](../../../.agents/skills/firecrawl-agent/SKILL.md) | Extração autônoma com schema é capacidade distinta; só escolher sob autorização para esse serviço e consumo, não por necessidade de ler página genérica. |
| [firecrawl-crawl](../../../.agents/skills/firecrawl-crawl/SKILL.md) | Operações especializadas de descoberta/bulk que não devem ser declaradas equivalentes a Scrapinho sem paridade observada. |
| [firecrawl-developer-index](../../../.agents/skills/firecrawl-developer-index/SKILL.md) | Busca especializada em issues/PRs/docs; preservar provedor até decisão com paridade comprovada, fora do roteamento genérico. |
| [firecrawl-download](../../../.agents/skills/firecrawl-download/SKILL.md) | Operações especializadas de descoberta/bulk que não devem ser declaradas equivalentes a Scrapinho sem paridade observada. |
| [firecrawl-interact](../../../.agents/skills/firecrawl-interact/SKILL.md) | Navegador hospedado em página raspada; manter somente para essa operação escolhida, respeitando o browser e contexto disponíveis na sessão. |
| [firecrawl-map](../../../.agents/skills/firecrawl-map/SKILL.md) | Operações especializadas de descoberta/bulk que não devem ser declaradas equivalentes a Scrapinho sem paridade observada. |
| [firecrawl-monitor](../../../.agents/skills/firecrawl-monitor/SKILL.md) | Monitoramento externo recorrente e notificações são capacidade real; remover a skill não cancela monitores existentes. |
| [firecrawl-parse](../../../.agents/skills/firecrawl-parse/SKILL.md) | Conversão hospedada opcional; escolher conversor local de formato quando suficiente. Uma entrada por aquisição de documento, sem upload automático. |
| [firecrawl-research-index](../../../.agents/skills/firecrawl-research-index/SKILL.md) | Índice de literatura separado da busca web, já preservado pela política; conservar a rota inicial de papers quando disponível. |
| [frontend-slides](../../../.agents/skills/frontend-slides/SKILL.md) | Apresentações HTML sem dependências são um formato distinto de vídeo; não inferir abandono de slides ao aposentar HyperFrames. |
| [job-application-automation](../../../.agents/skills/job-application-automation/SKILL.md) | Fluxo de candidatura com contexto pessoal e limites de submissão; mover para o projeto de emprego quando usado. |
| [notebooklm](../../../.agents/skills/notebooklm/SKILL.md) | Integração real com notebooks/auth, com ambiente local volumoso. Manter só se a rotina usa NotebookLM; avaliar estado local antes de limpeza. |
| [orca-cli](../../../.agents/skills/orca-cli/SKILL.md) | APIs reais de estado/workers do Orca. Usar quando esse runtime for parte da tarefa; os fluxos comuns não devem depender dele. |
| [orchestration](../../../.agents/skills/orchestration/SKILL.md) | APIs reais de estado/workers do Orca. Usar quando esse runtime for parte da tarefa; os fluxos comuns não devem depender dele. |
| [pptx](../../../.agents/skills/pptx/SKILL.md) | Ferramentas e contratos de formatos Office têm valor próprio; um pacote por formato e sem duplicação sincronizada no mesmo host. |
| [proxy-manager](../../../.agents/skills/proxy-manager/SKILL.md) | Operação real do Webshare, já configurado localmente. Não substituir por scraping genérico nem transformar em requisito de navegação. |
| [remove-ai-marks](../skills/remove-ai-marks/SKILL.md) | Transformações de arquivos e metadados são capacidade própria; não confundir com edição de voz, e considerar achados prévios antes de uso destrutivo. |
| [rule-curator](../skills/rule-curator/SKILL.md) | Auditoria/manutenção do corpus, com ferramenta opcional de curadoria; não é requisito de cada tarefa ou um daemon. |
| [sandbox-sdk](../../../.agents/skills/sandbox-sdk/SKILL.md) | SDK específico para execução isolada; fontes do produto trazem contratos úteis, mas não integra todo trabalho Workers. |
| [scrapingdog](../skills/scrapingdog/SKILL.md) | Preservar métodos especializados sem paridade Scrapinho e helpers de custo/chave; restringir gatilho, pois genérico já foi substituído. |
| [site-audit](../../site-audit/SKILL.md) | Auditoria funcional/visual/SEO de aplicação real; preservar o que mede e adequar gates ao pedido, integrando traces de web-perf. |
| [soymi-imagegen](../../../.agents/skills/soymi-imagegen/SKILL.md) | Conhecimento de marca/print não é genérico. Colocar no projeto Soymi; abandono de gerar-criativos Outis não implica abandonar Soymi. |
| [spec-council](../../spec-council/SKILL.md) | Revisores independentes são úteis quando pedidos ou quando o risco justifica; integração opcional em qualquer harness, sem automatismo herdado de $spec. |
| [stagehand-browser](../skills/stagehand-browser/SKILL.md) | Scripts Chromium portáveis com sessão e cleanup concretos; extensão OMP opcional. Preservar suites Playwright existentes e selecionar pelo contrato da tarefa. |
| [typesafe-ai](../../../.agents/skills/typesafe-ai/SKILL.md) | Integração de outro serviço/modelo; manter para desenvolvimento explicitamente escolhido com esse produto, sob sua própria autorização de uso. |
| [unslop](../../unslop/SKILL.md) | Preferências próprias de prosa e camada pt-BR; útil quando o trabalho exige essa voz, sem ativação em respostas comuns ou implementação. |
| [vercel-react-best-practices](../../../.agents/skills/vercel-react-best-practices/SKILL.md) | Catálogo de performance específico, melhor que os cinco checklists genéricos; usar para perf React/Next com versão/ambiente do projeto, não todo código. |
| [wrangler](../../../.agents/skills/wrangler/SKILL.md) | Legado permitido pela política em projetos com Wrangler; não usar como padrão para novos projetos cf nem deletar o suporte sem mapear consumidores. |
| [x-article-publisher](../../../.agents/skills/x-article-publisher/SKILL.md) | Publicação/rich text tem mecânica real; corrigir caminhos ~/.claude para a instalação se voltar ao uso, e preservar autorização de publicação. |

### 5 para manter

| Skill | Justificativa |
|---|---|
| [cloudflare](../../../.agents/skills/cloudflare/SKILL.md) | Um roteador do stack principal com fontes atuais e contratos de bindings/runtime; consolidar referências especializadas e respeitar cf versus Wrangler legado. |
| [frontend-visual-validation](../skills/frontend-visual-validation/SKILL.md) | Contrato verificável de estados, PNGs e inspeção visual. Enxugar a matriz ao produto e evitar impor driver fora do escopo. |
| [incredibly-pretty-websites](../../incredibly-pretty-websites/SKILL.md) | Direção visual própria e recursos de implementação. Enxugar o entrypoint; usar referências gratuitas e integrar motion quando pertinente. Roteamento Refero já retirado. |
| [research](../skills/research/SKILL.md) | Integração local com Scrapinho, escopo, idempotência, paginação, proveniência e recusa; capacidade concreta além de instruções genéricas. |
| [skill-creator](../../../.agents/skills/skill-creator/SKILL.md) | Autoria e validação portáveis de skills; uma versão por capacidade, com avaliações específicas de host condicionais. Os loops claude -p não pertencem ao caminho comum. |

## Parecer das 17 skills do kit

A tabela separada registra o destino do conteúdo versionado, inclusive aliases já contados na raiz. Não são 17 remoções adicionais.

| Skill | Destino | Justificativa |
|---|---|---|
| [agent-graph](../skills/agent-graph/SKILL.md) | Sob demanda | Runtime portável de coordenação durável, com journal, ownership e recovery próprios. Retirado do core, com suporte preservado e alias global opcional; tarefas nativas de um host não foram presumidas como substituição. |
| [computer-use](../skills/computer-use/SKILL.md) | Consolidar | Diferente do stub Orca global. Escolher backend por capacidade, contrato e autorização; manter o runner Jev pago como opcional em qualquer harness. |
| [frontend-visual-validation](../skills/frontend-visual-validation/SKILL.md) | Manter | Contrato verificável de estados, PNGs e inspeção visual. Enxugar a matriz ao produto e evitar impor driver fora do escopo. |
| [grill-me](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/grill-me/SKILL.md) | Remover | Entrevista e confronto com docs podem ser pedidos diretamente ao agente; retirar os dois gatilhos. Preserve decisões de domínio já escritas nos projetos. |
| [grill-with-docs](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/grill-with-docs/SKILL.md) | Remover | Entrevista e confronto com docs podem ser pedidos diretamente ao agente; retirar os dois gatilhos. Preserve decisões de domínio já escritas nos projetos. |
| [impl](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/impl/SKILL.md) | Consolidar | Consolidar escopo, aceite, checks e cleanup em AGENTS.md. Preservar execução portável e mover o protocolo específico de graph para agent-graph antes de retirar o entrypoint. |
| [ingest](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/ingest/SKILL.md) | Remover | Sem helper exclusivo; os cuidados de conversão e leitura/tabelas já estão em AGENTS e research. Preservar ferramentas de formatos sob demanda. |
| [readme-pass](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/readme-pass/SKILL.md) | Remover | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |
| [remove-ai-marks](../skills/remove-ai-marks/SKILL.md) | Sob demanda | Transformações de arquivos e metadados são capacidade própria; não confundir com edição de voz, e considerar achados prévios antes de uso destrutivo. |
| [research](../skills/research/SKILL.md) | Manter | Integração local com Scrapinho, escopo, idempotência, paginação, proveniência e recusa; capacidade concreta além de instruções genéricas. |
| [rule-curator](../skills/rule-curator/SKILL.md) | Sob demanda | Auditoria/manutenção do corpus, com ferramenta opcional de curadoria; não é requisito de cada tarefa ou um daemon. |
| [scrapingdog](../skills/scrapingdog/SKILL.md) | Sob demanda | Preservar métodos especializados sem paridade Scrapinho e helpers de custo/chave; restringir gatilho, pois genérico já foi substituído. |
| [spec](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/spec/SKILL.md) | Consolidar | Consolidar política comum em AGENTS.md; preservar planejamento portável, render_visual_brief e contratos de graph como recursos opcionais. Um modo nativo de um host não basta para descartá-los. |
| [stagehand-browser](../skills/stagehand-browser/SKILL.md) | Sob demanda | Scripts Chromium portáveis com sessão e cleanup concretos; extensão OMP opcional. Preservar suites Playwright existentes e selecionar pelo contrato da tarefa. |
| [thermo-nuclear-code-quality-review](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/thermo-nuclear-code-quality-review/SKILL.md) | Consolidar | Transferir preferências de complexidade e economia de testes para instruções e revisão portáveis; remover outro gatilho global de revisão. |
| [trim-code-comments](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/trim-code-comments/SKILL.md) | Remover | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |
| [writing](../../../.agents/skills-disabled/2026-09-30-cleanup/kit/writing/SKILL.md) | Remover | Preferências editoriais, Git e comentários já podem ficar nas instruções existentes; nenhum helper exclusivo justifica uma skill separada. |

## Parecer das 14 cópias sincronizadas

Estas fontes são geridas pelo host de origem e não aparecem no scanner padrão OMP exercitado. As cópias de `computer-use`, `docx`, `pptx` e `skill-creator` possuem nomes também presentes em outras fontes; isso não prova duplicação simultânea no prompt do OMP.

| Skill | Destino | Justificativa |
|---|---|---|
| [built-in-browser](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/built-in-browser/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [chrome-browser](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/chrome-browser/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [computer-use](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/computer-use/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [deep-research](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/deep-research/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [docs](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/docs/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [docx](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/docx/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |
| [google-workspace](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/google-workspace/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [import-memory](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/import-memory/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [mcp-builder](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/mcp-builder/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |
| [morning](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/morning/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Manter no host com as ferramentas e contexto correspondentes; integração específica não vira requisito da base compartilhada. |
| [pdf](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/pdf/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |
| [pptx](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/pptx/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |
| [skill-creator](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/skill-creator/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |
| [xlsx](../../../.agents/skills/synced/ef6b635e-03ac-4bbc-b07a-3fa055f01541_c0c368a8-ef22-4a25-a1b9-d0c8e6a5fc26/xlsx/SKILL.md) | Host de origem | Cópia sincronizada fora do scanner agents padrão OMP exercitado. Preservar recursos portáveis; escolher uma versão por capacidade e instalar sob demanda no host ativo. |

## Coleção e fonte aninhadas

| Skill | Destino | Justificativa |
|---|---|---|
| [impeccable](../../incredibly-pretty-websites/research/sources/impeccable-v4/repository.git/plugin/skills/impeccable/SKILL.md) | Fonte arquivada | Snapshot de pesquisa dentro de outro repositório; não é skill global instalada. Arquivar fora de árvores de descoberta ampla e preservar licença se houver reaproveitamento. |
| [resume-tailoring](../../../.agents/skills/resume-tailoring/skills/resume-tailoring/SKILL.md) | Sob demanda | Resume-tailoring está aninhada e não é descoberta na raiz padrão OMP; conhecimento pessoal pode ser útil no projeto de candidatura, sem reinstalar globalmente por precaução. |

## Resíduos e arquivo histórico

| Path na árvore compartilhada | Parecer |
|---|---|
| `skills/contract-review` | Contém `skill.md` minúsculo, fora do scanner exercitado. Retirar do catálogo pretendido; não renomear e ativar só por existir. |
| `skills/copywriting` | Contém `skill.md` minúsculo, fora do scanner exercitado. Retirar do catálogo pretendido; não renomear e ativar só por existir. |
| `skills/criativos-outis-codex` | Só contém `.tmp`; preservar qualquer conteúdo de trabalho antes de retirar o resíduo. |

Os 12 entrypoints seguintes já estão fora de `skills/`. Não foram tratados como instruções ativas nem seu conteúdo foi recertificado. Manter arquivados durante a consolidação; eliminar backups redundantes somente após preservar qualquer diferença útil. Nenhum deles justifica reinstalação automática.

| Entrypoint arquivado | Estado recomendado |
|---|---|
| `skills-backup/drawio-skill-local-20260812/SKILL.md` | Continuar arquivado |
| `skills-backup/grill-me.bak-20260807/SKILL.md` | Continuar arquivado |
| `skills-backup/grill-with-docs.bak-20260807/SKILL.md` | Continuar arquivado |
| `skills-backup/refero-design-npx-20260812/SKILL.md` | Continuar arquivado |
| `skills-backup/ux-audit-retired-20260807/SKILL.md` | Continuar arquivado |
| `skills-backup/writing.bak-20260807/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/humanizer.shared/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/llm-council.shared/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/ralph.shared/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/react-best-practices.duplicate-codex/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/react-best-practices.duplicate-shared/SKILL.md` | Continuar arquivado |
| `skills-disabled/2026-08-26/thermo-nuclear-code-quality-review.bak-20260812/SKILL.md` | Continuar arquivado |
