# Reauditoria Sol do harness `my-llm-kit`

Data de acesso: 2026-08-10.

## Pergunta

Quais mudanças no harness são justificadas diretamente pelas fontes primárias, e quais recomendações da auditoria anterior acrescentariam complexidade sem evidência suficiente?

## Critério

Uma mudança entra no caminho padrão apenas quando a fonte mede um mecanismo compatível e o repositório possui uma lacuna observável correspondente. Uma ideia relacionada, mas não testada nas mesmas condições, permanece opcional ou sai do plano.

## Falsificador

Esta revisão falha se usar um benchmark para prescrever uma automação que o benchmark não avaliou, tratar ausência de evidência como refutação ou remover uma proteção sem preservar seu comportamento verificável.

## Veredito

O harness deve ficar menor no caminho padrão. O fluxo defensável é: localizar o escopo, editar, executar um check externo e registrar o resultado. Planejamento, council, subagentes e esforço extra entram quando dependências, risco ou falha observada justificarem o custo.

A mudança para Sol não altera a evidência dos papers. Ela mudou o julgamento sobre a distância entre os papers e as automações propostas.

## Correções da auditoria anterior

### Não adicionar contagem bruta de linhas como métrica de qualidade

SlopCodeBench mede verbosidade com regras estruturais e duplicação. Mede erosão pela concentração de complexidade em funções já complexas. O paper não valida arquivos alterados ou linhas adicionadas como proxy universal de saúde. Portanto, adicionar esses campos ao estado seria uma extrapolação. Fonte primária: [SlopCodeBench, arXiv:2603.24755](https://arxiv.org/html/2603.24755v2#S2.SS3), acessada em 2026-08-10.

O que permanece útil é registrar fatos do próprio check, como resultado, duração e tentativas. Eles descrevem a trajetória sem fingir medir manutenibilidade.

### Não exigir mutação manual em toda lógica

Agentless filtra testes de reprodução executando-os no repositório original e usa validação externa para selecionar patches. Isso apoia um teste de regressão que distingue o comportamento defeituoso do corrigido. Não apoia quebrar transitoriamente toda implementação nova. Fonte primária: [Agentless, arXiv:2407.01489](https://arxiv.org/html/2407.01489v2#S3.SS3), acessada em 2026-08-10.

A regra correta é mais estreita: bug fixes precisam de regressão que falhe no caso conhecido; checks novos e suspeitos podem receber controle negativo. A mutação manual não deve ser custo obrigatório por task.

### Não expandir o compilador de aprendizado

Nenhum paper consultado avalia a promoção automática de regras ou skills depois de recorrências locais. Reflexion apoia usar feedback na tentativa seguinte, mas não prova que texto promovido vira uma regra permanente correta. A crítica à autocorreção intrínseca reforça que uma regra textual não substitui evidência externa. Fontes primárias: [Reflexion, arXiv:2303.11366](https://arxiv.org/abs/2303.11366) e [Large Language Models Cannot Self-Correct Reasoning Yet, arXiv:2310.01798](https://arxiv.org/abs/2310.01798), acessadas em 2026-08-10.

O compilador auditado também promovia uma recorrência depois de duas mudanças, enquanto a regra de pesquisa deste repositório classifica menos de cinco casos como amostra fraca. O conflito é observável no [`learning.py` anterior](https://github.com/badmuriss/my-llm-kit/blob/86a731fdfb31f2b71b9840efdeed6f2147041ea8/skills/impl/scripts/learning.py) e em [AGENTS.md](../AGENTS.md), acessados em 2026-08-10. A decisão conservadora é retirar esse compilador do caminho padrão, não enriquecê-lo com mais schema.

### Corrigir o registro sobre testes

O snapshot atual realmente não contém a suíte do harness. Porém, ela existia e foi removida pelo commit [`86a731f`](https://github.com/badmuriss/my-llm-kit/commit/86a731fdfb31f2b71b9840efdeed6f2147041ea8), acessado em 2026-08-10. O mesmo commit alterou roteamento e setup. A auditoria anterior errou ao tratar a ausência como uma lacuna histórica em vez de uma regressão recente. A implementação deve restaurar cobertura comportamental proporcional ao fluxo mantido.

## O que remover do caminho padrão

### Council em duas fases

O council atual roda antes e depois do grilling por padrão. A literatura diverge: debate pode melhorar algumas tarefas, mas também pode induzir conformidade, consenso prematuro e troca de resposta correta por incorreta. Fontes primárias: [Multiagent Debate, arXiv:2305.14325](https://arxiv.org/abs/2305.14325), [Talk Isn't Always Cheap, arXiv:2509.05396](https://arxiv.org/abs/2509.05396) e [When and Why Does Multi-Agent Debate Fail, arXiv:2510.20963](https://arxiv.org/abs/2510.20963), acessadas em 2026-08-10.

Decisão: council volta a ser `--council`, limitado a uma revisão do maior risco. Ele continua consultivo. Um teste ou artefato externo decide o aceite.

### Delegação obrigatória

Agentless demonstra que um fluxo fixo de localização, reparo e validação pode competir com scaffolding autônomo complexo no benchmark estudado. O próprio paper também reconhece vantagem de ferramentas agentic em problemas sem pista de localização. Fonte primária: [Agentless, arXiv:2407.01489](https://arxiv.org/html/2407.01489v2), acessada em 2026-08-10.

Decisão: uma task localizada pode ser executada no contexto atual. Subagentes ficam para paralelismo real, isolamento ou julgamento independente. O harness não deve pagar coordenação apenas para obedecer ao ritual.

### Aprendizado e geração de skills em todo run

O caminho atual exporta um segundo registro, compila quatro artefatos e pode gerar skills locais. Isso não possui validação empírica na pesquisa consultada. SlopCodeBench mostra ainda que instruções de qualidade melhoram o início sem impedir degradação posterior. Fonte primária: [SlopCodeBench, arXiv:2603.24755](https://arxiv.org/html/2603.24755v2#S3.SS4), acessada em 2026-08-10.

Decisão: preservar estado retomável e evidância da task. Remover exportação, promoção e geração automática do fluxo `impl`. Uma regra permanente continua exigindo revisão humana e um gate executável quando possível.

## O que implementar

1. Ler `Check:` de cada task e rejeitar task sem contrato de validação ou marcador explícito de evidência ausente.
2. Executar o check pelo gerenciador de estado e persistir comando, resultado, código de saída, duração e número de tentativas.
3. Impedir `pass` quando o check não foi observado com sucesso.
4. Manter `unobserved` para `Check: missing validation evidence`.
5. Restaurar testes comportamentais para inicialização, retomada, cleanup, checks e aceite.
6. Tornar council e múltiplos reasoners opcionais, acionados por risco ou pedido explícito.
7. Usar esforço adaptativo: começar no menor nível compatível com a task e escalar depois de falha observada, ambiguidade ou alto impacto. Não fixar `xhigh` como etapa universal. Fontes primárias: [OptimalThinkingBench, arXiv:2508.13141](https://arxiv.org/abs/2508.13141) e [When More Thinking Hurts, arXiv:2604.10739](https://arxiv.org/abs/2604.10739), acessadas em 2026-08-10.
8. Fazer preflight real do `paper-search`: executável, versão e consulta mínima. Falha deve declarar o fallback, não fingir que a pesquisa está operacional.
9. Incorporar do `unlazy` apenas gates de aceite, verificação externa, sweep completo quando o escopo pede totalidade, uma linha de ataque por vez e proibição de placeholders. Não instalar Depth Tree, `Wait` automático ou esforço multiplicativo como default. Fonte do mecanismo: [unlazy SKILL.md](https://raw.githubusercontent.com/Leonxlnx/unlazy/main/SKILL.md), acessada em 2026-08-10. Limites: [s1, arXiv:2501.19393](https://arxiv.org/abs/2501.19393), [OptimalThinkingBench](https://arxiv.org/abs/2508.13141) e [When More Thinking Hurts](https://arxiv.org/abs/2604.10739), acessadas em 2026-08-10.

## O que permanece aberto

- Nenhuma fonte avaliou o `my-llm-kit` diretamente.
- A vantagem líquida do council local ainda precisa de uma avaliação comparável com e sem council.
- Os rótulos Luna, Terra e Sol e seus níveis de esforço são política operacional, não resultado científico.
- A Depth Tree do `unlazy` continua sem validação como política de coding agent.
- Métricas estruturais de trajetória exigiriam ferramentas por linguagem. Não devem entrar como um score universal sem validação local.

## Trilha e fallback da reauditoria

- A CLI `paper-search` foi tentada primeiro e não retornou resultados, apenas avisos sobre fontes opcionais sem configuração.
- O ScrapingDog foi usado porque `SCRAPINGDOG_API_KEY` estava disponível. O endpoint Google Scholar encontrou URLs primárias, mas seu payload não trouxe títulos no campo esperado pelo parser usado nesta sessão.
- A API oficial do arXiv foi tentada para resolver os metadados e respondeu `Rate exceeded`.
- Firecrawl foi usado como fallback explícito para ler as páginas primárias já identificadas e os arquivos do `unlazy`.

## Trial by fire

As conclusões sobre planejamento, validação, debate, overthinking e degradação vieram de papers primários. As conclusões sobre o harness vieram do repositório e do histórico Git. A eficácia da Depth Tree vem apenas do autor do `unlazy` e não foi tratada como evidência independente. Valores de preço, disponibilidade de modelos e compatibilidade do host não sustentam nenhuma regra científica nesta revisão e precisam de nova checagem quando usados operacionalmente.
