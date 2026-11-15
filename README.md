# Spot Launcher

Um launcher para Linux que reúne aplicativos, arquivos, buscas e ferramentas em uma só janela.
Feito com Python, GTK 4 e libadwaita.

[![Versão](https://img.shields.io/badge/vers%C3%A3o-2.1.0-blue)](https://github.com/gubertaglia/spot-launcher/releases/tag/v2.1.0)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

**[Instalar](#instalar)** · **[Busca](#busca-e-aprendizado-local)** · **[Ferramentas](#dicionário)** · **[Atalhos](#atalhos-super-e-panorama-no-gnome)** · **[Atualizações](#atualizações)**

Busque aplicativos e arquivos, consulte clima e calendário, traduza textos,
execute comandos e controle ações do sistema sem sair do launcher. A interface
está disponível em português, inglês, espanhol e francês.

## Instalar

Requer Linux, Python 3.10+, GTK 4, libadwaita 1.4+ e uma sessão gráfica com D-Bus.
Instale as bibliotecas nativas pela distribuição:

**Ubuntu 24.04+ / Debian 13+:**

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora:**

```bash
sudo dnf install git python3 python3-pip python3-gobject gtk4 libadwaita
```

**Arch Linux:**

```bash
sudo pacman -S --needed git python python-pip python-gobject python-cairo gtk4 libadwaita
```

Os nomes de PyGObject e GTK seguem as [instruções oficiais do PyGObject](https://pygobject.gnome.org/getting_started.html).
A libadwaita precisa oferecer `Adw.SpinRow`, [disponível desde 1.4](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.SpinRow.html).
Distribuições com versões anteriores precisam ser atualizadas.
As receitas não equivalem a testes em todas as distribuições; veja a [validação registrada](docs/auditoria/revisao-2026-11-15.md).

Clone em uma pasta permanente e execute o instalador **sem sudo**:

```bash
git clone https://github.com/gubertaglia/spot-launcher.git
cd spot-launcher
python3 install.py
```

O instalador verifica as bibliotecas nativas, cria `.venv` com acesso aos pacotes
do sistema e instala RapidFuzz e Pint nesse ambiente. Publica SpotLauncher no
menu de aplicativos e o comando `~/.local/bin/spot-launcher`. Não altera Python
nem preferências do sistema. Se `~/.local/bin` não estiver no `PATH`, use o caminho
completo ou o menu. Para verificar apenas as bibliotecas nativas:

```bash
python3 install.py --check
```

Mantenha a pasta do projeto no mesmo local. Depois de movê-la ou atualizar o
Python da distribuição, execute o instalador novamente. Dependências novas após
uma atualização também exigem repetir esse comando. Se um ambiente antigo ficar
incompatível após a troca de Python, renomeie `.venv` e rode o instalador novamente.
O código baixado por ZIP também funciona, mas não oferece atualização por Git.

## Executar

Depois de instalar:

```bash
~/.local/bin/spot-launcher
~/.local/bin/spot-launcher --daemon
~/.local/bin/spot-launcher --toggle
```

Para executar diretamente pelo código:

```bash
.venv/bin/python run.py
```

Para alternar a janela de uma instância residente sem iniciar outro Python:

```bash
gapplication action org.spot.Launcher toggle
```

O autostart usa o interpretador e o caminho da instalação atual. Se mover o
projeto, desative e reative essa opção nas preferências para atualizar a entrada.

## Idiomas

O Spot usa o idioma da sessão Linux e oferece português do Brasil, inglês,
espanhol e francês. Variantes regionais usam a tradução do mesmo idioma.
Quando nenhum idioma disponível corresponde às preferências da sessão, o Spot
usa inglês. As datas e os números das ferramentas seguem o formato regional
do sistema.

Para escolher o idioma pela interface, abra as configurações e altere **Idioma**.
O Spot salva a escolha e reabre as configurações no idioma selecionado. A opção
**Idioma do sistema** volta a acompanhar a sessão Linux.

Para iniciar em outro idioma quando a opção **Idioma do sistema** está selecionada, encerre a instância residente do Spot e execute,
por exemplo:

```bash
LANGUAGE=en .venv/bin/python run.py
```

Use `pt_BR`, `es` ou `fr` para os outros idiomas. Os comandos de busca funcionam
independentemente do idioma da interface. Por exemplo, `hora em Paris`,
`time in Paris`, `hora en París` e `heure à Paris` consultam a hora local.

Nas configurações, **Tema** permite acompanhar o sistema ou escolher claro ou
escuro. Ative **Permitir mover a janela** para arrastar o Spot pela janela. Com **Lembrar a posição**, o Spot
volta ao último local ao reabrir. A restauração usa X11 ou XWayland.

Sem posição salva, o Spot abre no monitor onde está o ponteiro, em X11 e
XWayland. Em Wayland nativo no GNOME, ative **Monitor do ponteiro no Wayland**.
A opção instala ou atualiza a extensão do Spot; se solicitado, saia e entre
na sessão e ative a opção novamente. Ao reabrir, o monitor do ponteiro tem prioridade: **Lembrar a posição** só
restaura uma posição que pertença a esse monitor. Com Super configurado, a
extensão também faz o posicionamento nativo, mesmo sem ativar a opção separada.
Depois de atualizar a extensão, saia e entre na sessão para carregar o novo código.
Outros compositores Wayland controlam o posicionamento da janela.

**Escala do SpotLauncher (%)** muda toda a interface do launcher imediatamente:
50% a 200%, em passos de 25%. O padrão é 100%; 75% reduz e 125% amplia.
A escolha fica salva e se combina com a escala do monitor. Alterar a escala
preserva o centro da janela.

**Texto da caixa de pesquisa** permite substituir a dica de busca. A mudança
é imediata e fica salva; deixe vazio para restaurar o texto padrão do idioma.

**Máximo de Resultados** define quantos itens aparecem por vez, contando
também configurações e pesquisa na web. Com **Permitir rolagem nos resultados**
ligado, use a roda do mouse, o touchpad ou as setas para acessar os outros itens.
Desligue a opção para limitar o total de resultados ao número configurado.

**Ocultar ao perder o foco** controla o fechamento ao clicar fora ou trocar de
aplicativo. Desligue para manter o Spot aberto nessas situações. O atalho
configurado, Esc e a execução de resultados continuam ocultando a janela. Menus,
configurações e diálogos do Spot não acionam o fechamento por perda de foco.

Clique com o botão direito no launcher para abrir o menu de configurações.
No menu, use **Enter** no item selecionado ou **Alt + 1** e **Alt + 2**
para reiniciar ou fechar o SpotLauncher.
Os resultados exibem **Enter** no primeiro item e **Alt + 1** a **Alt + 9**
nos seguintes. Listas maiores continuam com **Alt + A**, **Alt + B** e assim
por diante. A posição fica salva em disco para a próxima inicialização.

## Busca e aprendizado local

A busca de aplicativos e arquivos ignora acentos, caixa, espaços e hífens.
Aceita palavras em outra ordem, um erro em palavras com pelo menos quatro letras
e até dois a partir de oito letras, incluindo letras trocadas de posição.
Apps também usam nomes, palavras-chave e nomes genéricos disponíveis em português,
inglês, espanhol e francês, independentemente do idioma da interface. Frases
como `navegar na internet`, `browse the internet`, `navegar por internet` e
`naviguer sur internet` reconhecem intenções comuns com vocabulário local.

Com uma ou duas letras, a busca considera somente o início do nome exibido.
Prefixos curtos têm a mesma relevância: nomes menores não ganham prioridade.
O histórico desempata apps equivalentes; os demais empates seguem o nome.
Assim, `V` encontra Visual Studio Code e visualizadores, sem incluir Bloquear tela
pelo alias francês. A partir de três caracteres, aliases dos quatro idiomas
continuam disponíveis; aliases parciais não ultrapassam prefixos do nome exibido.

Apps, painéis e ações relevantes aparecem antes dos arquivos, mesmo quando um
arquivo tem o nome exato. Filtros como `documentos:` continuam buscando somente
arquivos. Dentro de cada grupo, a ordem é nome exato, prefixo, palavras no nome,
metadados ou sinônimos e aproximações. Google aparece depois dos resultados
locais e antes das sugestões genéricas de mapas.

Comandos com erro aparecem como sugestões: `calendrio`, `clmia em São Paulo`
e `documntos: relatório`. Selecione a sugestão para confirmar a correção e abrir
a ferramenta. Textos, destinos, valores e comandos após `>` não recebem correção.

No GNOME, os painéis instalados das configurações também entram na busca:
Wi-Fi, Bluetooth, som, monitores, teclado, energia, privacidade e outros. Procure
por `volume`, `microfone` ou `configurar wifi`. Enter abre o painel pelo comando
fornecido pelo sistema. Esses painéis não preenchem a lista inicial vazia.

Abrir um aplicativo ou painel com sucesso aumenta sua prioridade em buscas
relevantes. O Spot também aprende qual resultado você escolhe para cada busca.
Nomes exatos têm prioridade; uso frequente não inclui aplicativos sem relação
com a consulta. O aprendizado mantém até 200 consultas de até 120 caracteres,
com até oito escolhas por consulta, no histórico local privado
`~/.cache/spot-launcher/history.json`. Esse arquivo pode conter termos sensíveis.
Nenhuma consulta de aplicativos é enviada pela rede. O histórico anterior é preservado.

## Pesquisar na web

Digite uma consulta e selecione **Pesquisar no Google** ao fim dos resultados.
Para pesquisar diretamente, use `g previsão do tempo`, `google Python GTK` ou
`web restaurantes em São Paulo` e pressione Enter. A busca abre no navegador
padrão. Nenhuma consulta é enviada ao Google enquanto você digita.

## Mapas, emojis e área de transferência

Digite `mapa São Paulo` ou `maps Paris` e pressione Enter para abrir a busca
no Google Maps, no navegador. Buscas comuns como `São Paulo`, `Brasil` ou
`Paris` também oferecem mapas após os resultados locais.
A opção de mapas aparece para qualquer texto; não há reconhecimento online de
lugares enquanto você digita. Se GNOME Mapas estiver instalado, aparece também
**Abrir no GNOME Mapas** antes das opções do navegador, inclusive para instalações Flatpak com entrada desktop
exportada. A consulta só é enviada ao serviço de mapas quando você abre o resultado.

Digite `emoji` e pressione Enter para abrir o seletor do sistema. Escolher um
emoji copia o caractere. Digite `clipboard` ou `histórico` para recuperar um
dos 15 textos copiados mais recentes. O Spot acompanha cópias enquanto está
ativo, inclusive no modo daemon, conforme as permissões do ambiente gráfico.
O histórico fica somente na memória e é descartado ao encerrar o Spot. Na primeira
execução desta versão, o cache antigo é carregado para a sessão e removido do disco.
Textos sensíveis sem o marcador de senha suportado ainda podem aparecer durante a sessão.

## Pesquisar fotos, vídeos e documentos

Pesquise pelo nome ou pela extensão, como `contrato.pdf`, ou use filtros:

- `fotos: praia` ou `imagens`
- `vídeos: festa` ou `videos`
- `documentos: contrato` ou `documentos`
- `áudio: música` ou `musicas`
- `arquivos: nome` para qualquer tipo de arquivo

Enter abre o arquivo no aplicativo padrão do sistema. A busca usa nomes de
arquivos locais. As pastas de documentos, imagens, vídeos, músicas, área de
trabalho e downloads configuradas no Linux têm prioridade no índice de até
10 mil entradas. A primeira busca cria o índice. A próxima busca após 60 segundos
atualiza os caminhos e reaproveita a classificação dos arquivos conhecidos.

O launcher e suas configurações ficam ocultos da dock na sessão X11/XWayland.

## Consultar o clima

Digite `Clima em Paris` ou `Clima em São Paulo` para ver temperatura em °C,
condições atuais, sensação térmica, umidade e vento diretamente no launcher.
Também aceita `Weather in Brazil`, `tiempo en Madrid` e `météo à Paris`.
Para países, o launcher consulta a capital e mostra seu nome no resultado.
Enquanto busca clima, hora local ou conversões, um indicador aparece logo abaixo
da barra de pesquisa. Enter copia o resumo do clima.
Os dados são fornecidos pelo [Open-Meteo](https://open-meteo.com/), com horário
local da atualização e cache de dez minutos. Se a atualização falhar, o último
resultado fica identificado como desatualizado.

## Calendário

Digite `calendário`, `calendar` ou `agenda` para abrir o calendário mensal no
launcher. Use as setas do calendário para navegar entre meses, selecione um dia
e clique em **Copiar data**. O botão **Hoje** volta para a data atual.
A data segue o formato regional do sistema.

## Ações do sistema

Digite `sistema` para listar as ações disponíveis ou busque diretamente por
`configurações do sistema`, `force quit`, `bloquear tela`, `suspender`,
`reiniciar`, `desligar` ou `sair da sessão`. Também há termos de busca em
inglês, espanhol e francês. As ações respeitam o limite de resultados e a rolagem.

**Force Quit** abre o monitor do sistema: selecione nele o processo que deseja
encerrar. Configurações, monitor e saída da sessão usam ferramentas instaladas
do GNOME, KDE, Xfce, Cinnamon ou MATE, com preferência pelo desktop atual.
Só aparecem ações cujo comando está instalado. Bloqueio usa `loginctl`;
suspensão, reinício e desligamento usam `systemctl`, sujeitos às permissões e
ao suporte da sessão. Falhas desses comandos são exibidas no launcher.
Reiniciar, desligar e sair da sessão pedem confirmação; salve o trabalho antes.

## Arquitetura

- A thread GTK mostra aplicativos e cálculos locais. A busca de arquivos e a
  leitura do histórico da área de transferência usam um worker com debounce de 80 ms.
- Ferramentas usam um único worker. Apenas a consulta pendente mais recente é
  mantida; respostas antigas são descartadas inclusive após serem enfileiradas
  para entrega no loop principal. Ocultar a janela invalida essas respostas.
- O debounce de 180 ms se aplica somente às ferramentas. Uma requisição de rede
  já iniciada termina pelo próprio timeout; invalidar uma consulta impede sua
  apresentação, sem interromper à força a thread.
- Pint é carregado no worker na primeira conversão de unidades. Nenhuma consulta
  de rede é feita ao construir a aplicação.
- Cotações têm validade de uma hora e intervalo mínimo de 60 segundos entre
  tentativas de atualização. Em falha, o cache anterior recebe indicação de
  desatualização. Não há cotações fixas de fallback.
- O índice de arquivos é construído fora da interface, publicado como snapshot
  imutável e atualizado sob demanda após 60 segundos. Há limite estrito de 10 mil entradas,
  exclusão de pastas ocultas, `node_modules`, `venv` e `__pycache__`, sem percorrer
  links simbólicos de diretórios. Alterações aparecem após a reconstrução e uma
  nova busca; o índice não é persistido em disco.
- Histórico, preferências e caches JSON usam substituição atômica com arquivo
  temporário privado. A calculadora aceita uma árvore limitada de operações,
  sem `eval`, com limites de tamanho, profundidade, expoente e resultado.

## Validar

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B docs/auditoria/benchmark.py
```

Os testes não abrem janelas nem acessam serviços externos. Usam diretórios
temporários, respostas simuladas e sincronização entre threads. A suíte também
valida o despacho pelo loop GLib; testes de interação visual precisam de uma
sessão gráfica.

A avaliação original da escolha de linguagem está em
[`docs/auditoria/rust-vs-python.md`](docs/auditoria/rust-vs-python.md).

## Atalhos, Super e panorama no GNOME

Em **Atalho para abrir o Spot**, clique em **Alterar** e pressione a combinação
desejada, ou pressione e solte **Super** para usá-la sozinha. Escape cancela e
Backspace remove o atalho, inclusive Super. Selecionar outro atalho desativa
Super sozinho. Configurações antigas de Super continuam válidas.
O GNOME gerencia este
atalho global; combinações reservadas pelo sistema podem não funcionar.
O Spot precisa estar ativo para receber o comando.

**Super** alterna o launcher usando a tecla de panorama configurada no GNOME.
**Desabilitar o panorama** bloqueia a visão geral do GNOME.
Esses recursos instalam e ativam uma extensão local para GNOME Shell 45 a 51; podem
ser desligadas separadamente. Para usar Super após entrar na sessão, ative também
**Iniciar com o sistema**. A extensão requer `gnome-extensions` e uma sessão
GNOME Shell que permita extensões.
Na primeira instalação, saia da sessão e entre novamente para o GNOME reconhecer
a extensão. Depois ative a opção desejada nas configurações. A instalação ocorre
em segundo plano para manter a interface responsiva.

A posição padrão fica centralizada horizontalmente e acima do centro vertical
em X11/XWayland. Em Wayland nativo, o compositor decide a posição da janela.
Ao reabrir, o monitor do ponteiro tem prioridade: **Lembrar a posição** só
restaura uma posição que pertença a esse monitor. Com Super configurado, a
extensão também faz o posicionamento nativo, mesmo sem ativar a opção separada.
Depois de atualizar a extensão, saia e entre na sessão para carregar o novo código.

## Blur my Shell

Ative **Compatibilidade com Blur my Shell** para deixar o fundo do Spot
translúcido, sem reduzir a opacidade dos textos e ícones. A mudança é imediata;
desligar a opção restaura o fundo opaco. A opção vem desligada.

Na extensão [Blur my Shell](https://github.com/aunetx/blur-my-shell), ative o
desfoque de aplicativos e adicione a janela do Spot à lista permitida
(`org.spot.Launcher`), caso o desfoque não esteja habilitado para todas as janelas.
Use opacidade de janela em 100% para manter textos e ícones nítidos. Desative a
opção que torna a janela focada opaca para manter o desfoque durante a busca.
O Spot não instala nem altera as preferências da extensão. Sem ela configurada,
a compatibilidade oferece transparência, sem desfoque.

## Executar comandos

Digite `> comando` e pressione Enter para executar no terminal, por exemplo
`> htop` ou `> ls -la | less`. O comando passa pelo shell da sessão e pode usar
pipes e redirecionamentos. O Spot precisa encontrar um terminal compatível.

## Licença

O código do projeto está disponível sob a [licença MIT](LICENSE). Os dados de
países e capitais possuem [licença própria](data/countries/README.md).

## Atualizações

O menu do botão direito permite fechar ou reiniciar o Spot Launcher. O Spot
verifica atualizações ao iniciar e periodicamente ao abrir a janela. O aviso
pode ser dispensado para a versão atual ou desativado permanentemente. O botão
**Atualizar** continua disponível nas configurações quando há uma atualização.
Ative **Atualizações automáticas** para instalar sem aviso e reiniciar o Spot.

A atualização exige Git e uma instalação clonada com uma branch remota
configurada. Ela só avança a branch quando possível e preserva alterações
locais. Se falhar, verifique a conexão e o estado do repositório. A atualização
não instala dependências novas do sistema ou do Python.

## Dicionário

Digite `defina palavra` para português, `define word` para inglês,
`diccionario palabra` para espanhol ou `définir mot` para francês.
`dict palavra` usa o idioma do Spot. Para escolher explicitamente a edição,
use `defina en: brain`, `dict es: cerebro` ou `dict fr: cerveau`.
Os códigos disponíveis são `pt`, `en`, `es` e `fr`; a edição escolhida define
o idioma das explicações, sem detecção automática do idioma da palavra.
As definições aparecem nos resultados após uma pausa de 400 ms; a consulta
exige internet. Cada definição mostra a edição consultada. Enter copia o texto.
O último resultado abre a fonte no navegador. Falhas ou palavras ausentes
mostram “Definição indisponível” e mantêm o link da fonte.
Também aceita `o que significa saudade?`, `significado de casa` e
`what does brain mean?`. Se a entrada não existe, tenta minúsculas e a
correção ortográfica sugerida pelo Wiktionary. Correções aparecem junto da definição.

## Tradução

Digite `traduza en: bom dia` para traduzir do idioma do Spot para inglês.
Para indicar origem e destino, use `traduza en:pt: good morning` ou
`translate pt:fr: bom dia`.
Também aceita `bom dia em ingles`, `traduza mesa para russo`,
`como se diz mesa em russo?`, `traduza para alemão: bom dia` e
`traduza mesa de português para russo`.
Os idiomas aceitos, por código ou nome, são: português (`pt`), inglês (`en`),
espanhol (`es`), francês (`fr`), russo (`ru`), alemão (`de`), italiano (`it`),
japonês (`ja`), chinês (`zh`), coreano (`ko`), árabe (`ar`), hindi (`hi`),
ucraniano (`uk`), grego (`el`), hebraico (`he`), turco (`tr`), holandês (`nl`),
polonês (`pl`), sueco (`sv`), dinamarquês (`da`), norueguês (`no`), finlandês (`fi`),
tcheco (`cs`), romeno (`ro`), húngaro (`hu`), indonésio (`id`), vietnamita (`vi`)
e tailandês (`th`). Nomes em português aceitam escrita sem acentos.
A origem é explícita ou usa o idioma do Spot; não há detecção automática.
O resultado aparece no launcher após uma pausa de 400 ms. Enter copia a tradução.

A consulta envia o texto ao [MyMemory](https://mymemory.translated.net/doc/spec.php),
exige internet e respeita o limite de 500 bytes UTF-8 por texto.
O serviço tem cota gratuita e pode ficar indisponível. Consultas repetidas
reutilizam até 64 traduções em memória durante a sessão, sem salvar em disco.

## Caffeine

Digite `caffeine` ou `cafeina` para ver o toggle e as durações configuradas
(curta, média, longa e ilimitada) da extensão Caffeine instalada. Escolher uma
duração define o timer e ativa a inibição de suspensão. A extensão precisa estar
habilitada no GNOME.


## Remover a instalação

Encerre o Spot pelo menu e desative **Iniciar com o sistema** e os atalhos nas
preferências. Depois remova somente os arquivos publicados pelo instalador:

```bash
rm -- "$HOME/.local/bin/spot-launcher"
rm -- "${XDG_DATA_HOME:-$HOME/.local/share}/applications/org.spot.Launcher.desktop"
```

A pasta clonada e `.venv` podem ser removidas depois. Configurações e aprendizado de busca
permanecem nos diretórios XDG do usuário; removê-los apaga essas preferências.
O histórico da área de transferência existe apenas durante a sessão. A extensão opcional do GNOME pode ser desativada ou removida
pelo aplicativo Extensões.

## Manutenção

Consulte [documentação e auditorias](docs/README.md),
[contribuição](CONTRIBUTING.md) e [segurança e privacidade](SECURITY.md).
A CI executa a suíte em Ubuntu 24.04 e Debian 13; resultados só existem após o
workflow rodar no GitHub. Dependabot verifica dependências Python e GitHub Actions.
