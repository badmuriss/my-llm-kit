---
name: ingestao
description: Converte documento em markdown estruturado antes de qualquer análise, roteando cada tipo de arquivo para o conversor certo. Use quando o usuário subir ou apontar para PDF, Word, Excel, PowerPoint, EPUB, imagem, áudio ou repositório de código, e quando um PDF científico precisar preservar fórmula, tabela e ordem de leitura. Também use antes de resumir, analisar ou citar qualquer documento.
---

# Ingestão

Converta antes de ler. Material que entra destruído produz conclusão destruída, e o modelo não avisa quando isso acontece.

## Roteamento por tipo

| Situação | Ferramenta | Comando |
|---|---|---|
| documento comum: pdf simples, word, excel, powerpoint, epub, imagem, áudio | markitdown | `markitdown entrada.pdf > saida.md` |
| pdf científico, duas colunas, escaneado, com fórmula ou tabela complexa e o markitdown embaralhou | MinerU (opcional, instale só quando precisar) | ver README do projeto |
| repositório de código inteiro | repomix | `npx repomix` |

Regra de decisão em duas linhas: comece pelo markitdown, que resolve a maioria e já está instalado. Se a saída vier com ordem de leitura embaralhada, fórmula perdida ou tabela virada em linha corrida, o problema é layout e a resposta é MinerU, que é dependência pesada e não vem instalada por padrão.

## Procedimento

1. Identifique o tipo e escolha a ferramenta pela tabela
2. Converta para uma pasta `./fontes-md` mantendo o nome original do arquivo
3. Abra a saída e verifique quatro coisas antes de seguir: os headings sobreviveram, as tabelas continuam tabelas, a ordem de leitura faz sentido, e as notas de rodapé não invadiram o corpo
4. Se qualquer uma falhar, troque de conversor antes de analisar

## Verificação obrigatória

Nunca declare a ingestão concluída sem abrir o markdown gerado. Conversão silenciosamente errada é a causa mais comum de análise errada, e é invisível se você confiar no processo sem olhar.

Se a conversão falhou e trocar de conversor não resolveu, reporte o problema ao usuário em vez de analisar o texto quebrado.

Ao relatar para o usuário, diga qual conversor foi usado e o que foi verificado.

---

Adaptado de [research-stack](https://github.com/nett0eth/research-stack) (Netto, @nett0eth), licença MIT.
