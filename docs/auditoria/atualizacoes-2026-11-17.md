# Revisão do atualizador e tipografia — 17/11/2026

## Escopo

Revisados `src/updater.py`, seus chamadores em `src/window.py`, as preferências,
o worker e os testes de atualização. Mudanças limitadas ao atualizador, estado
do botão de atualização e CSS do launcher; sem novas dependências ou configurações.

## Achados e correções

1. A consulta lia `FETCH_HEAD`, arquivo compartilhado que outro fetch pode sobrescrever.
   Agora consulta a referência upstream e usa `--no-write-fetch-head`, preservando
   o arquivo de outras operações. Teste com repositórios locais verifica ambos.
2. A instalação aceitava qualquer revisão fornecida e podia tratar um commit já
   instalado como sucesso. Agora exige hash completo, destino igual ao upstream,
   diferente de HEAD e descendente de HEAD. A instalação continua com `--ff-only`
   e `--no-overwrite-ignore`.
3. O início da consulta não atualizava o estado do botão nas preferências.
   Agora o botão reflete imediatamente o worker ocupado.

Os testes cobrem instalação, alterações locais, ausência de upstream, arquivos
ignorados e não rastreados em colisão, worktrees, cópias sem Git, entrada inválida,
commit já instalado e divergência local. Nenhum reset, stash ou limpeza é executado.

## Tipografia

Mantida a fonte nativa e o dimensionamento relativo: busca de 1.2rem para 1.15rem,
títulos explícitos em 1rem, descrições em 0.9rem e atalhos de 0.75rem para 0.8rem.
A opacidade das descrições sobe de 0.7 para 0.85; a cor dos atalhos usa alpha 0.8
em vez de 0.6. O objetivo é melhorar hierarquia e leitura, sem trocar a fonte
do usuário ou introduzir tamanhos fixos em pixels.

## Limites

A atualização acompanha a branch configurada, inclusive commits sem release.
O remoto configurado continua sendo a fonte de confiança; não há verificação de
assinatura de commits. Falhas de rede, divergência e ausência de atualização ainda
compartilham o retorno `None` na consulta. Dependências novas e o instalador não
são executados automaticamente. Não foi adicionada transação entre processos Git
externos concorrentes; o Git mantém suas próprias travas e verificações de merge.
Não foi feita instalação de uma atualização na cópia pessoal nem reiniciado o daemon.
A tipografia precisa de avaliação visual na sessão pessoal, especialmente com blur.

Referências: [git fetch](https://git-scm.com/docs/git-fetch) e
[git merge](https://git-scm.com/docs/git-merge).
