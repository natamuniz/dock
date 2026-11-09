# Doca 1.0.26: inspeção estática

Alvo: `C:\Program Files\WindowsApps\Racoelho.Doca_1.0.26.0_x64__z9dx3qx00ky50\Doca.exe`.
SHA-256: `05e1ad2b46a955af002320faa739bcb19ba2f21c78c86917733f9df3e2d0f95d`.

Esta inspeção não executou, modificou nem decompilou o Doca. Não copiou seus recursos gráficos ou código. Os nomes abaixo orientam perguntas de interoperabilidade; não são uma reconstrução da implementação.

## Evidências REA

| Evidência | Observação | Limite |
| --- | --- | --- |
| `ev_6f0f9bed2240e3991441df0f3435185f35a4e4e586855f3802f84856c333a8ed` — `rea-doca-imports.json` | PE32+ AMD64; 19 DLLs, 367 imports, nenhuma tabela delay-load. `USER32.dll` importa diretamente apenas `LoadStringW`. | Importações estáticas não estabelecem execução e não cobrem carregamento dinâmico por P/Invoke. |
| `ev_bc9b20e96d89395f67b888c2597b713c3373490e952cb1e8b2712d1e7d57b5d9` — `rea-doca-resources.json` | Árvore de recursos PE inventariada e identidades/hashes retidos. | Imagens e recursos opacos não foram usados ou copiados; relações de ícones não provam seu uso em tela. |
| `ev_87f5304e588da0e5cb285b9e4771bea34d38e3a082ce78482f587bb6ec72d084` — `rea-doca-managed.json` | O EXE não tem diretório CLI nem metadados CIL disponíveis. | Não pode ser tratado como assembly CIL decompilável pela rota gerenciada. |

## Observações por leitura comum de arquivos

Estas observações não são Evidence REA. Os arquivos JSON auxiliares identificam explicitamente o método de busca.

- `Doca.runtimeconfig.json`: declara `net10.0`, `Microsoft.NETCore.App` 10.0.14 e `RuntimeFeature.IsDynamicCodeSupported=false`.
- `Doca.deps.json`: declara Doca/1.0.26, Doca.Core/1.0.0, WindowsAppSDK/WinUI, WebView2, Microsoft.Data.Sqlite.Core e outras dependências.
- Em combinação com a ausência de CLI no EXE, isso é compatível com uma compilação NativeAOT. É uma inferência; o código nativo não foi reconstruído.
- Busca literal no EXE encontrou `SHAppBarMessage`, `SystemParametersInfoW`, `SetWindowPos`, `GetWindowPlacement`, `DwmSetWindowAttribute`, `DwmExtendFrameIntoClientArea`, APIs DWM de miniaturas e `RegisterHotKey`.
- Nomes retidos incluem `DockAppBar`, `AppBarGuard`, `SyncAppBar`, `ApplyReserveSpace`, `OnAppBarNotification`, `OnTaskbarCreated`, `WatchSystemVisibility`, `AutoHideTick`, `UpdateEdgeBarrier` e `get_ReserveWanted`.
- Nomes de apresentação incluem `DockChrome`, `DockItemPanel`, `DockFit`, `get_GlassHeight`, `get_Headroom`, `FitIconSize`, `GlassBackdrop`, `DesktopAcrylicController`, `SetBarPadding`, `BelowIcon`, `Press`, `FollowPointer`, `OutCubic` e `Spring`.
- Há nomes de opções `ReserveSpace`, `IconSize`, `Magnification`, `TaskbarMode`, `HideOtherWindows`, `EnvironmentDotsVisible`, `IndicatorEnvironmentColor`, `ShowTrash`, `ShowSettingsButton` e `CornerStyle`.

Os nomes podem vir de metadados preservados, projeções WinRT ou dependências. Sua presença não prova caminhos de chamada, valores, configuração atual ou comportamento observado.

## Consequências úteis para o NT Dock

1. Separar geometria do vidro, tamanho dos itens e espaço para ampliação é coerente com os nomes observados, mas os valores devem ser medidos na interface original.
2. Tratar a reserva como uma AppBar e reagir a mudanças do Explorer é uma hipótese apoiada pelos nomes; a sequência efetiva deve ser validada em execução.
3. O acabamento visual provavelmente utiliza composição/acrylic do Windows, em vez de somente um gradiente. O uso efetivo e a intensidade permanecem desconhecidos.
4. Alinhar tamanho, controles finais, indicadores, separadores e menu de ambientes pela observação visual evita depender de suposições sobre o código nativo.

Não foram observados: fórmulas de ampliação, constantes de layout, parâmetros de mola, temporizações, regras completas de ativação de janelas nem a sequência de chamadas de reserva/recuperação. Nenhum comportamento foi considerado equivalente apenas pela presença de uma string.
