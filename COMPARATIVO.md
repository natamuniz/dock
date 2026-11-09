# Análise do Doca e comparação com o NT Dock

**Atualização 0.3.0:** o Doca 1.0.26 instalado pelo usuário foi observado, e seus artefatos foram inspecionados com REA. A cobertura atual, evidências e limites estão em [docs/DOCA_RECONSTRUCTION.md](docs/DOCA_RECONSTRUCTION.md). O texto abaixo é o comparativo inicial da entrega 0.2.x.

Referência histórica: página pública <https://doca.racoelho.com.br/>, consultada em 7 de novembro de 2026. Foram analisados o conteúdo e a demonstração descrita na página; o aplicativo comercial original não foi instalado nem seu código-fonte inspecionado. A tecnologia interna do Doca não é conhecida por esta análise.

## O produto

O Doca combina três propostas: acesso rápido aos aplicativos, organização por contexto e informações compactas em widgets. A ampliação de ícones e o vidro oferecem o apelo visual; a integração com janelas, barra de tarefas, monitores e recuperação após falha concentra a parte mais complexa da implementação.

A página anuncia Windows 10 e 11, teste de sete dias, compra única de R$ 29,95, licença sem vencimento e um ano de atualizações e suporte. Esses são os termos exibidos na página consultada; não são condições comerciais deste projeto pessoal.

Para seu uso, a adaptação foi estruturada com quatro perfis e links de documentação e portfólio, sem dependência de backend ou IA. Aplicativos de desenvolvimento, GED/SIGAD, clientes e pastas de trabalho podem ser adicionados pela interface.

## O que foi entregue e o que difere

“Implementado” abaixo significa que existe implementação no código entregue. Recursos que dependem de Win32 continuam sujeitos à validação no Windows; a tabela não os apresenta como já homologados.

| Recurso anunciado na referência | NT Dock entregue | Verificação / diferença |
|---|---|---|
| Barra com vidro e ampliação | Implementado | Renderização Qt verificada; transparência/gradiente, sem compositor e blur nativo do macOS |
| Temas e força da ampliação | Implementado | Claro/escuro, tamanho e escala configuráveis |
| Aplicativos, documentos, pastas e links | Implementado | Editor, seleção de arquivo/pasta, ícone próprio e arrastar/soltar |
| Ambientes independentes | Implementado | Até 12 perfis; atalhos, cor e widgets por perfil |
| Troca por roda/touchpad/atalho | Implementado | Roda/touchpad e atalhos globais; registro de atalhos ainda exige teste Windows |
| Janelas separadas por ambiente | Implementado | Identificação por executáveis exclusivos e atribuição individual de janelas, inclusive do mesmo navegador; regras verificadas com janelas simuladas, chamadas nativas ainda sem homologação |
| Áreas de trabalho virtuais | Implementado com escopo menor | Acompanha desktops já criados e vinculados; não cria nem força troca de desktop |
| Apps abertos, ativação, minimizar e alternar | Implementado via Win32 | Pendente de teste real Windows; políticas do Windows podem impedir foco em algumas janelas |
| Shift e Ctrl ao clicar | Implementado | Nova instância e Explorer |
| Prévias ao vivo e fechamento de janela | Implementado via DWM | Até cinco prévias; sem validação real Windows; janelas protegidas podem não oferecer miniatura |
| Pastas em grade ou lista | Implementado | Até 500 entradas; pasta maior pode ser aberta no Explorer |
| Prévia rápida pela barra de espaço | Implementado | Imagens, PDF e texto; não inclui todos os formatos Office e multimídia |
| Contagem de arquivos novos em Downloads | Implementado | Badge, horário da última abertura e varredura em segundo plano; opção disponível para outras pastas |
| Dock inferior e nas laterais | Implementado | Layout verificado nas três posições |
| Auto-ocultar e seleção de monitor | Implementado | Seleção Qt e ativação por borda; validar múltiplos monitores e DPI no Windows |
| Substituir barra de tarefas e botão Iniciar | Implementado parcialmente | Na 0.2.1, oculta a barra e solicita ao Explorer a liberação de sua reserva por auto-ocultar temporário, com restauração da preferência original; oferece Iniciar, relógio e widgets; não replica toda a bandeja do sistema |
| Reservar espaço na tela | Implementado via AppBar | Pendente de teste real, especialmente com mais de uma barra e DPI misto |
| Mais de 40 widgets | 46 widgets incorporados | Lógica local verificada; serviços configuráveis e com limites próprios |
| Clima e cotações | Implementado | Três consultas públicas reais verificadas; ação Alpha Vantage depende de chave |
| Biblioteca Steam | Implementado | Conta/ID/chave do usuário não foram fornecidos; integração não autenticada nesta entrega |
| Tradutor | Implementado | MyMemory; texto enviado pelo usuário; integração não testada com consulta real nesta entrega |
| Consumo Claude Code | Implementado para registros locais | Sessões JSONL e JSON externo, contagem diária com cache e deduplicação; não consulta porcentagem da cota ou API de assinatura |
| Widgets criados pelo usuário | Implementado com escopo menor | JSON de texto, data ou link; sem SDK completo de widgets com código |
| Personagens / Porto vivo | Alternativa própria implementada | Gato e cão vetoriais animados; desenhos e animações próprios, sem copiar os personagens da referência |
| Backup automático e exportar/importar | Implementado | Gravação atômica, backup anterior, recuperação e exportação sem chaves de API |
| Restauração ao fechar ou falhar | Implementado com vigia | Teste de recuperação real incluído, ainda não executado por exigir Windows |
| Instalação pela Store / atualização / licença comercial | Não faz parte deste pacote | Instalação por Python e build local; sem assinatura, venda, autoatualizador ou publicação Store |

## Conclusão técnica

O pacote entrega um aplicativo próprio com boa parte das funções centrais e uma interface de dock inspirada no macOS. **Não foi alcançada equivalência integral ao Doca nesta entrega.** As diferenças objetivas estão acima; não é correto chamar o resultado de cópia completa, executável homologado ou produto pronto para distribuição comercial.

Para alcançar equivalência integral, os trabalhos restantes são homologar Win32/DWM/AppBar e recuperação em Windows 10/11; ampliar formatos de prévia e o SDK de widgets; reproduzir os indicadores de sistema restantes e eventuais diferenças do produto original não documentadas pela página; e concluir build Windows, atualização e distribuição. A aparência exata dos ícones do macOS depende de um conjunto de ícones que o usuário escolha; a entrega usa os ícones dos aplicativos instalados ou arquivos locais configurados.

## Fontes técnicas consultadas

- [Qt: janelas translúcidas](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html).
- [Microsoft: DwmRegisterThumbnail](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmregisterthumbnail).
- [Microsoft: DwmUpdateThumbnailProperties](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmupdatethumbnailproperties).
- [Microsoft: IVirtualDesktopManager](https://learn.microsoft.com/en-us/windows/desktop/api/shobjidl_core/nn-shobjidl_core-ivirtualdesktopmanager).
- [Microsoft: ABM_GETSTATE](https://learn.microsoft.com/en-us/windows/desktop/shell/abm-getstate).
- [Microsoft: ABM_SETSTATE](https://learn.microsoft.com/en-us/windows/win32/shell/abm-setstate).
- [Open-Meteo](https://open-meteo.com/en/docs).
- [Frankfurter v1](https://frankfurter.dev/v1/).
- [Alpha Vantage](https://www.alphavantage.co/documentation/).
- [Steam IPlayerService](https://partner.steamgames.com/doc/webapi/IPlayerService).
- [MyMemory](https://mymemory.translated.net/doc/spec.php).
- [CoinGecko](https://docs.coingecko.com/reference/simple-price).
