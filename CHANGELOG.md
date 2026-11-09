# Alterações

## 0.3.4 — 7 de novembro de 2026

- Barra superior com fundo grafite independente, tipografia mais legível e indicadores adaptáveis ao espaço disponível.
- Cor do dock e da barra superior com seletor, hexadecimal, prévia e retorno ao tema. Contraste automático do texto.
- Fonte e tamanho da barra superior configuráveis.
- 94 testes aprovados no Windows.

## 0.3.3 — 7 de novembro de 2026

- Corrige janelas maximizadas que ignoravam a reserva e deixavam os botões de título sob a barra superior. O encaixe usa as margens reais do DWM, inclusive para posições antigas incompatíveis com a área útil atual.
- Nova opção em Posição e Windows: arredondar somente os cantos inferiores das janelas maximizadas compatíveis. Recorte GDI reversível; mantém o estado maximizado e preserva regiões personalizadas não retangulares.
- O formato anterior é registrado antes de aplicar o efeito e restaurado ao desativar, ocultar, sair ou pelo vigia após falha. Regiões posteriormente modificadas pelo aplicativo não são sobrescritas. Falhas de restauração mantêm o registro para recuperação.
- 90 testes aprovados, incluindo recuperação nativa após encerramento forçado. Validação em janelas reais e de teste: cantos inferiores recortados, centro preservado e formato original restaurado (`docs/window-effects-validation.json`).

Referências: [margens visíveis do DWM](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute) e [SetWindowRgn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn). O efeito usa um recorte próprio; não é o arredondamento DWM nativo, que não se aplica a janelas maximizadas.

## 0.3.2 — 7 de novembro de 2026

- Lente usa centros fixos como referência, eliminando realimentação da posição dos ícones durante a ampliação.
- Suavização pelo tempo decorrido e temporizador preciso conforme o monitor, com resposta consistente em 60/120 Hz e retomada sem saltos.
- Ícones rasterizados em cache e desenhados em coordenadas fracionárias; repintura limitada ao movimento e às legendas.
- Métricas de CPU/disco/rede saem da thread da interface para um worker exclusivo; temporizadores e respostas online continuam sendo atualizados na interface.
- 83 testes aprovados, incluindo referência estável, independência da taxa de quadros e coleta lenta sem bloquear timers. Probe de 240 quadros Qt nativos em `docs/hover-performance.json`: processamento médio 3,26 ms e p95 4,43 ms neste Windows/DPI150%; isso não mede a cadência de apresentação do monitor.

## 0.3.1 — 7 de novembro de 2026

- Ilha no topo com expansão, timers rápidos de 5/15/25 minutos, pausa, retomada e avisos com ações para arquivos locais.
- Barra superior com reserva independente: ambiente, relógio, rede, volume real, bateria e acesso aos controles do Windows. Ocultar manualmente libera ambas as reservas; auto-ocultar só do dock mantém a reserva da barra superior.
- Integração local SMTC para música/vídeo e Core Audio para volume/mute, em um worker próprio. Novo widget Música e vídeo. Não inicia reprodução automaticamente.
- Avisos de downloads e capturas salvas nas pastas conhecidas do Windows, bateria e volume. Arquivos existentes formam a linha de base, downloads parciais são ignorados e um arquivo novo precisa estabilizar antes do aviso.
- Novos ajustes transacionais, encerramento dos serviços e correção do encaminhamento de mensagens AppBar entre a barra inferior e a superior.
- 80 testes automatizados; validação nativa de reserva superior/inferior, janela maximizada, ocultar/mostrar e restauração. Comandos de mídia validados com backend simulado; a consulta local real encontrou volume, mas nenhuma sessão de reprodução ativa.

## 0.3.0 — 7 de novembro de 2026

- Comparação com Doca 1.0.26 instalado: inventário e evidências REA, observação da interface e reconstrução independente das funções centrais. Ver `docs/DOCA_RECONSTRUCTION.md` para cobertura e limites.
- Oito temas, folga ajustável, lente de 1,45×, modos nenhum/crescer/lente e feedback de abertura selecionável.
- Apps e widgets fixados, apps abertos e controles finais agrupados; Lixeira nativa, ajustes discretos e pontos de ambientes clicáveis.
- Catálogo de apps do menu Iniciar com busca e carregamento em segundo plano, disponível no menu e nos ajustes.
- Ajustes com sidebar e cartões de temas, mantendo cancelamento e importação/exportação transacionais.
- Ícones das janelas abertas quando disponíveis, correção de janelas já maximizadas ao mudar a área útil e recuperação de novas barras após reinício do Explorer.
- 53 testes aprovados e validação nativa nas três posições. A equivalência integral ao Doca permanece não estabelecida; recursos adicionais dependem de investigação.

## 0.2.2 — 7 de novembro de 2026

- Refinamento visual segundo a skill Emil Kowalski: vidro neutro, separadores, controles discretos, estado pressionado nos ícones e botões e fundo dimensionado para os ícones de 32 a 64 pixels.
- Correção reproduzida no Windows: o Explorer pode retornar sucesso em `ABM_SETSTATE` sem liberar a faixa da barra. O dock registra a geometria antes de ocultar e corrige somente a borda ocupada pela barra, preservando as outras reservas. A recuperação normal, manual e por vigia restaura essa geometria.
- A notificação da correção de área útil é enviada aos outros processos; um broadcast para o Explorer recriava imediatamente a reserva antiga neste computador.
- A reserva do dock vem ativada por padrão, ocupa a linha inteira da borda selecionada e acompanha o tamanho dos ícones. Ocultar manualmente libera a reserva; mostrar novamente a recria. O modo auto-ocultar continua sem reserva permanente.
- O posicionamento usa a área útil nativa para não depender de geometria em cache do Qt. Retomar uma instância oculta também reaplica a integração com o Windows.
- 40 testes aprovados no Windows. Validação adicional real em 1920 × 1200 com escala de 150%: três posições, janelas maximizadas, ocultar/mostrar e restauração após encerramento forçado. Registro em `docs/windows-validation.json` e prévia em `docs/dock-refined.png`. Múltiplos monitores e outras escalas ainda precisam de validação específica.

Referências: [AppBar](https://learn.microsoft.com/en-us/windows/win32/shell/application-desktop-toolbars) e [área útil por monitor](https://learn.microsoft.com/en-us/windows/win32/gdi/multiple-monitor-system-metrics).

## 0.2.1 — 7 de novembro de 2026

Corrige o caso em que a barra do Windows desaparece, mas as janelas continuam respeitando a faixa reservada para ela.

- A substituição da barra usa a API pública `ABM_SETSTATE` para ativar temporariamente o auto-ocultar do Windows, em vez de apenas esconder `Shell_TrayWnd`.
- O estado original é gravado antes de qualquer alteração e restaurado ao sair, ao mostrar a barra novamente, no vigia de encerramento inesperado e na recuperação manual.
- Ativações repetidas não sobrescrevem o estado original com o estado já alterado pelo próprio dock.
- Se o Windows já usava auto-ocultar, a preferência não é modificada.
- O posicionamento passa a respeitar a área útil publicada pelo Windows e aguarda sua atualização por temporizadores, sem bloquear a interface.
- “Reservar espaço para o dock” permanece independente. Desmarque para as janelas ocuparem toda a área disponível.
- Sete testes novos de regressão: 34 aprovados no total; um teste nativo pulado por exigir Windows. A correção ainda não foi verificada numa sessão real do Windows.

Atualização: feche o dock, substitua os arquivos da pasta do aplicativo pelo conteúdo desta versão e abra `INICIAR.bat`. Configurações e ambiente Python existentes são mantidos. Se usa executável, gere-o novamente com `GERAR_EXE.bat`.

Referências: [ABM_GETSTATE](https://learn.microsoft.com/en-us/windows/desktop/shell/abm-getstate) e [ABM_SETSTATE](https://learn.microsoft.com/en-us/windows/win32/shell/abm-setstate).
