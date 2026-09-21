<#
=============================================================================
 EchoScript - dal codice al file da mandare a qualcuno, in un comando solo.
=============================================================================
 Uso:
     .\costruisci.ps1
     .\costruisci.ps1 -Versione 1.1.0
     .\costruisci.ps1 -SoloInstallatore     (salta PyInstaller, riusa dist\)

 Risultato:
     installer\output\EchoScript-Setup.exe

 I due passaggi, e perche' sono due
 ----------------------------------
 1. PyInstaller legge il codice Python e ne fa un programma vero: EchoScript.exe
    piu' la cartella _internal con dentro l'interprete e tutte le librerie. Da
    qui in poi Python sul computer di chi lo usa non serve piu'.

 2. Inno Setup prende quella cartella e la chiude dentro un unico file di
    installazione. E' questo secondo passaggio a dare l'icona sul desktop, la
    voce in "App installate" e la disinstallazione pulita.

 Nessuno dei due fa il lavoro dell'altro: senza il primo non c'e' un programma
 da installare, senza il secondo c'e' una cartella che chi la riceve deve
 sistemarsi da se'.
=============================================================================
#>
[CmdletBinding()]
param(
    # Finisce nella voce di "App installate" e nelle proprieta' dell'eseguibile.
    # Va alzata a ogni versione pubblicata.
    #
    # NON finisce nel nome del file: quello resta sempre EchoScript-Setup.exe,
    # perche' l'indirizzo di scaricamento diretto pubblicato nel README funziona
    # solo se il nome non cambia fra una versione e l'altra. La spiegazione per
    # esteso sta in installer\EchoScript.iss, accanto a OutputBaseFilename.
    [string] $Versione = '3.0.0',

    # Per quando si sta lavorando sullo script di installazione e la cartella
    # dist\ e' gia' buona: PyInstaller ci mette dieci minuti, Inno Setup uno.
    [switch] $SoloInstallatore,

    # Salta la domanda di conferma quando trova roba da cancellare in dist\.
    [switch] $Forza
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Radice     = $PSScriptRoot
$Dist       = Join-Path $Radice 'dist\EchoScript'
$Spec       = Join-Path $Radice 'echoscriptapp.spec'
$Iss        = Join-Path $Radice 'installer\EchoScript.iss'
$Uscita     = Join-Path $Radice 'installer\output'

function Titolo($testo) { Write-Host "`n=== $testo ===" -ForegroundColor Cyan }
function Nota($testo)   { Write-Host "    $testo" -ForegroundColor DarkGray }
function Allarme($testo){ Write-Host "[!] $testo" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 0. Gli attrezzi ci sono?
# ---------------------------------------------------------------------------
Titolo 'Controlli preliminari'

if (-not (Test-Path $Spec)) { throw "Manca lo spec di PyInstaller: $Spec" }
if (-not (Test-Path $Iss))  { throw "Manca lo script di Inno Setup: $Iss" }

# ffmpeg: lo spec lo cerca nel PATH e lo INCORPORA nel pacchetto. Se qui non
# c'e', il pacchetto viene senza, e a chi lo installa servira' ffmpeg suo - che
# e' esattamente la scocciatura che questo installatore dovrebbe togliere di
# mezzo. Non e' un errore fatale, ma e' quasi sempre uno sbaglio.
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($null -eq $ffmpeg) {
    Allarme 'ffmpeg non e'' nel PATH: il pacchetto verra'' SENZA ffmpeg incorporato.'
    Allarme 'Installalo e ricostruisci:  winget install Gyan.FFmpeg'
} else {
    Nota "ffmpeg: $($ffmpeg.Source)"
}

# Inno Setup. Il suo compilatore si chiama ISCC.exe e di norma non e' nel PATH.
$Iscc = $null
$candidati = @(
    'iscc',
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($c in $candidati) {
    $trovato = Get-Command $c -ErrorAction SilentlyContinue
    if ($null -ne $trovato) { $Iscc = $trovato.Source; break }
}
if ($null -eq $Iscc) {
    Write-Host ''
    Allarme 'Inno Setup 6 non trovato. Installalo con:'
    Allarme '    winget install JRSoftware.InnoSetup'
    throw 'ISCC.exe mancante: senza il compilatore di Inno Setup non si produce l''installatore.'
}
Nota "Inno Setup: $Iscc"

# ---------------------------------------------------------------------------
# 1. PyInstaller
# ---------------------------------------------------------------------------
if ($SoloInstallatore) {
    Titolo 'PyInstaller (saltato: -SoloInstallatore)'
    if (-not (Test-Path (Join-Path $Dist 'EchoScript.exe'))) {
        throw "Non c'e' niente da riusare in $Dist. Rilancia senza -SoloInstallatore."
    }
} else {
    Titolo 'PyInstaller - dal codice al programma'
    # Si chiede a Python, non al PATH: pip installa il comando `pyinstaller` in
    # una cartella Scripts\ che su Windows spesso nel PATH non c'e', e cercarlo
    # li' lo farebbe reinstallare a ogni costruzione anche quando c'e' gia'.
    $versionePyInst = (python -m PyInstaller --version 2>$null)
    if ($LASTEXITCODE -ne 0) {
        Nota 'PyInstaller non trovato, lo installo...'
        python -m pip install --upgrade pyinstaller
        if ($LASTEXITCODE -ne 0) { throw 'Installazione di pyinstaller fallita.' }
    } else {
        Nota "PyInstaller: $versionePyInst"
    }
    Nota 'Circa 8 minuti sulla macchina di riferimento. E'' il passaggio lungo.'
    python -m PyInstaller $Spec --noconfirm --distpath (Join-Path $Radice 'dist') --workpath (Join-Path $Radice 'build')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller ha fallito: vedi il registro qui sopra.' }
}

if (-not (Test-Path (Join-Path $Dist 'EchoScript.exe'))) {
    throw "PyInstaller non ha prodotto $Dist\EchoScript.exe"
}

# ---------------------------------------------------------------------------
# 2. Ripulire dist\ da cio' che non deve essere spedito
# ---------------------------------------------------------------------------
# EchoScript scrive accanto a se'. Se qualcuno ha aperto dist\EchoScript.exe
# per una prova - e prima o poi capita sempre - in quella cartella sono rimaste
# le SUE preferenze e le SUE trascrizioni. Inno Setup impacchetta la cartella
# intera: senza questa pulizia finirebbero addosso a ogni persona che installa
# il programma.
Titolo 'Pulizia di dist\ prima di impacchettare'
$Intrusi = @('settings.json', 'results', '.env', '.pdfassets')
$Trovati = @()
foreach ($i in $Intrusi) {
    $p = Join-Path $Dist $i
    if (Test-Path $p) { $Trovati += $p }
}
if ($Trovati.Count -eq 0) {
    Nota 'Niente da togliere: la cartella e'' pulita.'
} else {
    Write-Host '    Roba di una prova precedente, non va spedita:' -ForegroundColor Yellow
    $Trovati | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
    $procedi = $Forza
    if (-not $procedi) {
        $risposta = Read-Host '    Cancellare? [S/n]'
        $procedi = ($risposta -eq '' -or $risposta -match '^[sSyY]')
    }
    if ($procedi) {
        $Trovati | ForEach-Object { Remove-Item $_ -Recurse -Force }
        Nota 'Fatto.'
    } else {
        throw 'Interrotto: con quei file dentro, l''installatore spedirebbe i tuoi dati.'
    }
}

# ---------------------------------------------------------------------------
# 3. Inno Setup
# ---------------------------------------------------------------------------
Titolo "Inno Setup - dal programma all'installatore (versione $Versione)"
& $Iscc "/DVersione=$Versione" $Iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup ha fallito: vedi il registro qui sopra.' }

# ---------------------------------------------------------------------------
# 4. Il risultato
# ---------------------------------------------------------------------------
$Prodotto = Join-Path $Uscita 'EchoScript-Setup.exe'
if (-not (Test-Path $Prodotto)) { throw "Atteso $Prodotto, non trovato." }

$Mb = [math]::Round((Get-Item $Prodotto).Length / 1MB, 1)
$Impronta = (Get-FileHash $Prodotto -Algorithm SHA256).Hash

Titolo 'Pronto'
Write-Host "    $Prodotto" -ForegroundColor Green
Write-Host "    $Mb MB" -ForegroundColor Green
Write-Host "    SHA256  $Impronta" -ForegroundColor DarkGray
Write-Host ''
Nota 'E'' il file da allegare alla release. Chi lo riceve fa doppio clic,'
Nota 'tre volte Avanti, e si ritrova l''icona di EchoScript sul desktop.'
Write-Host ''
