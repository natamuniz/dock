# Comparação com o Doca instalado

Data: 7 de novembro de 2026. Referência: Doca 1.0.26, instalado pelo usuário.

## Evidência e limites

A CLI REA 6.8.0 foi executada com o Node 24.22.1 já instalado. O launcher antigo e o registro MCP apontam para um runtime removido; não foram alterados. A análise não dependeu de um servidor MCP conectado.

O inventário `rea-doca-inventory.json` reteve 404 entradas, com 53 arquivos sondados e 18.020 bytes lidos. Seu identificador é `ev_68ec06af41047cc4fa489a138acf0c6f006c48fb1ecf1b86269582ff0849bfab`. A identidade do inventário não é o hash de todo o conteúdo da instalação.

As evidências estáticas de imports, recursos e metadados e seus identificadores estão em [rea-doca-static-report.md](rea-doca-static-report.md). O EXE não oferece CIL para decompilação gerenciada. NativeAOT é uma inferência apoiada pelos manifests .NET 10 e pela ausência de CLI; não foi recuperado seu código-fonte nem estabelecida equivalência de algoritmos.

A interface foi observada em execução usando Computer Use, separadamente da análise REA. Essa observação não é uma captura de runtime REA e não recebeu um Evidence ID inventado. Foram lidas as páginas Seu dock, Aparência, Posição e espaço e Barra do Windows, e observada a troca de ambiente.

## O que foi observado e implementado

| Observação no Doca | Implementação própria no NT Dock | Verificação |
| --- | --- | --- |
| Ícones de 36 px, folga de 7 px, lente de 1,45× | Proporções e folga configuráveis, três modos de ampliação | Testes de layout, ausência de movimento e ampliação isolada |
| Oito temas e controles de aparência | Oito paletas originais com prévias nos ajustes | Validação, compatibilidade de configurações antigas e render |
| Lixeira, ajustes e indicadores de ambientes no final | Ícone da Lixeira fornecido pelo Windows, controles opcionais e pontos clicáveis | Testes de ordem e troca de perfil |
| Indicadores de aplicativos na cor do ambiente | Indicadores configuráveis e ícones copiados das janelas abertas quando disponíveis | Render e testes de configuração |
| Apps fixados, widgets e aplicativos abertos em grupos | Organização em grupos e separadores | Testes da interface e render |
| Caixa de peças com apps | Catálogo próprio de atalhos do menu Iniciar, busca, ícones e seleção em segundo plano | 72 apps encontrados neste PC; testes sem executar apps |
| Ajustes divididos por categorias | Sidebar, cartões de temas e páginas Seu dock, Aparência, Posição/Windows e Widgets/fontes | Cancelar mantém a configuração original; teste de roundtrip |
| Reserva de espaço e auto-ocultar | Reserva própria, liberação da faixa da barra nativa e recuperação | Validação nativa nas três posições |

O ajuste de janelas já maximizadas é uma implementação própria. Ele mantém as bordas invisíveis e o estado maximizado, sem restaurar ou ativar a janela. Janelas com geometria incompatível e janelas sem moldura não são forçadas a mudar.

## Validação no Windows

- 53 testes automatizados aprovados.
- Monitor de 1920 × 1200 com escala de 150%.
- Reserva de 100 pixels físicos para o dock de 36 px e folga de 7 px.
- Posições inferior, esquerda e direita; ocultar/mostrar; restauração da área útil.
- Uma janela descartável que já estava maximizada ajustou-se nas três posições e permaneceu maximizada.
- Evidência de geometria em [rea-windows-validation.json](rea-windows-validation.json).
- Render atual da barra em [dock-rea-refined.png](dock-rea-refined.png) e ajustes em [settings-refined.png](settings-refined.png).

## Questões ainda abertas

A equivalência integral ao Doca não está estabelecida. Bandeja completa, reprodução de todos os widgets e comportamento simultâneo em vários monitores não foram reconstruídos ou homologados. O usuário concluiu manualmente a confirmação de e-mail e a observação da Ilha e da barra superior foi retomada; nenhuma interação com a autenticação foi automatizada.

## Continuação 0.3.1: Ilha, barra superior e mídia

Observação direta no Doca: Ilha colapsada de aproximadamente 230 × 32, expandida com estado, ambiente/data e timers de 5/15/25 minutos; opções de downloads, capturas, bateria, calendário e volume/brilho. A barra superior depende da Ilha e exibe ambiente, hora, rede, volume, bateria e acesso à bandeja. A opção da Ilha foi temporariamente ativada para observação e devolvida ao estado inicial desligado.

Implementação própria: `island.py`, `topbar.py`, `desktop_events.py` e `media_service.py`. A Ilha usa os temporizadores reais do engine e o estado de mídia fornecido pelo Windows; não inventa compromissos. A barra reserva 28 pixels lógicos no topo independentemente da reserva do dock. Ocultar manualmente esconde os dois painéis e libera as reservas.

Amostragem de arquivos: somente metadados nas pastas conhecidas Downloads e Capturas de Tela, até 4.000 entradas por pasta a cada dois segundos, em worker. Arquivos existentes são ignorados; os novos precisam estabilizar entre amostras. Não há leitura ou envio do conteúdo. Capturas apenas na área de transferência não geram aviso.

Mídia: PyWinRT/SMTC para título, artista e comandos permitidos; Core Audio para volume/mute. Não houve reprodução ou alteração de volume durante a validação real. A leitura retornou volume do sistema e ausência de sessão SMTC; os comandos e falhas foram testados com backend simulado. Dependências Windows constam em requirements.txt e o runtime oferece hook para PyInstaller.

Validação atual: **80 testes aprovados**. Em Windows com DPI de 150%, a área útil passou de `[72, 0, 1920, 1200]` para `[0, 42, 1920, 1100]`, preservando uma janela já maximizada. Ocultar/mostrar e encerrar restauraram a área. Ver `island-topbar-validation.json`, `island-nt.png` e `topbar-nt.png`.

Diferenças remanescentes: calendário da Ilha, avisos de brilho e espelhamento completo de notificações/tray não implementados. Os acessos da barra usam o popup nativo de overflow quando existente ou páginas de Configurações do Windows; não reproduzem integralmente os flyouts de calendário e controles rápidos do Doca. Reserva, tema e timers são implementação própria, não fórmulas decompiladas.

Referências de implementação: [SMTC](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager), [Core Audio](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume), [pastas conhecidas](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid), [URIs de Configurações](https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-settings) e [empacotamento PyWinRT](https://pywinrt.readthedocs.io/en/latest/freezing/).

As cores e os desenhos do NT Dock são implementações próprias. Não foram copiados código, imagens, ícones proprietários, recursos comerciais ou mecanismos de licença do Doca. Os perfis, atalhos, widgets e fontes existentes do usuário foram preservados; a configuração visual foi atualizada com backup.

## Auditoria das configurações em 9 de novembro de 2026

Referência observada em execução: Doca 1.0.26. As oito páginas foram lidas pela árvore de acessibilidade e conferidas visualmente. A personalização avançada do tema foi expandida. Os valores do Doca foram preservados.

| Página | Disponível no NT Dock | Diferenças em aberto |
| --- | --- | --- |
| Seu dock | Perfis, atalhos de apps e pastas, widgets, pontos e isolamento de janelas | Troca por sessão de Foco do Windows e equivalência da galeria com ajuste por instância |
| Aparência | Oito temas, cor hexadecimal, opacidade, contorno, brilho, cantos, reflexo, ponto/traço e três estilos de Lixeira. Tamanho, folga, ampliação e animações já existiam | Geometrias e materiais exatos de cada preset e personalização independente por tema |
| Posição e espaço | Borda inferior, esquerda ou direita, monitor selecionado, reserva e ocultação automática | Docks simultâneos e borda individual por monitor |
| Barra do Windows | Mostrar ou substituir barra nativa, botão Iniciar e modos completo/compacto/mínimo para bandeja, indicadores e hora | Auto-ocultação independente da barra nativa, espelhamento integral da bandeja e Iniciar próprio do Doca. Os botões usam os acessos do Windows já existentes no projeto |
| Ilha | Temporizadores, mídia, downloads, capturas, bateria e volume | Próximo compromisso, brilho e notificações gerais |
| Barra superior | Bandeja, estado, hora e ambientes; cor e fonte próprias | Equivalência dos painéis nativos de calendário e bandeja |
| Porto vivo | Personagens animados já disponíveis no NT Dock | Cenário marítimo e seleção de personagens por água, céu, cais e estação |
| Teclado e atalhos | Atalhos globais do dock e de ambientes, roda e vínculo a áreas de trabalho | Busca global, interceptação isolada da tecla Win e navegação/ordenação por teclado |
| Geral | Inicialização com o Windows e importação/exportação de configuração | Idiomas, histórico de backups e zona de soltar com armazenamento temporário. Licença, atualização, telemetria e ofertas são específicas do Doca |

Nesta entrega, as novas opções ficam em **Aparência** e **Posição e Windows**. Os controles do Windows no dock são opcionais e independentes da barra superior. O botão Iniciar mantém sua configuração própria. O NT Dock não foi iniciado em paralelo ao Doca durante a auditoria.

Validação: 94 testes automatizados aprovados. Renderização das três posições e dos três estilos de Lixeira, coleta dos novos valores, restauração do tema sem mutar a configuração em uso e roteamento do botão da bandeja verificados em modo de teste.
