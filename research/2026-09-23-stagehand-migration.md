# Migração de automação própria para Stagehand

Data de verificação: 2026-09-23.

## Decisão e entrega

O kit passa a oferecer Stagehand 4.1.0 local para automação determinística de
Chromium, com uma extensão OMP e a skill `stagehand-browser`. Jev continua
preferencial nos objetivos que atende bem, quando disponível e autorizado.
Stagehand não usa Jev internamente: os dois podem atuar sequencialmente no mesmo
Chrome isolado, com verificação independente do resultado.

A integração usa o modelo da sessão OMP para decidir ações e as APIs determinísticas
do SDK para executá-las. Não encaminha tokens OAuth, não cria uma ponte de inferência,
não exige Browserbase e não habilita `act`, `observe` ou `extract` com IA. A execução
OMP foi comprovada com o modelo Astra autorizado durante a tarefa. Os arquivos privados
`config.yml` e `models.yml` não foram alterados por esta migração.

## Inventário e limites de propriedade

| Caminho ou componente | Situação | Ação |
| --- | --- | --- |
| `skills/frontend-visual-validation` | Orientação própria de captura, sem suíte Playwright própria | Stagehand para novas capturas Chromium; conservar os contratos de suítes existentes |
| `skills/impl/SKILL.md` e `skills/computer-use/SKILL.md` | Roteamento próprio | Jev autorizado para objetivos adequados; Stagehand para verificações determinísticas; Orca para desktop |
| `setup.sh` e `setup.ps1` | Instalação própria | Integração apenas em `--full` / `-Full`, ou instalação avulsa explícita |
| `skills/stagehand-browser/tools` | Novo runtime próprio | SDK fixado, sessão com propriedade explícita, extensão OMP, instalador e smoke real |
| Referência Playwright e matriz de plataformas | Contratos de consumidores e cobertura WebKit | Mantidos; dimensões móveis no Chromium não equivalem a WebKit |
| Browser Harness / Jev Ultrafast | Backend externo distinto de Python browser-use | Preservado; composição no mesmo Chrome isolado exercitada |
| OMP browser/Puppeteer e navegador embutido Orca | Implementações do host | Não alterados nem apresentados como migração do kit |
| `agent-browser` e `job-application-automation` instalados | Skills externas | Não reescritas; menções a browser-use não tornam seu runtime propriedade do kit |
| Puppeteer/Mermaid em `skills/spec/tools` | Renderização de diagramas | Fora do cutover de automação de navegador |
| Nomes Playwright no resource guard | Reconhecimento de processos de consumidores | Mantidos; não representam dependência a remover |

Não havia uma suíte Playwright própria para converter. A mudança implementa o runtime
que faltava e migra os pontos próprios de instalação e invocação. Não simula equivalência
com Playwright Test, suas fixtures, auto-wait, assertions visuais ou engines.

## Instalação e operação

- Node >=22.18, npm e Chrome já instalado. SDK e lockfile pertencem à skill instalada,
  não ao projeto consumidor. Nenhum download de navegador ou upgrade global de OMP.
- `tools/install.mjs` admite `--home` e `--dry-run`, preserva uma skill/extensão alheia
  e não escreve modelos, credenciais ou MCPs. O instalador completo não foi executado
  contra o HOME real como teste.
- A instalação avulsa foi aplicada ao ambiente local após a prova em HOME temporário.
  O loader fica em `~/.omp/agent/extensions/stagehand-browser.mjs`.
- Reiniciar a sessão ou recarregar extensões disponibiliza `stagehand` com operações
  `run`, `snapshot`, `screenshot` e `close`. A aba permanece entre chamadas; variáveis
  JavaScript locais não permanecem. Código de `run` possui privilégios Node, não sandbox.
- Perfil temporário isolado por padrão. `STAGEHAND_USER_DATA_DIR` aceita somente um
  perfil dedicado, autorizado e não aberto por outro navegador.
- A configuração de traces aponta para loopback: a versão fixada não oferece um
  campo de desativação. Não há coletor provisionado nem exportação externa configurada.

### CDP e persistência

A conexão a um navegador emprestado está deliberadamente desabilitada. No código
publicado da versão 4.1.0, `browser.close()` envia `Browser.close` também quando a
origem é `localBrowser.connect()`. A prova de reconexão também excedeu o timeout de
60 segundos. `STAGEHAND_CDP_URL` produz erro explícito; o kit não encerra o Chrome
pessoal nem abre outra sessão silenciosamente para declarar sucesso.

No navegador pertencente ao kit, a limpeza imediata do SDK perdeu um cookie sintético
persistente recém-criado. O runtime envia `Browser.close`, espera a saída do PID obtido
por CDP e só depois libera o SDK. A regressão confirmou cookie e localStorage depois
de reabrir o mesmo perfil dedicado. Isso não prova todos os fluxos OAuth ou logins reais.

## Provas executadas

| Prova | Resultado observado |
| --- | --- |
| `node skills/stagehand-browser/tools/smoke.mjs .visual-evidence/stagehand-browser` | Chrome real: navegação, preenchimento, seleção, clique, gravação no servidor, extração DOM, snapshot e PNG |
| Elemento ausente | `waitForSelector` e clique falharam; não houve falso sucesso |
| Perfil dedicado | Cookie sintético persistente e localStorage mantidos entre duas aberturas |
| OMP real com a extensão | `stagehand.run` alterou o título via formulário para `OMP_STAGEHAND_OK`; `stagehand.close` liberou os recursos, ambos sem erro |
| Jev + Stagehand no mesmo navegador | Jev completou três ações; Stagehand verificou a aba antes de seu fechamento, extraiu `Ana` / `Pro` e confirmou exatamente uma gravação no servidor |
| Instalador avulso em HOME temporário e cwd alheio | Dry-run sem mutação, instalação repetida, configuração privada sentinela preservada e extensão alheia recusada |
| `python3 -m unittest scripts.tests.test_installers -v` | Seis testes existentes passaram |
| `bash -n setup.sh` | Sintaxe Unix válida |
| Validador `skill-creator` | As quatro skills alteradas passaram na validação de frontmatter |
| `bash setup.sh --full --dry-run`, em HOME temporário | Retornou zero e incluiu Stagehand; outros passos criaram `.claude`, `.claude.json` e `.npm` no HOME temporário, portanto o dry-run completo não foi considerado livre de mutações |

A prova conjunta usou o Jev existente `typesafe/jev-1.13` via OpenRouter, explicitamente
autorizado. Stagehand não fez uma chamada adicional de inferência. O `verified: false`
do runner Jev permaneceu intacto: a prova veio das assertions independentes de Stagehand,
não de reclassificar a declaração do modelo.

Browser Harness captura defaults na importação. Na composição, definir `BU_NAME`
exclusivo e `BU_CDP_WS` privado antes de importar o módulo. Verificar a aba exata
antes da saída do runner Jev, pois essa saída fecha a aba. Encerrar o daemon exclusivo
antes de fechar o navegador pertencente ao runtime. Não repetir submissões para verificar
um resultado que já existe.

### Evidência visual local

Arquivos em `.visual-evidence/stagehand-browser/`, ignorados pelo Git:

- `saved.png`: 1366 × 768, formulário preenchido e confirmação verde
  `Saved: Stagehand test / Pro`, sem sobreposição ou corte no conteúdo inspecionado.
- `hybrid.png`: 1280 × 713, campos `Ana` / `Pro` e confirmação verde
  `Saved: Ana / Pro`, sem sobreposição ou corte no conteúdo inspecionado.
- `result.json`, `hybrid.json`, `omp.json` e `review.json`: resultados observados,
  hashes dos PNGs e revisão visual. Dados exclusivamente sintéticos.

São fixtures da integração no Linux/Chrome, não uma validação responsiva de produto.
Windows nativo, macOS, Firefox, WebKit e login de produção permanecem não verificados;
Firefox e WebKit não são suportados por este runtime. A lógica PowerShell foi alinhada,
mas não foi executada em Windows.

## Fontes primárias

Consultadas em 2026-09-23:

- [SDK publicado 4.1.0 no npm](https://www.npmjs.com/package/@browserbasehq/stagehand/v/4.1.0), incluindo declarações de tipos, dependências e implementação distribuída.
- [Migração Playwright](https://docs.stagehand.dev/v4/migrations/playwright).
- [Configuração de navegador](https://docs.stagehand.dev/v4/configuration/browser).
- [Configuração de modelos](https://docs.stagehand.dev/v4/configuration/models).
- [Integração Pi oficial](https://docs.stagehand.dev/v4/integrations/pi).
- [SDK TypeScript oficial](https://github.com/browserbase/stagehand/tree/main/packages/sdk-ts).

A integração Pi documentada não estava disponível como pacote npm instalável e não
foi presumida compatível com OMP. A extensão usa a API real de registro do host, testada
em execução. A documentação descreve timeout de `waitForSelector` como retorno booleano;
a versão publicada lançou erro na prova. O código trata falha como falha, sem enfraquecer
a verificação para acompanhar essa descrição.
