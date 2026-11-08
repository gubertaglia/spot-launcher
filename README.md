# Spot Launcher

Launcher para Linux com Python, GTK 4 e libadwaita.

Versão atual: **1.6.0**.

## Executar

Use Python 3.10 ou superior. GTK 4, libadwaita (1.4 ou superior), Gio e seus
typelibs precisam estar instalados pelo sistema. As dependências Python estão
em `requirements.txt`; PyGObject também pode ser fornecido pela distribuição.
Um ambiente virtual precisa ter acesso a essas bibliotecas nativas.

```bash
python3 run.py
python3 run.py --daemon
python3 run.py --toggle
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
LANGUAGE=en python3 run.py
```

Use `pt_BR`, `es` ou `fr` para os outros idiomas. Os comandos de busca funcionam
independentemente do idioma da interface. Por exemplo, `hora em Paris`,
`time in Paris`, `hora en París` e `heure à Paris` consultam a hora local.

Nas configurações, **Tema** permite acompanhar o sistema ou escolher claro ou
escuro. Ative **Permitir mover a janela** para arrastar o Spot pela janela. Com **Lembrar a posição**, o Spot
volta ao último local ao reabrir. A restauração usa X11 ou XWayland.

**Máximo de Resultados** define quantos itens aparecem por vez, contando
também configurações e pesquisa na web. Com **Permitir rolagem nos resultados**
ligado, use a roda do mouse, o touchpad ou as setas para acessar os outros itens.
Desligue a opção para limitar o total de resultados ao número configurado.

Clique com o botão direito no launcher para abrir o menu de configurações.
Os resultados exibem **Enter** no primeiro item e **Alt + 1** a **Alt + 9**
nos seguintes. Listas maiores continuam com **Alt + A**, **Alt + B** e assim
por diante. A posição fica salva em disco para a próxima inicialização.

## Pesquisar na web

Digite uma consulta e selecione **Pesquisar no Google** ao fim dos resultados.
Para pesquisar diretamente, use `g previsão do tempo`, `google Python GTK` ou
`web restaurantes em São Paulo` e pressione Enter. A busca abre no navegador
padrão. Nenhuma consulta é enviada ao Google enquanto você digita.

## Mapas, emojis e área de transferência

Digite `mapa São Paulo` ou `maps Paris` e pressione Enter para abrir a busca
no Google Maps, no navegador. A consulta só é enviada ao abrir o resultado.

Digite `emoji` e pressione Enter para abrir o seletor do sistema. Escolher um
emoji copia o caractere. Digite `clipboard` ou `histórico` para recuperar um
dos 15 textos copiados mais recentes. O Spot acompanha cópias enquanto está
ativo, inclusive no modo daemon, conforme as permissões do ambiente gráfico.
O histórico fica no cache local e pode conter dados sensíveis.

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
python3 -B -m unittest discover -s tests -v
python3 -B docs/auditoria/benchmark.py
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
Uma posição salva com **Lembrar a posição** tem prioridade.

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
