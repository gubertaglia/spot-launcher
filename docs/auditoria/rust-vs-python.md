# Auditoria: Rust ou Python no Spot Launcher

Data: 7 de novembro de 2026. Escopo: código presente neste workspace.

> Registro da avaliação anterior às correções. A implementação posterior separou
> ferramentas em worker, adiou o Pint, corrigiu caches e persistência, limitou e
> atualizou o índice e substituiu `eval`. Consulte o [README](../../README.md) para
> o comportamento atual e [as novas medições](medicoes-apos-correcao.json).

## Decisão recomendada

**Manter Python nesta etapa e corrigir o fluxo de execução antes de considerar uma migração.** Rust é uma opção tecnicamente adequada para um launcher GTK, mas as evidências coletadas não justificam reescrever a aplicação agora.

Os problemas de maior impacto encontrados são chamadas de rede na thread da interface, inicialização antecipada de dependências e ausência de controle de atualização dos caches. A troca de linguagem não resolve esses problemas automaticamente. A busca local já apresenta tempos baixos no ambiente medido.

Confiança: alta quanto aos bloqueios identificados no código; moderada quanto à decisão de longo prazo, porque não há requisitos definidos de memória, escala ou distribuição, nem uma implementação Rust equivalente para comparação.

## O que foi auditado

- Todos os 12 arquivos Python: aproximadamente 1.550 linhas, incluindo CSS, comentários e linhas vazias.
- Aplicação residente com GTK 4, libadwaita, Gio e integração D-Bus.
- Indexação e lançamento de aplicativos, busca de arquivos, calculadora, ferramentas de conversão, histórico e preferências.
- Dependências identificadas: PyGObject, RapidFuzz e Pint, além da biblioteca padrão.
- Não foram encontrados manifesto de dependências, suíte de testes, configuração de CI ou documentação de instalação nos arquivos disponíveis. O diretório `plugins/` está vazio; não há sistema de plugins implementado para preservar ou migrar.

Foram executadas medições sem abrir a janela, consultar APIs, escrever nos caches pessoais ou percorrer o diretório pessoal. A lista de aplicativos foi lida via Gio. Não foi possível consultar histórico Git: o diretório disponibilizado não é reconhecido como um repositório Git utilizável. `rustc` e `cargo` não foram encontrados no PATH; não foi compilado um protótipo Rust.

## Evidências de desempenho

Ambiente: Linux x86_64, Python 3.15.0, PyGObject 3.58.1, RapidFuzz 3.14.5 e Pint 0.26.2. O Python medido está com GIL habilitado. Resultados completos em [medicoes.json](medicoes.json), com procedimento em [benchmark.py](benchmark.py).

| Operação | Mediana | P95 | Observação |
|---|---:|---:|---|
| Busca entre 48 aplicativos | 0,049–0,076 ms | 0,052–0,122 ms | Cinco consultas, 120 amostras por consulta |
| Reindexação de aplicativos | 4,890 ms | 5,576 ms | 20 amostras, cache aquecido |
| Busca em 1.000 arquivos sintéticos | 0,245–0,284 ms | 0,259–0,309 ms | Três consultas |
| Busca em 10.000 arquivos sintéticos | 2,556–3,141 ms | 2,901–3,989 ms | Próxima do limite pretendido pelo código |
| Busca em 50.000 arquivos sintéticos | 13,378–16,756 ms | 17,412–20,677 ms | Cenário de expansão, acima do limite pretendido |
| Importação de GTK/libadwaita | 84,951 ms | 120,405 ms | Sete processos novos |
| Importação de Pint + `UnitRegistry()` | 179,632 ms | 252,557 ms | Sete processos novos |
| Importação de `src.app` | 264,111 ms | 361,916 ms | Inclui dependências; sem construir a aplicação |

As faixas representam os resultados das diferentes consultas, não intervalos de confiança. P95 usa o método de posto mais próximo; com apenas sete amostras de importação, corresponde ao maior valor observado.

Limitações importantes:

- Os arquivos são sintéticos, com nomes curtos e regulares. Não representam toda a distribuição de nomes, caminhos e correspondências reais. Não foi medida concorrência com a indexação.
- As buscas medem as funções originais, sem renderização GTK, despacho de eventos, espera do debounce ou indexação do disco. Não são a latência entre tecla e resultado visível.
- Os processos de importação são novos, mas não houve limpeza dos caches do sistema operacional. O relógio começa dentro do interpretador; o tempo de criação do processo e de inicialização do Python fica de fora.
- A importação de `src.app` teve pico mediano de RSS de 71,36 MiB; GTK/libadwaita isoladamente, 50,90 MiB. São picos de processos diferentes, **não** memória do daemon ocioso ou parcelas que possam ser subtraídas para estimar economia com Rust.
- Não foram medidos consumo energético, CPU ociosa, memória da GUI, primeira apresentação da janela ou latência real de D-Bus. Não há números de Rust nem promessa de redução percentual de RAM ou tempo.

## Achados que determinam a decisão

### 1. A rede bloqueia a interface — prioridade alta

Em `src/window.py:222–240`, `GLib.timeout_add(180, ...)` agenda `_do_search` no loop principal. Em `src/window.py:277–282`, esse fluxo chama as ferramentas diretamente. O geocoding usa `urllib.request.urlopen(..., timeout=2.5)` em `src/tools.py:127`; a cotação usa `timeout=3` em `src/tools.py:234`.

O debounce adia a chamada e agrupa entradas anteriores; não move o trabalho para outra thread. Uma chamada de rede lenta impede que esse callback devolva o controle ao GTK. Esses timeouts não devem ser interpretados como limites rígidos para a duração total da operação.

A inicialização também chama `_load_rates()` em `ToolsEngine.__init__` (`src/tools.py:67`), executado durante a construção da janela (`src/window.py:102`). Sem cache válido, a primeira apresentação pode depender da rede.

**Ação:** executar I/O fora da thread da interface ou por API assíncrona, publicar o resultado no contexto principal e descartar respostas cuja consulta já mudou. Mostrar resultados locais sem esperar a rede. Aplicar cancelamento, cache e estado de carregamento. A documentação do [GTK sobre threads](https://gnome.pages.gitlab.gnome.org/gtk/gtk4/section-threading.html) exige cuidado com os widgets; o próprio [guia de Rust/GTK](https://gtk-rs.org/gtk4-rs/stable/latest/book/main_event_loop.html) demonstra que tarefas bloqueantes também congelam uma GUI em Rust.

### 2. A inicialização pode melhorar sem reescrita — prioridade média

`src/tools.py:17–23` importa Pint e cria `UnitRegistry()` no carregamento do módulo, mesmo que o usuário só queira abrir aplicativos. O teste isolado dessa operação levou aproximadamente 180 ms. O [Pint documenta](https://pint.readthedocs.io/en/stable/getting/tutorial.html) que o registro carrega definições e relações entre unidades.

**Ação:** avaliar carregamento sob demanda ou preparação em segundo plano, com indicação de disponibilidade da ferramenta. Medir novamente tanto a abertura da aplicação quanto a primeira conversão: inicialização tardia pode apenas transferir a espera para o primeiro uso.

O processo já permanece residente (`src/app.py:44`), e existe ação D-Bus para alternar a janela. Portanto, importação inicial e reabertura de uma instância residente são problemas distintos. Verificar também se o atalho usa D-Bus ou inicia um novo interpretador a cada acionamento; a configuração do atalho não está neste workspace.

### 3. O núcleo fuzzy já usa código nativo — prioridade baixa para migração

`src/matcher.py` e `src/files.py` usam RapidFuzz. No ambiente auditado, `fuzz.ratio.__module__` é `rapidfuzz.fuzz_cpp_avx2`. O [projeto oficial](https://github.com/rapidfuzz/RapidFuzz) confirma sua implementação majoritariamente em C++.

Rust poderia reduzir o custo dos laços Python, normalizações, alocações e ordenação, mas a comparação entre strings já é executada por uma extensão nativa neste ambiente. A busca de aplicativos não apresentou gargalo relevante nas medições.

**Ação:** manter o motor atual e medir dados reais antes de otimizá-lo. Se necessário, pré-calcular nomes normalizados e avaliar seleção dos melhores resultados sem ordenar todos os candidatos. Preservar relevância, desempates e comportamento Unicode ao comparar implementações.

### 4. O índice de arquivos exige desenho melhor antes de escala maior

`src/files.py:66–113` percorre o diretório pessoal e acumula objetos em uma lista. O corte em 10.000 ocorre apenas ao terminar um diretório e usa `>`, podendo ultrapassar bastante esse valor em um diretório grande. Não há persistência do índice nem mecanismo para atualizar remoções e renomeações após essa varredura.

A thread de indexação acrescenta entradas à mesma lista percorrida pela busca, sem snapshot explícito. Não foi demonstrado um crash por isso, mas o conjunto observado pode variar durante uma consulta. O GIL não define um contrato consistente de resultados.

A busca visita todos os itens, aloca cópias dos candidatos e ordena os aprovados. Nos 50 mil itens sintéticos, o P95 ultrapassa 16,7 ms em todas as consultas medidas, podendo consumir o orçamento de um frame de 60 Hz se executada integralmente na thread principal. Isso não prova travamento visual, que depende do fluxo completo.

**Ação:** definir limite real, diretórios permitidos, publicação de snapshots e atualização do índice. Para escala maior, avaliar persistência, filtragem e busca em worker. Rust passa a ser candidato interessante para esse subsistema caso CPU ou memória continuem acima das metas após essas mudanças.

### 5. Robustez e correção não dependem apenas da linguagem

- `src/history.py:32–37` descreve escrita atômica, mas abre o destino diretamente com `w`. Usar arquivo temporário e substituição atômica; revisar os demais JSONs pelo mesmo motivo.
- `src/tools.py:215–252` aceita caches de cotação sem prazo de validade e, em falhas, usa taxas fixas. A interface continua chamando o resultado de “Cotação em Tempo Real” (`src/tools.py:207`). Registrar origem e horário, definir validade e mostrar indisponibilidade ou desatualização.
- `src/calculator.py:45` usa `eval` com filtros e escopo restrito, mas sem limite de tamanho ou complexidade. Expressões matemáticas podem consumir recursos mesmo sem execução arbitrária. Preferir parser com operações permitidas e limites explícitos; esta auditoria não demonstrou fuga do filtro.
- `src/preferences.py:21` fixa `/usr/bin/python3` e `~/spot-launcher` no autostart. Manifesto, instalação e entrada de desktop são necessidades de distribuição em qualquer linguagem.

Esses achados reforçam a necessidade de corrigir contratos e fluxos. Reproduzir o comportamento em Rust preservaria vários desses defeitos.

## Comparação das alternativas

| Critério | Manter Python | Migrar tudo para Rust |
|---|---|---|
| Integração GNOME | Já implementada com PyGObject | Viável com gtk4-rs/libadwaita; requer portar callbacks e estado |
| Busca atual | Tempos baixos medidos | Benefício perceptível ainda não demonstrado |
| Índices grandes e paralelismo de CPU | Exigem atenção a estruturas e ao runtime | Potencial de melhor controle de alocações e paralelismo |
| Memória e startup | Custo do interpretador e imports | Pode eliminar esse custo; GTK e dependências nativas permanecem |
| Conversão de unidades | Pint já integrado | Exige escolher solução e validar equivalência de unidades e temperaturas |
| Robustez | Validação, tipagem e testes precisam ser estruturados | Compilador ajuda com tipos e compartilhamento; não corrige regras de negócio |
| Distribuição | Precisa declarar Python, bibliotecas e instalação | Executável por alvo; build e bibliotecas GTK continuam necessários |
| Custo imediato | Mudanças concentradas nos problemas encontrados | Reescrita, validação de paridade, novo build e manutenção |

Rust não torna automaticamente esta aplicação GTK um binário estático autossuficiente: o [guia oficial de instalação](https://gtk-rs.org/gtk4-rs/stable/latest/book/installation_linux.html) inclui GTK/libadwaita e dependências de build. Também não garante ausência de falhas nas bibliotecas nativas acessadas pelos bindings.

Uma solução híbrida é tecnicamente possível com [PyO3](https://pyo3.rs/main/), mantendo a interface Python e expondo um motor Rust. Deve cruzar essa fronteira em lotes, sem callbacks Python por item e com custo de conversão medido. Acrescenta duas toolchains e empacotamento de extensão por plataforma/versão compatível; não recomendo esse custo para a busca atual. Verificar suporte à versão de Python escolhida antes de um protótipo, especialmente porque o ambiente usa Python 3.15.

O projeto é pequeno, o que favorece uma migração se Rust for uma escolha estratégica explícita. Porém, faltam testes de comportamento e informações sobre experiência da equipe. Não é possível estimar prazo de migração com responsabilidade apenas pelo número de linhas.

## Próximos passos e critérios para reconsiderar Rust

1. Definir e medir latência entre tecla e resultado, abertura pelo atalho, RSS/PSS do daemon após estabilizar e durante indexação, e custo de primeira abertura com rede indisponível. Usar o equipamento alvo.
2. Corrigir rede na thread principal e no startup; permitir resultados locais imediatos e descartar respostas antigas.
3. Avaliar inicialização do Pint, corrigir caches e persistência e tornar o índice de arquivos previsível.
4. Declarar dependências e instalação; criar cobertura dos comportamentos críticos de busca, conversão, lançamento e tratamento de erros antes de uma eventual migração.
5. Repetir as medições. Somente se restarem gargalos relevantes, comparar o Python corrigido com um protótipo Rust isolado, compilado em release e usando os mesmos dados e regras.

Como **metas propostas para discussão**, não requisitos existentes: busca local P95 inferior a 10 ms para 10 mil itens no equipamento alvo; nenhum I/O de rede bloqueando a interface; nenhuma espera artificial de 180 ms para mostrar resultados locais. O orçamento de memória precisa ser definido após medir o daemon real.

Reabrir a decisão se o produto exigir índices muito maiores, processamento de CPU concorrente, um teto de memória que Python não consiga cumprir, distribuição com requisitos incompatíveis com o runtime atual ou adoção estratégica de Rust pela equipe. Exigir do protótipo ganho suficiente para cumprir essas metas e preservar a experiência existente.

**Resultado da auditoria:** o investimento de melhor retorno agora é corrigir a arquitetura em Python. Rust permanece uma alternativa para um motor de busca maior ou para uma mudança estratégica comprovada por requisitos e medições.
