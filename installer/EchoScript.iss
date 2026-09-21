; ============================================================================
;  EchoScript - script di installazione (Inno Setup 6)
; ============================================================================
;  Serve Inno Setup 6.3 o superiore  (winget install JRSoftware.InnoSetup).
;  Su una versione piu' vecchia si ferma su ArchitecturesAllowed=x64compatible,
;  che prima del 6.3 si chiamava x64 e non esisteva con questo nome.
;
;  Costruzione:  iscc installer\EchoScript.iss
;  Ma il modo giusto e' lanciare  .\costruisci.ps1  dalla radice del progetto:
;  fa prima PyInstaller e poi questo, che da solo non saprebbe cosa impacchettare.
;
;  Risultato:  installer\output\EchoScript-Setup-<versione>.exe
;              un file unico da mandare a chiunque.
;
;  COSA FA QUESTO FILE, E COSA NO
;  ------------------------------
;  Non costruisce niente. PyInstaller ha gia' prodotto dist\EchoScript\ con
;  dentro EchoScript.exe e la cartella _internal; qui quella cartella viene
;  compressa dentro un programma di installazione che la copia al posto giusto,
;  crea le scorciatoie, registra la voce in "App installate" e sa disinstallarsi.
;
;  La differenza per chi lo riceve e' tutta li': prima scaricava uno ZIP, doveva
;  estrarlo, doveva capire che _internal non si tocca e doveva crearsi la
;  scorciatoia a mano. Adesso fa doppio clic su un file e trova l'icona sul
;  desktop.
; ============================================================================

#define NomeApp          "EchoScript"
; La versione puo' arrivare da fuori  (iscc /DVersione=1.1.0 ...), ed e' cosi'
; che la passa costruisci.ps1. Il valore qui sotto e' solo la rete di sicurezza
; per chi lancia iscc a mano: senza #ifndef sovrascriverebbe quello ricevuto.
#ifndef Versione
  #define Versione       "1.0.0"
#endif
#define Autore           "Imkun-on"
#define SitoApp          "https://github.com/Imkun-on/EchoScript"
#define EseguibileApp    "EchoScript.exe"
; La cartella prodotta da PyInstaller, relativa a QUESTO file.
#define Sorgente         "..\dist\EchoScript"

[Setup]
; L'identita' del programma agli occhi di Windows. Non va MAI cambiata fra una
; versione e l'altra: e' con questa che l'installazione nuova riconosce quella
; vecchia e la sostituisce invece di affiancarsi.
AppId={{4724F349-E5FA-4BD4-9E44-4B8536B14C73}
AppName={#NomeApp}
AppVersion={#Versione}
AppVerName={#NomeApp} {#Versione}
AppPublisher={#Autore}
AppPublisherURL={#SitoApp}
AppSupportURL={#SitoApp}/issues
AppUpdatesURL={#SitoApp}/releases
VersionInfoVersion={#Versione}

; -- Dove si installa, e perche' proprio li' --------------------------------
; NON in "Programmi". Due motivi, e il secondo e' quello vero.
;
; Il primo: installare in "Programmi" richiede i diritti di amministratore, e
; su un computer aziendale o su quello di casa di qualcun altro spesso non ci
; sono. Con PrivilegesRequired=lowest non compare nemmeno la richiesta di
; Windows ("Vuoi consentire a questa app di apportare modifiche?"): si installa
; per l'utente che ha fatto doppio clic, e basta.
;
; Il secondo: EchoScript scrive accanto a se'. Le trascrizioni finiscono in
; results\, le preferenze in settings.json, i parziali in results\.checkpoints\.
; "Programmi" e' di sola lettura per un utente normale - installarlo li'
; significherebbe un programma che parte e poi non riesce a salvare niente.
; %LOCALAPPDATA%\Programs e' la cartella che Windows riserva esattamente a
; questo caso, ed e' scrivibile. E' anche dove si installano Visual Studio Code
; e parecchi altri.
;
; {autopf} con PrivilegesRequired=lowest vale %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#NomeApp}
DefaultGroupName={#NomeApp}
DisableProgramGroupPage=yes
; auto = la pagina "dove lo installo" compare la prima volta e sparisce agli
; aggiornamenti successivi, dove la risposta e' gia' nota ed e' sempre la stessa.
DisableDirPage=auto

; -- Il file prodotto -------------------------------------------------------
OutputDir=output
OutputBaseFilename={#NomeApp}-Setup-{#Versione}
SetupIconFile=..\assets\EchoScript.ico
LicenseFile=..\LICENSE
; lzma2/max: il pacchetto e' grosso (ffmpeg da solo sono 400 MB) e il tempo di
; compressione si paga una volta sola, in costruzione. Chi scarica ringrazia.
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
ShowLanguageDialog=auto
UninstallDisplayIcon={app}\{#EseguibileApp}
UninstallDisplayName={#NomeApp}

[Languages]
Name: "italiano"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[CustomMessages]
italiano.CreaIconaDesktop=Crea un'icona sul &desktop
italiano.GruppoScorciatoie=Scorciatoie aggiuntive:
italiano.ApriRisultati=Trascrizioni salvate
italiano.AvviaOra=Avvia {#NomeApp}
italiano.WebView2Titolo=Componente di Windows mancante
italiano.WebView2Testo=A {#NomeApp} serve WebView2, il componente con cui Windows disegna la finestra del programma. Non risulta installato su questo computer: verra' scaricato da Microsoft (circa 2 MB) e installato insieme all'app.
italiano.WebView2Installo=Installazione di WebView2 in corso...
italiano.WebView2Fallito=Non e' stato possibile scaricare WebView2 (probabilmente manca la connessione). L'installazione prosegue, ma se la finestra del programma non si apre, installa "Microsoft Edge WebView2 Runtime" dal sito Microsoft e riprova.
italiano.RimuoviDati=Vuoi cancellare anche le trascrizioni e le preferenze salvate?%n%nSe rispondi No restano nella cartella:%n%1
english.CreaIconaDesktop=Create a &desktop icon
english.GruppoScorciatoie=Additional shortcuts:
english.ApriRisultati=Saved transcriptions
english.AvviaOra=Launch {#NomeApp}
english.WebView2Titolo=Missing Windows component
english.WebView2Testo={#NomeApp} needs WebView2, the component Windows uses to draw the program window. It is not installed on this computer: it will be downloaded from Microsoft (about 2 MB) and installed along with the app.
english.WebView2Installo=Installing WebView2...
english.WebView2Fallito=WebView2 could not be downloaded (most likely there is no connection). Setup will continue, but if the program window does not open, install "Microsoft Edge WebView2 Runtime" from the Microsoft site and try again.
english.RimuoviDati=Do you also want to delete the saved transcriptions and preferences?%n%nIf you answer No they stay in:%n%1

[Tasks]
; Spuntata di suo: e' il motivo per cui esiste un programma di installazione
; invece di uno ZIP - l'icona sul desktop senza doversela creare.
Name: "desktopicon"; Description: "{cm:CreaIconaDesktop}"; GroupDescription: "{cm:GruppoScorciatoie}"

[InstallDelete]
; Via la _internal della versione precedente PRIMA di copiare la nuova.
;
; PyInstaller ci mette dentro i file della libreria uno per uno, e i nomi
; cambiano fra una versione e l'altra di ogni dipendenza. Senza questa riga i
; file vecchi resterebbero accanto ai nuovi: nessuno li sovrascrive, perche'
; l'installazione copia solo cio' che porta con se'. Python poi ne caricherebbe
; un misto, e il guasto che ne esce non assomiglia a niente.
;
; Non tocca niente di chi usa il programma: dentro _internal c'e' soltanto la
; libreria impacchettata. Le trascrizioni, le preferenze e il file .env stanno
; un livello sopra, accanto a EchoScript.exe, e restano dove sono.
Type: filesandordirs; Name: "{app}\_internal"

[Dirs]
; Creata subito, vuota, cosi' la scorciatoia "Trascrizioni salvate" del menu
; Start apre qualcosa anche prima della prima trascrizione.
Name: "{app}\results"

[Files]
; Tutta dist\EchoScript\, cosi' com'e'.
;
; Gli Excludes sono la seconda rete di sicurezza (la prima e' in costruisci.ps1):
; se qualcuno ha aperto dist\EchoScript.exe per una prova, in quella cartella
; sono rimaste le SUE preferenze e le SUE trascrizioni, e da qui finirebbero
; addosso a chiunque installi il programma. La barra iniziale ancora le al
; livello piu' alto della cartella sorgente.
Source: "{#Sorgente}\*"; DestDir: "{app}"; \
    Excludes: "\settings.json,\.env,\results,\.pdfassets"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; Il programma di installazione di WebView2 viene scaricato al volo (vedi
; [Code]): nel pacchetto non c'e', e infatti qui non lo si cerca sul disco.

[Icons]
Name: "{group}\{#NomeApp}";         Filename: "{app}\{#EseguibileApp}"; IconFilename: "{app}\_internal\assets\EchoScript.ico"
Name: "{group}\{cm:ApriRisultati}"; Filename: "{app}\results"
Name: "{autodesktop}\{#NomeApp}";   Filename: "{app}\{#EseguibileApp}"; IconFilename: "{app}\_internal\assets\EchoScript.ico"; Tasks: desktopicon

[Run]
; WebView2 per primo: se manca, la finestra del programma non si aprirebbe.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
    StatusMsg: "{cm:WebView2Installo}"; Flags: waituntilterminated; Check: ServeWebView2
Filename: "{app}\{#EseguibileApp}"; Description: "{cm:AvviaOra}"; \
    Flags: nowait postinstall skipifsilent

[Code]
var
  PaginaScarico: TDownloadWizardPage;
  WebView2Assente: Boolean;
  ScaricoRiuscito: Boolean;

{ --- C'e' WebView2 su questo computer? ------------------------------------ }
{ Microsoft registra il runtime "Evergreen" sotto un GUID fisso. Tre posti da
  guardare: due per l'installazione di sistema (a 64 e a 32 bit) e uno per
  quella del singolo utente, che e' proprio quella che faremmo noi se manca. }
function WebView2Installato(): Boolean;
var
  versione: String;
  clienti: String;
begin
  clienti := 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result :=
    (RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SOFTWARE\WOW6432Node\' + clienti, 'pv', versione) and (versione <> '') and (versione <> '0.0.0.0')) or
    (RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SOFTWARE\' + clienti,             'pv', versione) and (versione <> '') and (versione <> '0.0.0.0')) or
    (RegQueryStringValue(HKEY_CURRENT_USER,  'SOFTWARE\' + clienti,             'pv', versione) and (versione <> '') and (versione <> '0.0.0.0'));
end;

{ Usata dalla sezione [Run]: lancia il runtime solo se mancava E se il file e'
  davvero arrivato. Su Windows 11 non si verifica mai nessuna delle due. }
function ServeWebView2(): Boolean;
begin
  Result := WebView2Assente and ScaricoRiuscito;
end;

function AvanzamentoScarico(const Url, NomeFile: String; const Fatto, Totale: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  WebView2Assente := not WebView2Installato();
  ScaricoRiuscito := False;
  PaginaScarico := CreateDownloadPage(
    ExpandConstant('{cm:WebView2Titolo}'),
    ExpandConstant('{cm:WebView2Testo}'),
    @AvanzamentoScarico);
end;

{ Lo scarico avviene DOPO il riepilogo e PRIMA di copiare i file: e' l'unico
  punto in cui si puo' ancora mostrare una barra di avanzamento propria.
  Se fallisce non si interrompe niente - su una macchina senza rete il resto
  dell'installazione e' comunque valido, e su Windows 11 il programma partira'
  lo stesso perche' WebView2 c'e' gia' di fabbrica. }
function NextButtonClick(PaginaCorrente: Integer): Boolean;
begin
  Result := True;
  if (PaginaCorrente = wpReady) and WebView2Assente then
  begin
    PaginaScarico.Clear;
    PaginaScarico.Add(
      'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
      'MicrosoftEdgeWebview2Setup.exe', '');
    PaginaScarico.Show;
    try
      try
        PaginaScarico.Download;
        ScaricoRiuscito := True;
      except
        ScaricoRiuscito := False;
        MsgBox(ExpandConstant('{cm:WebView2Fallito}'), mbInformation, MB_OK);
      end;
    finally
      PaginaScarico.Hide;
    end;
  end;
end;

{ --- Disinstallazione ------------------------------------------------------ }
{ Windows toglie solo cio' che l'installazione aveva messo. Le trascrizioni e le
  preferenze sono nate dopo, quindi resterebbero li' in silenzio: meglio
  chiedere, invece di cancellarle senza dire niente o di lasciare una cartella
  che nessuno sa piu' cos'e'. }
procedure CurUninstallStepChanged(Passo: TUninstallStep);
var
  cartella: String;
begin
  if Passo = usPostUninstall then
  begin
    cartella := ExpandConstant('{app}');
    if DirExists(cartella) then
      if MsgBox(FmtMessage(ExpandConstant('{cm:RimuoviDati}'), [cartella]),
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(cartella, True, True, True);
  end;
end;
