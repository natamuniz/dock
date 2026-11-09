# NT Dock

Aplicativo desktop pessoal para Windows 10/11, com barra de vidro, ampliação de ícones e perfis de Desenvolvimento, Trabalho, Estudo e Lazer. Código Python/PySide6 com integração Win32/DWM. Interface inspirada no dock do macOS, com identidade NT.

**Estado da entrega:** versão de desenvolvimento 0.3.4. Testes de lógica e GUI aprovados no Windows. Barra de tarefas, reserva nas três posições e recuperação após falha verificadas neste computador; outros monitores e escalas ainda precisam de validação. Este pacote contém o código completo deste projeto e os scripts de instalação; **não contém um `.exe` Windows já compilado e não é uma réplica integral certificada do Doca**. Veja [COMPARATIVO.md](COMPARATIVO.md) para as diferenças concretas.

## Instalar e abrir

1. Extraia toda a pasta para um local permanente, por exemplo `C:\NTDock`. Execute os scripts depois de extrair o ZIP.
2. Tenha Python 3.11 a 3.14 para Windows, com `py` ou `python` disponível no PATH. Python oficial: <https://www.python.org/downloads/windows/>.
3. Dê duplo clique em **INSTALAR.bat**. Ele cria um ambiente Python isolado, instala as dependências e abre o dock.
4. Nas próximas vezes, abra **INICIAR.bat**.
5. Na engrenagem, configure os caminhos de aplicativos e pastas deste computador. Os links web já funcionam; pastas padrão podem precisar de ajuste em instalações com OneDrive ou caminhos corporativos.

A instalação não solicita privilégios de administrador. A primeira instalação precisa de internet para baixar as dependências. O aplicativo também funciona sem internet; só os widgets com fontes externas ficam sem dados.

### Atualizar uma instalação existente

1. Feche o aplicativo pelo menu **Sair do NT Dock** antes de substituir os arquivos.
2. Extraia este pacote e copie o conteúdo da pasta `NT_Dock` para a pasta que já contém seu `INICIAR.bat`, substituindo os arquivos.
3. Abra **INICIAR.bat**. As configurações em `%APPDATA%\NTDock` e o ambiente `.venv` são mantidos. Esta correção não adiciona dependências.
4. Se estiver usando um `.exe` gerado anteriormente, execute **GERAR_EXE.bat** novamente e passe a usar o novo executável.

## Personalizar as cores e a barra superior

Em **Ajustes → Aparência → Cor do dock**, use o seletor ou um hexadecimal, como `#243047`. A prévia mostra o resultado; **Usar tema** restaura a cor do tema.

Em **Ajustes → Ilha e barra superior**, personalize a cor, a fonte e o tamanho da barra superior. Salve os ajustes para aplicar.

## Usar o dock

| Ação | Resultado |
|---|---|
| Passar o mouse | Amplia o ícone e desloca os vizinhos |
| Girar a roda / gesto do touchpad | Troca de perfil |
| Clicar no símbolo do perfil | Abre o menu de perfis e ações |
| Clicar em um aplicativo | Abre, ativa, minimiza ou alterna suas janelas |
| Shift + clique | Abre outra instância; em uma pasta, abre no Explorer |
| Ctrl + clique | Mostra o destino no Explorer |
| Parar o mouse sobre aplicativo aberto | Abre painel com até cinco prévias DWM |
| Clicar em uma pasta | Abre a pilha em grade ou lista |
| Espaço na pilha | Prévia de imagem, PDF ou texto selecionado |
| Arrastar arquivo, `.exe`, `.lnk`, pasta ou link | Adiciona um atalho ao perfil |
| Arrastar um atalho dentro do dock | Reordena os atalhos fixados |
| Botão direito | Menu de aplicativo, janelas, widgets e ajustes |
| Clicar em ✦ | Abre o catálogo e painel de widgets |
| Ctrl + Alt + 1…9 | Seleciona um dos nove primeiros perfis |
| Ctrl + Alt + D | Mostra/oculta o dock |
| Ícone NT na bandeja | Mostra/oculta o dock e oferece menu de saída |

Os atalhos globais avisam quando houver conflito com outro programa. Existem até 12 perfis e 12 atalhos fixados por perfil; aplicativos em execução não fixados aparecem conforme o espaço disponível. Cada perfil pode ter até seis widgets no dock; os demais estão no painel. A pilha mostra até 500 itens, ordenados com pastas primeiro; para pastas maiores, use o botão Explorer.

## Aparência e Windows

Em **Ajustes → Aparência e Windows**:

- Oito temas com prévia; ícones de 32 a 64 pixels; folga de 0 a 16 pixels; modos sem movimento, crescer ou lente; ampliação de 1 a 2 vezes.
- Catálogo de aplicativos instalados pelo menu do dock ou em Seu dock nos ajustes; pesquisa em segundo plano nos atalhos do menu Iniciar.
- Lixeira, botão de ajustes, botão Iniciar e indicadores de ambientes configuráveis.
- Posição inferior, esquerda ou direita e seleção de monitor.
- Auto-ocultar com ativação ao tocar a borda física do monitor.
- Reserva de espaço por AppBar; desativada automaticamente enquanto auto-ocultar estiver ligado.
- Opção de ocultar a barra de tarefas; adiciona botão Iniciar ao dock e ativa temporariamente o auto-ocultar do Windows para liberar a reserva de tela da barra original. Ao sair, restaura a configuração anterior.
- Isolamento de janelas entre perfis: identifica os executáveis fixados exclusivos de cada perfil. Aplicativos presentes em vários perfis continuam compartilhados por padrão; pelo menu de cada janela é possível atribuí-la a um perfil, inclusive separar duas janelas do mesmo navegador. A atribuição individual dura a sessão.
- Personagens vetoriais animados: gato ou cão, selecionáveis nos ajustes.
- Associação de um perfil à área de trabalho virtual atual. Ao mudar de desktop com os atalhos do Windows, o dock acompanha os vínculos configurados.
- Inicialização automática para o usuário atual, pelo Registro HKCU; pode ser desligada no mesmo lugar.

O fundo usa transparência e gradiente. **Não implementa o desfoque óptico nativo do macOS nem replica seu compositor.** Os aplicativos usam seus próprios ícones do Windows; é possível escolher um PNG/ICO/SVG próprio ao editar cada atalho.

**Comportamento padrão:** o dock reserva uma faixa na borda selecionada, impedindo que janelas maximizadas cubram sua base. Essa reserva acompanha o tamanho dos ícones e é liberada ao ocultar manualmente o dock. Para usar sem faixa permanente, ative o modo auto-ocultar.

**Para usar toda a tela:** habilite **Ocultar barra de tarefas enquanto o dock estiver aberto** e desmarque **Reservar espaço para o dock**. São duas reservas diferentes: a primeira opção libera a faixa da barra original; a segunda cria, se marcada, uma reserva própria para o NT Dock. Janelas já maximizadas com moldura padrão são ajustadas automaticamente à nova área útil, mantendo seu estado e sem roubar foco.

A versão 0.2.1 usa `ABM_GETSTATE` / `ABM_SETSTATE` para preservar e restaurar a preferência de auto-ocultar do Windows. A versão anterior apenas escondia a janela da barra, o que podia deixar sua faixa reservada. O processo vigia e o script de recuperação manual agora também restauram essa preferência. Na versão 0.2.2, quando o Explorer não libera a reserva, o dock corrige somente a borda anteriormente ocupada pela barra, com registro para recuperação. As demais bordas e a reserva própria do dock são preservadas. A correção foi verificada em Windows real neste computador.

Downloads recebe um badge com a contagem de arquivos novos desde a última abertura pelo dock, ou desde o início da sessão se ainda não houver histórico. A contagem é atualizada em segundo plano a cada cinco segundos. Para outra pasta, marque **Mostrar contagem de arquivos novos** no editor do atalho. A identificação de chegada usa o horário de criação do arquivo informado pelo sistema de arquivos.

Para vincular áreas virtuais, primeiro crie e selecione o desktop pelo Windows, entre nos ajustes e clique em **Vincular à área de trabalho atual**. O programa usa a interface pública `IVirtualDesktopManager`; não cria nem troca desktops por APIs internas do Explorer.

## Widgets

Há **47 widgets incorporados**, organizados nestas famílias:

| Família | Widgets |
|---|---|
| Horários e calendário | Relógio digital, analógico, mundial, data e calendário |
| Foco | Pomodoro, cronômetro, temporizador e ciclos de foco |
| Progresso | Dia, semana, mês, ano e contagem regressiva |
| Computador | CPU, frequência, RAM, memória virtual, processos, tempo ligado e sistema |
| Disco | Espaço livre, porcentagem utilizada, leitura e gravação |
| Rede e energia | Upload, download, tráfego da sessão, bateria e fonte de energia |
| Pessoal | Hidratação e nota rápida |
| Tempo | Temperatura, máxima/mínima, umidade, vento, nascer e pôr do sol |
| Mercado | Dólar/real, euro/real, Bitcoin/real, Ethereum/real e uma ação configurável |
| Integrações | Música e vídeo do Windows, biblioteca Steam, tradução e consumo local Claude Code / arquivo JSON |

Clique nos temporizadores para iniciar/pausar. O Pomodoro alterna foco de 25 minutos e pausa de 5 minutos, com início manual de cada fase. O botão direito ou o painel permite zerar. Contagens de água, cronômetro, temporizadores e ciclos são da sessão; configurações e notas são persistidas.

### Configurar fontes externas

Dados online vêm desligados. Ative em **Ajustes → Widgets e fontes**. Requisições acontecem em threads, com tempo limite e cache, para não bloquear a animação.

| Recurso | Fonte e configuração |
|---|---|
| Clima | Open-Meteo, coordenadas configuráveis; padrão: centro do Rio de Janeiro |
| USD e EUR | Frankfurter, taxas de referência; atualização da fonte diária, consulta no máximo de hora em hora |
| Criptomoedas | Endpoint público CoinGecko; sujeito a disponibilidade e limite do provedor |
| Ação | Alpha Vantage; preencher símbolo e chave de API; disponibilidade conforme plano do provedor |
| Steam | Steam ID 64 e chave Web API; biblioteca precisa estar acessível à API; clicar abre lista, duplo clique inicia pelo Steam instalado |
| Tradução | MyMemory, par de idiomas como `en\|pt`; até 500 bytes UTF-8 por consulta; o texto informado é enviado ao serviço |
| Relógio mundial | Fuso IANA, por exemplo `Europe/London` ou `America/Sao_Paulo` |
| Claude | Selecione `%USERPROFILE%\.claude\projects`, uma pasta de projeto ou uma sessão `.jsonl`. Conta os tokens de mensagens assistant do dia, incluindo cache e removendo duplicatas por ID. Também aceita JSON externo `{"tokens_today": 12345}`. Não consulta a cota da conta nem estima custo |

As chaves ficam no arquivo local de configurações, com campo mascarado na interface. A exportação pelo aplicativo remove as chaves de API; ao importar em outro PC, informe-as novamente. Erros de rede não interrompem o dock. Dados de mercado não são uma conexão de negociação e podem estar atrasados conforme a fonte.

A leitura do Claude Code acontece localmente, em segundo plano, no máximo uma vez por minuto, sem enviar o conteúdo das sessões. O formato JSONL não é uma API de conta e pode mudar entre versões do Claude Code. O parser lê até 100 MB de sessões do dia por atualização; selecione uma pasta de projeto menor se ultrapassar esse limite. A contagem mede os registros disponíveis, não a porcentagem de cota da assinatura.

### Criar widget próprio

Na primeira abertura, os exemplos são copiados para `%APPDATA%\NTDock\widgets`. Abra essa pasta pelo menu **Abrir pasta de configuração**. Adicione um arquivo JSON, por exemplo:

```json
{"title":"Entrega","type":"countdown","value":"2027-02-10"}
```

Tipos suportados: `text` (texto), `countdown` (data ISO) e `url` (link http/https). Clique em um widget `url` para abrir o navegador. Salve os ajustes ou reabra o aplicativo para recarregar o catálogo. O formato é declarativo: não executa código arbitrário.

## Configurações, backups e recuperação

Dados ficam em `%APPDATA%\NTDock`:

- `config.json`: configuração atual; escrita por arquivo temporário e substituição atômica.
- `config.json.bak`: versão anterior, atualizada ao salvar.
- `config-invalida-*.json`: preservação quando o arquivo atual e o backup não puderem ser lidos.
- `widgets\`: widgets próprios.
- `ntdock.log`: diagnóstico com rotação, até três arquivos de aproximadamente 1 MB.
- `recovery-*.json`: registros temporários de janelas e barras ocultadas.

Um processo vigia independente acompanha o PID e o instante de criação do processo principal. Se o dock terminar, tenta devolver somente as barras e janelas que ele ocultou. A identidade de cada janela é conferida por HWND, PID e criação do processo para reduzir o risco de restaurar outro aplicativo após reutilização de identificadores.

Se precisar restaurar manualmente, execute **RESTAURAR_WINDOWS.bat** e reabra o aplicativo. O script mostra a barra, restaura janelas registradas e desliga essas opções na configuração; não encerra aplicativos. A recuperação nativa foi verificada neste Windows, incluindo encerramento forçado; outras configurações de monitores ainda precisam de validação.

## Gerar executável e testar

Execute **GERAR_EXE.bat** em um Windows com a instalação concluída. O script instala PyInstaller, executa os testes e gera `dist\NTDock\NTDock.exe`. Copie **a pasta inteira** `dist\NTDock`, incluindo suas bibliotecas, para executar em outro Windows compatível. O binário é gerado para a arquitetura do Python usado no build. Ele não é assinado digitalmente nem publicado na Microsoft Store.

Há um workflow opcional em `.github/workflows/windows-build.yml` para build manual no GitHub Actions. Ele só funciona depois de colocar este projeto num repositório e iniciar o workflow; nenhum repositório foi criado nem workflow executado nesta entrega.

Execute **TESTAR_WINDOWS.bat** para verificar no computador de destino. O teste nativo usa somente uma janela descartável criada pelo próprio teste, oculta-a em outro processo e força o encerramento desse processo para verificar o vigia. Não usa documentos nem janelas do usuário e não oculta a barra de tarefas durante esse teste.

Validação atual: **94 testes aprovados no Windows**. Também foram verificadas a liberação da faixa da barra nativa, a reserva do dock nas três posições, janelas maximizadas, ocultar/mostrar e a recuperação após encerramento forçado. Ambiente: 1920 × 1200, escala de 150%. Registro em [docs/windows-validation.json](docs/windows-validation.json) e prévia atual em [docs/dock-refined.png](docs/dock-refined.png).

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Dock, animação, menus, pastas, prévias, painel e instância única |
| `core.py` | Configuração, validação, gravação e Pomodoro |
| `native.py` | Win32, DWM, AppBar, inicialização automática, desktops e vigia |
| `settings.py` | Edição transacional de perfis e opções |
| `widgets.py` | Métricas locais, catálogo, temporizadores, dados externos e cache |
| `recover.py` | Recuperação manual |
| `tests/` | Testes de lógica, GUI e recuperação Windows |

Python + Qt foi escolhido para permitir que você evolua o código na stack que já usa. Não há servidor, banco de dados externo, assinatura ou serviço de IA obrigatório para o funcionamento do dock.


## Comparação com o Doca instalado

A versão 0.3.0 usa observação do Doca 1.0.26 e evidências estáticas REA para aproximar o funcionamento central. Consulte [a cobertura e as questões abertas](docs/DOCA_RECONSTRUCTION.md). A implementação mantém identidade e código próprios; equivalência integral não foi estabelecida.


## Ilha e barra superior

Em **Ajustes → Ilha e barra superior**, ative o painel do topo. Passe o mouse para expandir a Ilha e usar os timers de 5, 15 ou 25 minutos, pausar ou retomar. A barra superior mostra ambiente, hora, rede, volume e bateria e reserva sua própria faixa. Ocultar manualmente o dock esconde os painéis e libera as duas reservas.

A mídia usa a sessão que o aplicativo fornece ao Windows: título, artista e comandos permitidos. O widget **Música e vídeo** abre a Ilha. A consulta é local, sem iniciar reprodução automaticamente. Em instalações existentes, execute INSTALAR.bat para instalar as novas dependências PyWinRT antes de abrir esta versão.

Downloads e capturas são detectados por metadados nas pastas conhecidas do Windows e aparecem com ações para abrir ou mostrar o arquivo. Arquivos já existentes e downloads parciais são ignorados. A Ilha também pode avisar mudanças de bateria e volume. Calendário da Ilha e avisos de brilho ainda não estão integrados.


Em **Ajustes → Posição e Windows**, a opção **Arredondar cantos inferiores das janelas maximizadas compatíveis** aplica um recorte reversível. O efeito mantém os cantos superiores e o estado maximizado, e restaura o formato ao desativar, ocultar ou encerrar. Janelas com recortes personalizados não retangulares são preservadas. O vigia e RESTAURAR_WINDOWS.bat também recuperam o formato se o processo terminar inesperadamente.
