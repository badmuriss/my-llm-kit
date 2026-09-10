# Spec: a change the owner can understand

This is a planning example, not a report of implemented behavior. Keep the
visual-brief block in the existing canonical decision/spec; do not keep a
second independently maintained JSON document. Detailed decisions can remain
outside this bounded presentation block.

```visual-brief
{
  "schema_version": 1,
  "language": "pt-BR",
  "title": "Menos supervisão mecânica. Mais clareza para decidir.",
  "summary": "Proposta de fluxo para o my-llm-kit: tornar a mudança compreensível antes do código e deixar explícito como investigar falhas depois.",
  "before": "Um plano técnico pode esconder o que muda, quais escolhas importam e onde olhar quando a execução falha. Consultas repetidas ao coordenador também podem aumentar o custo.",
  "after": "A mesma spec gera uma visão visual. O trabalho é separado por decisões verificáveis; rotinas mecânicas ficam no código, e o modelo retorna quando existe algo novo para avaliar.",
  "flow": [
    {"title": "Entender a mudança", "detail": "Objetivo, antes/depois, limites e dúvidas que realmente alteram o plano."},
    {"title": "Revisar a decisão", "detail": "Mostrar escolhas, alternativas e critérios de aceite antes de implementar; respeitar a autorização já dada."},
    {"title": "Executar com escopo", "detail": "Usar um agente para trabalho coeso; delegar somente pacotes independentes e justificáveis."},
    {"title": "Observar e verificar", "detail": "Checks e evidências devem distinguir resultado observado, falha e informação indisponível."},
    {"title": "Explicar a conclusão", "detail": "Comparar o resultado com a spec e apontar o que não foi verificado, sem transformar aparência em aprovação."}
  ],
  "checks": [
    {"criterion": "O plano pode ser compreendido", "evidence": "A visão mostra objetivo, mudança, decisões, limites e critérios sem exigir a leitura de logs."},
    {"criterion": "A apresentação corresponde à fonte", "evidence": "O fingerprint do HTML corresponde à spec; alterações exigem regeneração."},
    {"criterion": "As falhas têm um caminho de investigação", "evidence": "Cada risco aponta um sintoma, onde buscar evidência e como recuperar sem esconder incerteza."}
  ],
  "risks": [
    {"symptom": "O worker não terminou", "inspect": "Estado da tentativa, timeout e identificação do responsável; silêncio não prova falha.", "recovery": "Verificar o estado antes de cancelar ou substituir; manter as obrigações de cleanup."},
    {"symptom": "O teste falhou", "inspect": "Check exato, versão dos arquivos e evidência produzida; separar defeito de erro do ambiente.", "recovery": "Corrigir uma hipótese delimitada. Não aumentar reasoning ou abrir novos agentes automaticamente."},
    {"symptom": "O diagrama está bonito, mas desatualizado", "inspect": "Fingerprint da spec e revisão do código referenciada.", "recovery": "Regenerar a visão a partir da fonte; não editar o PDF como se fosse o plano original."}
  ],
  "decisions": [
    "HTML é a visão principal para leitura, navegação e impressão. PDF é uma exportação da mesma visão.",
    "Mermaid ou Draw.io complementam relações complexas. O fluxo resumido não se passa por um mapa completo da arquitetura.",
    "A renderização é determinística: não precisa de outro modelo para redesenhar a apresentação."
  ],
  "excluded": [
    "Ativar modelos, MCPs ou serviços externos automaticamente.",
    "Transformar todo ajuste trivial em um documento formal.",
    "Apresentar esta proposta como dashboard ao vivo ou evidência de execução."
  ]
}
```
