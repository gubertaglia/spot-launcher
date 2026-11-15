# Segurança e privacidade

Para relatar uma vulnerabilidade, use **Security → Report a vulnerability** no
GitHub, quando disponível. Se esse canal estiver desabilitado, abra uma issue
pedindo um canal privado, sem publicar segredos nem instruções de exploração.
Inclua versão, ambiente e uma reprodução com dados sintéticos no canal privado.

O histórico da área de transferência fica apenas na memória, limitado aos últimos
15 textos, e é descartado ao encerrar o processo. O cache antigo `clipboard.json`
é carregado para a primeira sessão e removido do disco em segundo plano ao
iniciar. Uma falha de remoção gera um erro no log, sem imprimir o conteúdo.
Backups, snapshots e cópias anteriores do arquivo não são removidos.

O aprendizado de busca continua em `$XDG_CACHE_HOME/spot-launcher/history.json`
(por padrão, `~/.cache/spot-launcher/history.json`), privado ao usuário e sem
criptografia. Não publique esse arquivo em issues. Ofertas com
`x-kde-passwordManagerHint` são ignoradas; textos sensíveis sem esse marcador
podem aparecer no histórico em memória durante a sessão.

Clima, hora, cotações, dicionário e tradução usam serviços externos, conforme
as ferramentas descritas no README. Traduções enviam o texto ao MyMemory.
Buscas comuns de aplicativos e arquivos permanecem locais. Mapas e pesquisas
web enviam a consulta quando o resultado é aberto.

Comandos iniciados por `>` executam no shell com as permissões do usuário.
Atualizações Git usam o upstream configurado na instalação. Revise a origem
antes de ativar atualizações automáticas.
