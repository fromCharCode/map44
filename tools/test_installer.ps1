# Map44 – Test des Kartendaten-Teils von install/install.ps1 (pwsh, auch unter Linux/macOS)
#
#   pwsh -NoProfile -File tools/test_installer.ps1 <release-ordner>
#
# Wird von tools/test_installer.sh mit dessen Schein-Releases (data-v1 … data-v3) aufgerufen. Lädt den Abschnitt
# zwischen den Kartendaten-Markern aus install.ps1, ersetzt Invoke-WebRequest durch Kopieren aus dem Release-Ordner
# und prüft dieselben Fälle wie der Shell-Test.
param([Parameter(Mandatory)] [string]$Rel)
$ErrorActionPreference = 'Stop'

class MockHttpException : System.Exception {
    $Response
    MockHttpException([int]$code) : base("HTTP $code") { $this.Response = [pscustomobject]@{ StatusCode = $code } }
}

$src = Get-Content -Raw (Join-Path $PSScriptRoot '../install/install.ps1')
$m = [regex]::Match($src, '(?s)# >>> Kartendaten[^\n]*\n(.*?)\n\s*# <<< Kartendaten')
if (-not $m.Success) { throw 'Kartendaten-Abschnitt in install.ps1 nicht gefunden' }
. ([ScriptBlock]::Create($m.Groups[1].Value))

$T = Join-Path ([IO.Path]::GetTempPath()) ("map44-pstest-" + [guid]::NewGuid())
$Repo = 'x/y'; $Api = 'https://api.github.com/repos/x/y/releases'
$Dest = Join-Path $T 'dest'; $Dl = Join-Path $T 'dl'
New-Item -ItemType Directory -Force -Path $Dest, $Dl | Out-Null
$script:MockHttp = 0; $script:FailZip = $false; $script:Legacy = $false

function Say($m) { }
function Assets($url) { $script:Legacy = $true; @() }
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    if ($script:MockHttp) { throw [MockHttpException]::new($script:MockHttp) }
    $f = Join-Path $Rel ($Uri -replace '^https://github.com/x/y/releases/download/', '')
    if ($script:FailZip -and $f.EndsWith('.zip')) { throw [MockHttpException]::new(500) }
    if (-not (Test-Path $f)) { throw [MockHttpException]::new(404) }
    Copy-Item $f $OutFile
}
function Start-Sleep { }
function Fail($msg) { Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue; Write-Host "FEHLER (ps1): $msg"; exit 1 }
function Ok($msg) { Write-Host "  ok (ps1): $msg" }
function Files {
    $d = Join-Path $Dest 'data'
    if (-not (Test-Path $d)) { return '' }
    $r = Get-ChildItem -Path $d -Recurse -File -Force | Where-Object { $_.FullName -notlike "*$([IO.Path]::DirectorySeparatorChar).packs$([IO.Path]::DirectorySeparatorChar)*" } |
        ForEach-Object { [IO.Path]::GetRelativePath($Dest, $_.FullName) -replace '\\', '/' }
    [string[]]$a = @($r); [Array]::Sort($a, [StringComparer]::Ordinal)
    return ($a -join ' ')
}
function Run($v) { InstallData $v }
$base = 'data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/city.json data/tiles/420_5670/city.json'

Run 'data-v1'
if ((Files) -ne 'data/MANIFEST data/VERSION data/streets.json data/tiles/410_5654/city.json data/tiles/412_5656/city.json data/tiles/414_5660/city.json') { Fail "Neuinstallation: $(Files)" }
Ok 'Neuinstallation'
Run 'data-v2'
if ((Files) -ne $base) { Fail "Teil-Update: $(Files)" }
if ((Get-Content (Join-Path $Dest 'data/tiles/414_5660/city.json')) -ne 'c2') { Fail 'Teil-Update: Inhalt' }
Ok 'Teil-Update'
Run 'data-v3'
if ((Get-Content (Join-Path $Dest 'data/streets.json')) -ne 'r3') { Fail 'Austausch aller Pakete' }
if (@(Get-ChildItem (Join-Path $Dest 'data/.packs')).Count -ne 3) { Fail 'Austausch aller Pakete: Dateilisten' }
Ok 'Austausch aller Pakete (.packs bleibt erhalten)'
Run 'data-v3'; Ok 'erneuter Lauf ohne Änderungen'

# Paket gleichen Namens neu veröffentlicht (Schein-Release data-v3r aus test_installer.sh)
Run 'data-v3r'
if ((Files) -ne 'data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/neu.json data/tiles/420_5670/city.json') { Fail "neu veröffentlichtes Paket: $(Files)" }
if (@(Get-Content (Join-Path $Dest 'data/MANIFEST') | Where-Object { ($_ -split '\s+')[2] -eq 'map44-data-v3-t414_5660.zip' }).Count -ne 1) { Fail 'neu veröffentlichtes Paket: doppelte Manifestzeile' }
Run 'data-v3'
if ((Files) -ne $base) { Fail "zurück auf data-v3: $(Files)" }
Ok 'Paket gleichen Namens mit neuem Inhalt ersetzt das alte vollständig'

# beschädigtes Manifest
$mfPath = Join-Path $Rel 'data-v3/map44-data-v3.manifest'
$orig = Get-Content -Raw $mfPath
foreach ($bad in @('', 'kaputt', $orig.Substring(0, 300))) {
    Set-Content -Path $mfPath -Value $bad -NoNewline
    Set-Content -Path (Join-Path $Dest 'data/VERSION') -Value 'data-v2' -NoNewline
    $err = $null
    try { Run 'data-v3' } catch { $err = "$_" }
    if ($err -notlike '*beschädigt*') { Fail "beschädigtes Manifest nicht abgelehnt: $err" }
    if ((Files) -ne $base) { Fail "beschädigtes Manifest hat Daten verändert: $(Files)" }
}
Set-Content -Path $mfPath -Value $orig -NoNewline
Ok 'leeres/beschädigtes/abgeschnittenes Manifest: Abbruch ohne Löschen'

# Reste abgebrochenen Entpackens, liegengebliebene Zips
New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'data/tiles/499_5699') | Out-Null
Set-Content (Join-Path $Dest 'data/tiles/499_5699/city.json') 'y'
Set-Content (Join-Path $Dest 'data/.packs/map44-data-v9-t499_5699.zip.files') 'data/tiles/499_5699/city.json'
Set-Content (Join-Path $Dl 'map44-data-v9-t499_5699.zip') 'z'
Set-Content (Join-Path $Dest 'data/VERSION') 'data-v2'
Run 'data-v3'
if (Test-Path (Join-Path $Dest 'data/tiles/499_5699')) { Fail 'Reste abgebrochenen Entpackens nicht entfernt' }
if (@(Get-ChildItem $Dl -Filter '*.zip').Count) { Fail 'liegengebliebene Zips' }
Ok 'Reste abgebrochenen Entpackens und alte Zips werden entfernt'

# data/.packs fehlt: kein Abbruch
Remove-Item -Recurse -Force (Join-Path $Dest 'data/.packs')
Set-Content (Join-Path $Dest 'data/VERSION') 'data-v2'
Run 'data-v3'
if (-not (Test-Path (Join-Path $Dest 'data/.packs'))) { Fail 'fehlendes .packs nicht neu angelegt' }
Ok 'fehlendes data/.packs wird neu angelegt'

# Umstieg von alter Installation mit abgebrochenem Download
Remove-Item -Recurse -Force (Join-Path $Dest 'data'), $Dl
New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'data'), $Dl | Out-Null
Set-Content (Join-Path $Dest 'data/alt.txt') 'alt'; Set-Content (Join-Path $Dest 'data/VERSION') 'data-v0'
$script:FailZip = $true
$failed = $false
try { Run 'data-v3' } catch { $failed = $true }
$script:FailZip = $false
if (-not $failed) { Fail 'abgebrochener Download hätte scheitern müssen' }
if ((Files) -ne 'data/VERSION data/alt.txt') { Fail "abgebrochener Umstieg hat Daten verändert: $(Files)" }
Ok 'Umstieg mit abgebrochenem Download lässt alte Daten stehen'
Run 'data-v3'
if ((Files) -ne $base) { Fail "Umstieg: $(Files)" }
Ok 'Umstieg von Installation ohne Manifest'

$err = $null
try { Run 'data-v0' } catch { $err = "$_" }
if (-not $script:Legacy -or $err -notlike '*nicht gefunden*') { Fail "404 führt nicht zum alten Verfahren: $err" }
Ok 'alte Datenversion (404) -> bisheriges Verfahren'
$script:MockHttp = 503; $err = $null
try { Run 'data-v3' } catch { $err = "$_" }
$script:MockHttp = 0
if ($err -notlike '*HTTP 503*') { Fail "Serverfehler nicht gemeldet: $err" }
Ok 'Serverfehler (503) bricht mit Meldung ab'

Remove-Item -Recurse -Force $T
Write-Host 'Alle ps1-Tests bestanden.'
