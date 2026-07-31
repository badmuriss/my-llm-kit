# my-llm-kit

Setup pessoal de Claude Code do Murilo: sistema de escrita, sistema de pesquisa e CLAUDE.md versionado, tudo num repo só.

## Inventário

| Componente | O que faz | Origem/crédito |
|---|---|---|
| skills/pesquisa | Ciclo de pesquisa com fonte primária, divergência reportada e saída auditável | Adaptado de [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| skills/ingestao | Roteia PDF/Word/Excel/repo para o conversor certo antes de qualquer análise | Adaptado de [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| unslop | Sistema de escrita (humanizer), v2 | Próprio: [github.com/badmuriss/unslop](https://github.com/badmuriss/unslop) |
| CLAUDE.md | Configuração global do Claude Code, versionada | Próprio |
| setup.sh | Instala dependências, registra MCP, clona o unslop e symlinka tudo para `~/.claude/` | Próprio, adaptado do setup do research-stack |

## Sistema de escrita (unslop)

Vive em repo próprio, [badmuriss/unslop](https://github.com/badmuriss/unslop), clonado localmente em `~/Documents/unslop`. Esse clone é a fonte de verdade. Há uma cópia sincronizada manualmente em `outis-hermes-skills/skills/unslop` para rodar na VPS do Hermes, mas quem manda é o repo.

v2 tem 4 modos: escrever, editar, detectar e avaliar. Camada pt-br para corrigir maneirismo de tradução automática (travessão, "no entanto", "é importante notar"). Rubrica de 0 a 50 pontos com corte em 35: abaixo disso o texto entra em reescrita antes de sair. Eval de auto-checagem roda no fim de cada geração para pegar recaída antes do usuário ver.

`setup.sh` clona o repo em `~/Documents/unslop` se ainda não existir e faz symlink para `~/.claude/skills/unslop`.

## Sistema de pesquisa

Duas skills, `pesquisa` e `ingestao`, adaptadas do [research-stack](https://github.com/nett0eth/research-stack) de Netto (@nett0eth), licença MIT.

`pesquisa` aplica quatro regras inegociáveis em toda investigação: fonte primária na frente, divergência reportada nunca resolvida em silêncio, amostra fraca marcada como tal, saída sempre auditável (URL e data ao lado de todo número). `ingestao` roteia cada arquivo (PDF, Word, Excel, repositório) para o conversor certo antes de qualquer leitura.

O MCP `paper-search` entra para localizar literatura em arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex e Unpaywall. `setup.sh` registra ele em escopo de usuário, sem duplicar se já existir.

## CLAUDE.md global versionado

O `CLAUDE.md` deste repo é a configuração global do Claude Code. `setup.sh` faz symlink de `~/.claude/CLAUDE.md` para o arquivo do repo, com backup automático (`~/.claude/CLAUDE.md.bak-<data>`) se já existir um arquivo normal no lugar. Rodar de novo não duplica o backup nem quebra o symlink já correto.

## Instalação

```bash
git clone <url-deste-repo> my-llm-kit
cd my-llm-kit
./setup.sh --dry-run   # confere o que vai mudar antes de rodar de verdade
./setup.sh
```

O script é idempotente: rodar de novo não duplica MCP nem quebra symlink já correto.

## Créditos

O sistema de pesquisa e ingestão é adaptado de [research-stack](https://github.com/nett0eth/research-stack), de Netto (@nett0eth), licença MIT.

O sistema de escrita (unslop) é próprio.
