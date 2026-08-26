# Research finding: política adaptativa de processo para my-llm-kit

## Protocol

- Question: Que política adaptativa, baseada em evidência, deve escolher entre execução direta, loop verificado de um agente, spec leve e grafo multiagente, mantendo o processo proporcional ao risco e ao paralelismo real?
- Decision criterion: Adotar o menor modo que preserve validação proporcional ao risco, permita revisão quando a evidência muda e só acrescente coordenação quando pacotes independentes, checks objetivos e ganho esperado de tempo justificarem seu custo.
- Falsifier: A recomendação falha se evidência reproduzível mostrar que impor spec ou grafo por padrão melhora resultado, custo ou tempo para trabalho pequeno, reversível e coeso, ou se uma política de escalonamento por gates aumentar falhas não detectadas.
- Risk: material
- Budget: 75 credits
- Credits used: 0

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Literatura sobre agentes e engenharia de software | ScrapingDog | `GET /google_scholar` | Tentativa concluída com três consultas; devolveu URLs de arXiv/ACM, mas os campos de título vieram inutilizáveis para triagem. | 0 | O catálogo MCP desta sessão não expôs `google_scholar`; o fallback HTTP documentado foi usado. A resposta não bastou para identificar fontes sem abrir os originais. |
| Artigos, posts oficiais e fontes primárias | Web público | abertura direta de URLs oficiais, arXiv e repositórios | Concluído; cada fonte aceita foi aberta. | 0 | Nenhum. |
| Fontes oficiais de produto | OpenAI | preflight de `https://developers.openai.com/llms.txt`, depois guia oficial de prompt caching | O índice estruturado existe, mas não responde sozinho à questão; o guia foi aberto. | 0 | Índice é descoberta, não evidência. |
| Evidência de confiabilidade de sistemas | Web público | abertura direta de NIST e arXiv | Concluído. | 0 | Nenhum. |

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| A afirmação de que modelos de fronteira recebem pouco ou nenhum ganho de harness não tem dataset público, protocolo, repetições e variância suficientes neste material. | https://arxiv.org/abs/2604.25850 | 2026-08-21 | None | yes | partial | yes | yes | rejected |
| Um harness alterado melhorou resultados em três famílias de modelo no estudo AHE; isso contradiz a formulação “pouco ou nenhum benefício” como regra geral. | https://arxiv.org/abs/2604.25850 | 2026-08-21 | None | yes | yes | yes | unknown | limited |
| Uma evidência recente diz que modelos-alvo mais fracos receberam os maiores ganhos de scaffolding, mas a tarefa foi Theory of Mind, não engenharia de software. | https://arxiv.org/abs/2608.12307 | 2026-08-21 | None | yes | yes | yes | unknown | limited |
| O custo pode mudar materialmente quando o transporte preserva um prefixo estável e elegível ao cache; conteúdo, ordem e configurações devem ser idênticos para reutilização. | https://developers.openai.com/api/docs/guides/prompt-caching | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| A fórmula de produto para etapas vale para componentes independentes que todos precisam sobreviver; não modela dependência, redundância, verificação nem recuperação. | https://www.itl.nist.gov/div898/handbook/apr/section1/apr122.htm | 2026-08-21 | None | yes | yes | yes | yes | accepted |
| Cognition publicou a crítica de que ações carregam decisões implícitas e que escritores paralelos podem divergir por contexto e pressupostos não compartilhados. | https://cognition.com/blog/dont-build-multi-agents | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| A atualização posterior de Cognition limita, em vez de repetir, essa tese: múltiplos agentes funcionam melhor quando a escrita continua serial e os demais acrescentam inteligência. | https://cognition.com/blog/multi-agents-working | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| Anthropic relatou cerca de 15x tokens de chat para sistemas multiagente e disse que pesquisa com paralelismo amplo encaixa melhor que a maior parte de coding, que tem mais dependências. | https://www.anthropic.com/engineering/multi-agent-research-system | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| A alegação de que a maior parte dos ganhos da arquitetura da Anthropic veio de gasto extra de tokens não é suportada pelo post; ele não apresenta uma ablação causal de arquitetura versus orçamento. | https://www.anthropic.com/engineering/multi-agent-research-system | 2026-08-21 | None | yes | yes | yes | unknown | rejected |
| MAP entrevistou 20 casos e filtrou a pesquisa para 86 sistemas em produção ou piloto, dentro de 26 domínios reportados no levantamento. | https://arxiv.org/html/2512.04123v4 | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| Em MAP, 68% dos sistemas implantados executavam no máximo 10 passos antes de intervenção humana; a amostra não é censo global e foi coletada de abril a novembro de 2025. | https://arxiv.org/html/2512.04123v4 | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| Thoughtworks colocou SDD em Assess em novembro de 2025 e advertiu que workflows elaborados, opinionated e regras detalhadas podem não escalar. | https://www.thoughtworks.com/en-in/radar/techniques/spec-driven-development | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| Thoughtworks também recomenda reavaliar o harness ao mudar de modelo e manter um humano no loop para evitar context rot e feedback ruidoso. | https://www.thoughtworks.com/en-au/radar/techniques/feedback-flywheel | 2026-08-21 | None | yes | yes | yes | unknown | accepted |
| Gartner declarou, em comunicado de 25 de junho de 2025, que mais de 40% dos projetos de IA agêntica seriam cancelados até o fim de 2027 e estimou cerca de 130 fornecedores substantivos. | https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027 | 2026-08-21 | None | yes | yes | no | unknown | volatile |
| Um pipeline simples, interpretável e com validação pode competir bem em software engineering; Agentless superou os agentes open-source comparados no SWE-bench Lite de sua época. | https://arxiv.org/abs/2407.01489 | 2026-08-21 | None | yes | yes | partial | unknown | limited |
| Em geração de README, um estudo comparativo recente achou qualidade lexical comparável com agente único, menor consumo e maior velocidade, mas maior consistência estrutural com MAS. | https://arxiv.org/abs/2606.30524 | 2026-08-21 | None | yes | yes | yes | unknown | limited |
| Verificar pós-condição antes de retry é mais defensável que retry cego para ações externas ambíguas; a evidência citada é um simulador com dois fluxos. | https://arxiv.org/abs/2608.02645 | 2026-08-21 | None | yes | yes | yes | unknown | limited |

## Findings

### Veredito sobre o ensaio

O ensaio acerta ao rejeitar o grafo, o papel de agente e a spec como respostas automáticas. A evidência mais útil é condicional. A Anthropic encontrou bom encaixe para pesquisa com largura, contexto que excede uma janela e muitas ferramentas, mas disse que boa parte de coding tem menos trabalho realmente paralelizável e mais dependências. O post registra aproximadamente 15x o consumo de tokens de chat para sistemas multiagente, acessado 2026-08-21: https://www.anthropic.com/engineering/multi-agent-research-system.

A crítica da Cognition também é concreta: agentes que escrevem em paralelo podem tomar decisões de estilo, bordas e arquitetura que não foram explicitadas ao colega. O argumento é um relato de engenharia, não um experimento controlado, mas é coerente com o risco operacional de contexto fragmentado. A própria Cognition atualizou a posição em 2026: há valor em agentes adicionais como pesquisa, revisão e escalonamento, desde que a escrita permaneça em um fluxo único. Fontes primárias, acessadas em 2026-08-21: https://cognition.com/blog/dont-build-multi-agents e https://cognition.com/blog/multi-agents-working.

O ensaio exagera quando transforma essas observações em lei universal. Não há, entre as fontes públicas abertas, um benchmark geral que isole modelo, harness, ferramentas, orçamento, política de cache, tarefa e métrica de manutenção. O estudo AHE relata ganhos do harness em famílias alternativas de modelos, mas é preprint e o seu ambiente não prova transferência para este repositório. O estudo AI4AI indica que modelos mais fracos receberam ganhos maiores, mas mede Theory of Mind, não coding. Ambos derrubam a certeza da tese, mas não estabelecem uma curva universal de “ganho por força do modelo”. Fontes primárias, acessadas em 2026-08-21: https://arxiv.org/abs/2604.25850 e https://arxiv.org/abs/2608.12307.

A alegação sobre custo está correta, porém precisa da condição técnica. O cache não é uma propriedade abstrata do “harness”. Para o provedor OpenAI, a reutilização depende do prefixo renderizado estável, incluindo conteúdo, ordem e configurações pertinentes. Assim, fan-out que replica contexto pode perder economia de cache, enquanto um loop que preserva instruções e contexto estável pode ganhá-la. Isso deve ser medido por `cached_tokens`, `cache_write_tokens` e custo real por resultado, não inferido da topologia. Fonte oficial, acessada em 2026-08-21: https://developers.openai.com/api/docs/guides/prompt-caching.

Os números atribuídos a MAP estão substancialmente corretos, com uma correção de escopo. A versão de 4 de junho de 2026 declara 20 estudos de caso, 306 praticantes consultados e filtro de 86 sistemas em produção ou piloto; reporta 68% com até 10 passos antes de intervenção humana. Os 26 domínios pertencem ao levantamento, e não tornam os 86 um censo aleatório mundial. O próprio trabalho descreve viés de participação, concentração geográfica e janela temporal de abril a novembro de 2025. É evidência forte para preferir controles e supervisão, mas não para fixar “10 passos” como limite do kit. Fonte primária, acessado 2026-08-21: https://arxiv.org/html/2512.04123v4.

Thoughtworks sustenta a preocupação com cerimônia. Seu Radar de novembro de 2025 colocou SDD em Assess e relatou que processos longos e opinionated variam muito com tamanho e tipo de tarefa. O texto posterior afirma que drift de spec é difícil de evitar e que CI/CD determinístico ainda protege qualidade. Ele também descreve a questão “spec ou código como verdade” como aberta. Isto favorece specs curtas, revogáveis e ligadas a checks, não uma documentação eterna. Fontes oficiais, acessadas em 2026-08-21: https://www.thoughtworks.com/en-in/radar/techniques/spec-driven-development e https://www.thoughtworks.com/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-ai-assisted-engineering-practices.

Gartner realmente publicou os dois números citados em comunicado de 25 de junho de 2025. Eles são previsão e estimativa de analista, não resultado experimental nem métrica de qualidade de grafos. São voláteis e não devem virar threshold de produto. Fonte oficial, acessada em 2026-08-21: https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027.

### O que a comparação empírica permite, e não permite, concluir

Não há evidência pública suficiente para coroar agente único ou multiagente em todo software engineering. Agentless mostrou que um processo de localização, reparo e validação pode superar agentes open-source então comparados no SWE-bench Lite, mas o resultado é de 2024 e é específico ao benchmark e às baselines daquele estudo. Fonte primária, acessada em 2026-08-21: https://arxiv.org/abs/2407.01489.

Há também resultado em sentido oposto, mas estreito. O preprint de README comparou pipeline de agente único, MAS especializado e plano guiado pelo desenvolvedor. No seu conjunto de geração de documentação, agente único reduziu consumo de tokens em 86% e operou duas vezes mais rápido, enquanto MAS atingiu 98% de consistência estrutural. Isto é uma **amostra fraca** de uma família de tarefa, não uma prescrição para alteração de código. Fonte primária, acessado 2026-08-21: https://arxiv.org/abs/2606.30524.

O sinal mais consistente não é “mais agentes” ou “menos agentes”. É: manter o estado que decide o produto coeso, introduzir paralelismo onde o trabalho é leitura ou produção isolada, e usar feedback verificável para corrigir a trajetória. A literatura recente sobre chamadas não atômicas reforça que retry sem verificar o estado externo pode duplicar efeitos. O experimento é limitado a simulador e dois fluxos, portanto a recomendação é de engenharia defensiva, não de eficácia geral. Fonte primária, acessada em 2026-08-21: https://arxiv.org/abs/2608.02645.

### Confiabilidade: por que `0.9^10` não prova a taxa de um sistema de dez agentes

`0.9^10 = 0.3486784401` é aritmética. Ele representa um sistema em série com dez eventos de sucesso, cada um com probabilidade 0,9, independentes, e onde qualquer falha encerra o resultado. O NIST explicita que multiplicar confiabilidades pressupõe componentes independentes e que todos precisem sobreviver. Fonte oficial, acessada em 2026-08-21: https://www.itl.nist.gov/div898/handbook/apr/section1/apr122.htm.

Um workflow real viola essas premissas de várias maneiras: passos podem compartilhar o mesmo erro de interpretação, algumas falhas podem ser detectadas por teste e corrigidas, tarefas podem ser redundantes, e uma integração pode falhar mesmo quando cada filho “terminou”. Portanto o número não estima taxa de sucesso de agentes. A modelagem correta começa com dependências, pontos de verificação, caminhos de retry, custo de erro e observabilidade. Para este kit, o controle prático é registrar a evidência por pacote e checar pós-condições antes de retry de ações externas, não multiplicar probabilidades imaginadas.

### Política proposta: classificador observável

Classifique a tarefa antes de escolher processo. Não some um “score mágico”; marque os sinais abaixo e registre os que mudarem durante o trabalho.

| Entrada observável | Pergunta operacional | Efeito na escolha |
|---|---|---|
| Tamanho e coesão | A alteração cabe em um objetivo, uma área coesa e uma reversão simples? | Favorece execução direta ou loop único. |
| Incerteza arquitetural | Ainda há decisão de interface, esquema, limite de domínio ou comportamento do usuário? | Pede spec leve antes de escrever. |
| Reversibilidade e blast radius | Uma falha afeta dados, credenciais, infraestrutura, contrato público ou muitos módulos? | Pede check mais forte, aprovação humana quando necessária e, em geral, spec. |
| Força do oráculo | Existe typecheck, teste, lint, contrato, screenshot ou pós-condição capaz de refutar o resultado? | Sem oráculo, não aumente autonomia; reduza escopo ou peça confirmação. |
| Paralelismo real | Há pelo menos dois pacotes que podem avançar sem decisão compartilhada, sem arquivo concorrente e sem integrar escolhas implícitas? | Só então o grafo se torna candidato. |
| Acoplamento de escrita e estado | Duas pessoas precisariam combinar estilo, abstração, interface ou estado mutável durante a execução? | Serialize sob um único escritor. |
| Contexto | O contexto necessário excede a janela ou se torna caro demais para um agente conservar? | Permite subagente de leitura, resumo verificável ou investigação, não autoriza escritores paralelos por si só. |
| Duração e valor temporal | A economia de parede de executar pacotes independentes supera briefing, integração, revisão e cleanup? | Se não superar, mantenha um agente. |
| Credenciais, efeitos externos e execução sem supervisão | A ação é irreversível, cobra dinheiro, publica, deleta ou atua sem humano? | Exige permissões explícitas, idempotência, pós-condição e parada segura. |

O classificador é um gate de decisão, não uma estimativa de probabilidade. Ele deve manter um registro breve com: fatos observados, modo escolhido, check planejado, limites de autonomia e condição de escalonamento ou redução. Esses campos são suficientes para auditoria e para aprender depois sem congelar um plano grande cedo demais.

### Escada mínima de modos

| Modo | Escolher quando | Artefato mínimo | Não fazer | Escalonar quando |
|---|---|---|---|---|
| 0. Execução direta | Mudança pequena, conhecida, reversível, coesa e com validação rápida. | Objetivo de uma frase e resultado do menor check pertinente. | Não criar spec, grafo, papéis ou estado durável só para satisfazer template. | Surge incerteza de arquitetura, risco maior ou um segundo pacote realmente independente. |
| 1. Loop verificado de um agente | A tarefa exige investigar, editar, testar, depurar ou iterar, mas continua coesa e tem um escritor. | Hipótese, limites, check por tentativa e breve registro de decisão mudada. | Não trocar de agente para cada papel nem paralelizar escrita. | O escopo fica interdependente demais para a memória local ou um contrato precisa de revisão antes da implementação. |
| 2. Spec leve | Há decisão arquitetural, contrato, migração, alto blast radius, requisito ambíguo ou validação não óbvia. | Uma página: decisão, alternativas rejeitadas, invariantes, checks, risco, responsável por aprovar e regra de emenda. | Não decompor automaticamente em plano longo, OpenSpec completo ou grafo. | Depois de resolver a decisão, aparecem pacotes independentes com ownership e checks próprios. |
| 3. Grafo multiagente | Todos os gates passam: pacotes independentes, paths ou ambientes isolados, retornos verificáveis, integração definida, custo de coordenação compensado e lifecycle/cleanup observáveis. | Contrato curto por pacote, dependências reais, ownership de path, check independente, orçamento e receipt de cleanup. | Não criar worker para um papel ornamental, nem usar vários escritores sobre decisões acopladas. | Nunca por tamanho aparente sozinho; só por evidência de paralelismo e valor. |

“Pelo menos dois pacotes” no último modo não é um threshold empírico de produtividade. É apenas a condição lógica para haver paralelismo. Não há número universal de arquivos, tokens, minutos, agentes ou passos que determine cada modo.

### Emergência e redução de complexidade

O plano é uma hipótese operacional. Cada descoberta que altere escopo, interface, risco, check ou decomposição deve gerar uma emenda curta: o que mudou, a evidência, o impacto e o novo check. Código executado, testes, typechecks, logs de runtime e pós-condições têm precedência sobre prose anterior. Se a evidência contradiz a spec, corrija ou aposente a spec antes de continuar; não force a realidade a caber no documento.

O coordenador deve reduzir o modo quando a descoberta eliminar pacotes, revelar acoplamento de decisão, tornar a integração mais cara que a economia de parede ou deixar um check incapaz de aceitar com segurança. Reduzir significa cancelar trabalho ainda não iniciado, concluir cleanup, reverter para um escritor e transformar resultados de leitura em insumos verificáveis. Um worker nunca nasce porque há uma linha de template para “revisor”, “tester” ou “arquiteto”.

O inverso também é permitido. Um loop único pode descobrir uma investigação somente leitura que isola contexto, ou uma tarefa que pode ser dividida por paths sem disputa. Nesse caso, o registro explicita os novos contratos antes de despachar. Esta é a forma útil de emergência: o grafo descobre sua forma na evidência, em vez de a forma impor trabalho inexistente.

### Orçamento e condições de parada

Antes de iniciar um modo com loop ou grafo, declare uma tupla de orçamento configurável: gasto ou tokens totais, contexto por agente, tempo de parede, máximo de tentativas, número máximo de workers, custo de ferramentas e obrigações de cleanup. Os valores são política local e devem ser escolhidos pela tarefa e pelo provedor; esta pesquisa não encontrou base para números universais.

Pare com sucesso quando os critérios de aceitação e seus checks passarem, não quando todos os papéis planejados tiverem produzido texto. Pare e peça decisão humana quando surgir requisito novo material, permissão ausente, efeito externo não idempotente sem pós-condição, oráculo insuficiente para o blast radius, ou gasto que não compra uma próxima hipótese verificável.

Para retries, use a política: observar o estado, verificar pós-condição, decidir se a operação já ocorreu, então repetir apenas quando for seguro. Isso é especialmente importante fora do repositório. O estudo que suporta a ordem é limitado a simulador, por isso a regra deve ser testada nos conectores reais do kit antes de ser promovida a garantia. Fonte primária, acessada em 2026-08-21: https://arxiv.org/abs/2608.02645.

Para contexto e custo, registre tokens de entrada, saída, leitura de cache, escrita de cache, ferramentas e tempo por resultado aceito quando o provedor expuser tais campos. Use o dado para comparar o mesmo tipo de tarefa em modos diferentes. Não trate uma estimativa de tokens, um encerramento de processo ou um relatório de worker como prova de qualidade.

### Specs executáveis e memória de projeto

Uma spec útil para este kit deve servir como contrato temporário de decisão, não como autoridade eterna. Ela deve conter comportamento observável, invariantes, precondições ou pós-condições quando existirem, os checks que podem refutá-la e uma regra de emenda. No fim, arquive ou resuma o que continua verdadeiro; descarte narrativa que não orienta trabalho futuro.

Checks e feedback de runtime superam a spec porque são a observação mais próxima do produto, mas também não são mágicos: um teste incompleto não torna uma decisão correta. Onde o oráculo é fraco, a spec leve torna suposições auditáveis e requer revisão humana proporcional ao risco. Isso concilia a prática SDD com o alerta de Thoughtworks sobre drift e documentação excessiva. Fonte oficial, acessada em 2026-08-21: https://www.thoughtworks.com/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-ai-assisted-engineering-practices.

Memória de projeto e spec se complementam. A spec é prospectiva e específica à mudança: “qual decisão tomar e como saber se esta mudança está pronta”. Memória é retrospectiva e seletiva: “qual contexto, check ou falha observada merece reaplicação”. Só promova memória derivada de trabalho real, com evidência, escopo e condição de invalidação. Não promova resumo de agente, preferência estética ou conclusão de uma única execução. O comportamento shadow-only de aprendizado descrito no README atual já vai nessa direção e deve continuar sem bloquear execução até revisão explícita.

### Mapeamento para futuras mudanças em my-llm-kit

Estas são recomendações para uma mudança futura. Esta sessão não alterou código, skills, OpenSpecs, journal, state ou runs congelados.

1. Adicionar um selecionador de modo antes de `$spec` e `$impl`. Ele deve produzir os sinais observáveis, o modo escolhido, check mínimo, budget e gatilhos de escalonamento ou redução. O padrão deve ser Modo 0, não OpenSpec ou Agent Graph.
2. Separar o loop verificado de um agente do runtime de grafo. `$impl` não deve congelar runtime, criar journal ou coordenador novo para uma tarefa que o selecionador classifica como Modo 0 ou 1.
3. Criar um formato de spec leve, descartável e emendável. Só converter para OpenSpec completo quando risco, contrato ou decomposição material exigirem a durabilidade adicional.
4. Tornar a entrada no Agent Graph uma precondição explícita: dois ou mais pacotes independentes, ownership sem sobreposição, check por pacote, integrador ou escritor único, orçamento e cleanup. Papéis não são pacotes.
5. Incorporar redução de grafo como transição de primeira classe: cancelar futuros dispatches, liberar recursos com receipt, manter evidência aceita e consolidar a escrita sob um agente quando o acoplamento aparecer.
6. Medir, em shadow mode, resultados por classe de tarefa e modo: resultado aceito, falha detectada, tempo de parede, tokens, cache, retrabalho e overhead de coordenação. Só endurecer gates após repetir uma comparação representativa e auditável; resultados privados sem protocolo, repetições, variância, runs brutos e histórico público permanecem não verificados.
7. Manter coordinator e workers sob perfis proporcionais à tarefa, e não uma exigência de esforço máximo por default. A evidência reunida apoia checks, contexto e feedback; não apoia um esforço de raciocínio máximo universal.
8. Preservar a separação atual entre receipt de execução, evidência de check e aprendizado. Acrescentar pós-condição e idempotency key aos conectores que produzem efeitos externos antes de permitir retry autônomo.
9. Estabilizar o prefixo de contexto que realmente se repete e registrar telemetria de cache quando suportada. Decisão de topologia deve considerar custo medido, não assumir que todo fan-out é mais caro ou que todo loop é mais barato.

## Disagreements

- Cognition, em 12 de junho de 2025, argumentou contra sistemas com escritores paralelos por perda de contexto e decisões implícitas conflitantes. Em 22 de abril de 2026, a mesma empresa reportou um padrão mais estreito: múltiplos agentes podem ajudar quando a escrita fica serial. Não é contradição factual; é uma delimitação posterior de escopo. https://cognition.com/blog/dont-build-multi-agents e https://cognition.com/blog/multi-agents-working, accessed 2026-08-21.
- Anthropic, em 13 de junho de 2025, relatou valor para pesquisa paralela e advertiu que coding é menos paralelizável. O preprint de README, de junho de 2026, encontrou uma troca: agente único foi mais barato e rápido, MAS foi mais consistente estruturalmente. As tarefas, métricas, modelos e ambientes divergem; não há vencedor geral. https://www.anthropic.com/engineering/multi-agent-research-system e https://arxiv.org/abs/2606.30524, accessed 2026-08-21.
- Agentless, de 2024, mostra que pipeline simples pode ser competitivo em SWE-bench Lite. AHE, de 2026, relata ganhos de um harness evoluído em seus benchmarks. Ambos rejeitam a falsa escolha entre “modelo puro” e “cerimônia máxima”: o resultado depende de tarefa, ferramentas, verificador e protocolo. https://arxiv.org/abs/2407.01489 e https://arxiv.org/abs/2604.25850, accessed 2026-08-21.

## Open questions

- Qual conjunto pequeno e representativo de tarefas do próprio my-llm-kit permite comparar Modo 0, 1, 2 e 3 sem confundir mudança de modelo, provider, cache e tarefa?
- Quais efeitos externos do kit têm uma pós-condição consultável e uma chave de idempotência? Onde isso não existir, qual aprovação humana é exigida?
- Qual overhead real de coordinator, dispatch, contexto e cleanup ocorre no Host e no Orca para pacotes com paths isolados?
- As telemetrias de `cached_tokens` e `cache_write_tokens` estão disponíveis em todos os transportes que o kit usa, e como serão normalizadas sem esconder preços ou taxas por provedor?
- O resultado AHE é reproduzível com código, configurações, custos, sementes e runs suficientes para orientar uma alteração do kit? O preprint aberto não basta, sozinho, para endurecer política.
- A estatística MAP ainda descreve prática de produção após a janela de coleta de 2025? O artigo recomenda tratá-la como evidência qualitativa, não prevalência fixa.

## Council review

- Status: not run
- Reason: risco material, mas não houve pedido de `--council`, conclusão material apoiada apenas em fonte secundária ou desacordo direto entre fontes primárias sobre a mesma condição. As divergências encontradas são de escopo, tarefa e métrica, e foram registradas acima.
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://www.anthropic.com/engineering/multi-agent-research-system, accessed 2026-08-21.
- https://cognition.com/blog/dont-build-multi-agents, accessed 2026-08-21.
- https://cognition.com/blog/multi-agents-working, accessed 2026-08-21.
- https://arxiv.org/html/2512.04123v4, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2512.04123.
- https://arxiv.org/abs/2407.01489, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2407.01489.
- https://arxiv.org/abs/2606.30524, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2606.30524.
- https://arxiv.org/abs/2604.25850, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2604.25850.
- https://arxiv.org/abs/2608.12307, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2608.12307.
- https://arxiv.org/abs/2608.02645, accessed 2026-08-21. DOI: https://doi.org/10.48550/arXiv.2608.02645.
- https://www.itl.nist.gov/div898/handbook/apr/section1/apr122.htm, accessed 2026-08-21.
- https://developers.openai.com/api/docs/guides/prompt-caching, accessed 2026-08-21.
- https://www.thoughtworks.com/en-in/radar/techniques/spec-driven-development, accessed 2026-08-21.
- https://www.thoughtworks.com/en-au/radar/techniques/feedback-flywheel, accessed 2026-08-21.
- https://www.thoughtworks.com/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-ai-assisted-engineering-practices, accessed 2026-08-21.
- https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027, accessed 2026-08-21.

## Trial by fire

- Primary-source claims: Anthropic sustenta o custo e o encaixe limitado do multiagente; Cognition sustenta o risco de decisões implícitas e a atualização para escrita serial; MAP sustenta a amostra e os números de supervisão; NIST sustenta as premissas da multiplicação de confiabilidade; OpenAI sustenta a condição técnica do cache; Thoughtworks sustenta o risco de SDD rígido e drift; Gartner sustenta os números de previsão; os preprints sustentam apenas os seus próprios ambientes.
- Secondary-only claims: None. Comentários de terceiros, snippets e posts de LinkedIn serviram apenas para descobrir as fontes primárias.
- Volatile claims: preços, comportamento de cache, catálogo de providers, recomendações de produto e a previsão Gartner. Reconfirmar no momento de implementar ou comprar.
