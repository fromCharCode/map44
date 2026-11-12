# Map44 – Dresden: Installer für Windows 10/11 (x64)
#
#   irm https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.ps1 | iex
#
# Lädt die neueste Spielversion und die Kartendaten (~5 GB, einmalig) von GitHub-Releases, installiert nach
# %LOCALAPPDATA%\Map44 und legt Verknüpfungen im Startmenü und auf dem Desktop an. Erneut ausführen = Update
# (Kartendaten nur bei neuer Datenversion; abgebrochene Downloads werden fortgesetzt).
# Deinstallieren: Ordner %LOCALAPPDATA%\Map44 und die Verknüpfungen "Map44 Dresden" löschen.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $Repo = 'fromCharCode/map44'
    $Api = "https://api.github.com/repos/$Repo/releases"
    $Dest = if ($env:MAP44_HOME) { $env:MAP44_HOME } else { Join-Path $env:LOCALAPPDATA 'Map44' }
    $Dl = Join-Path $Dest '.downloads'
    New-Item -ItemType Directory -Force -Path $Dl | Out-Null

    function Say($m) { Write-Host "==> $m" -ForegroundColor Yellow }
    function Assets($url) { (Invoke-RestMethod -Uri $url -Headers @{ 'User-Agent' = 'map44-installer'; 'Accept' = 'application/vnd.github+json' }).assets }
    function Sha($file) { (Get-FileHash -Algorithm SHA256 -Path $file).Hash.ToLower() }
    function SumOf($sumFile, $name) {
        if (-not (Test-Path $sumFile)) { return $null }
        foreach ($line in Get-Content $sumFile) {
            $p = $line -split '\s+'
            if ($p.Count -ge 2 -and $p[1] -eq $name) { return $p[0].ToLower() }
        }
        return $null
    }
    function Fetch($url, $out, $sum) {
        if ($sum -and (Test-Path $out) -and ((Sha $out) -eq $sum)) { return }
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        for ($try = 1; $try -le 3; $try++) {
            if ($curl) {
                & curl.exe -fL --retry 5 --retry-delay 3 -C - --progress-bar -o $out $url
            } else {
                Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
            }
            if (-not $sum -or ((Test-Path $out) -and ((Sha $out) -eq $sum))) { return }
            Say "Prüfsumme falsch, lade $(Split-Path $out -Leaf) neu (Versuch $try) ..."
            Remove-Item -Force $out -ErrorAction SilentlyContinue
        }
        throw "Download fehlgeschlagen: $url"
    }
    function Expand($zip, $to) {
        $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
        if ($tar) {
            & tar.exe -xf $zip -C $to
            if ($LASTEXITCODE -ne 0) { throw "Entpacken fehlgeschlagen: $zip" }
        } else {
            Expand-Archive -Path $zip -DestinationPath $to -Force
        }
    }

    Say 'Suche die neueste Version ...'
    $game = Assets "$Api/latest"
    $gz = $game | Where-Object { $_.name -eq 'map44-windows-x86_64.zip' } | Select-Object -First 1
    if (-not $gz) { throw 'Keine Windows-Version im neuesten Release gefunden.' }
    $sums = $game | Where-Object { $_.name -eq 'SHA256SUMS' } | Select-Object -First 1
    $sumFile = Join-Path $Dl 'SHA256SUMS'
    if ($sums) { Invoke-WebRequest -Uri $sums.browser_download_url -OutFile $sumFile -UseBasicParsing }

    Say 'Lade das Spiel ...'
    $gzip = Join-Path $Dl $gz.name
    Fetch $gz.browser_download_url $gzip (SumOf $sumFile $gz.name)
    Expand $gzip $Dest
    if (-not $env:MAP44_KEEP_ZIPS) { Remove-Item -Force $gzip }

    $need = (Get-Content (Join-Path $Dest 'DATA_VERSION') -Raw).Trim()
    $verFile = Join-Path $Dest 'data\VERSION'
    $have = if (Test-Path $verFile) { (Get-Content $verFile -Raw).Trim() } else { '' }
    if ($need -ne $have) {
        Say "Lade die Kartendaten $need (rund 5 GB, einmalig - das dauert je nach Leitung eine Weile) ..."
        $data = Assets "$Api/tags/$need"
        $dsum = $data | Where-Object { $_.name -eq "map44-$need.sha256" } | Select-Object -First 1
        $dsumFile = Join-Path $Dl 'data.sha256'
        if ($dsum) { Invoke-WebRequest -Uri $dsum.browser_download_url -OutFile $dsumFile -UseBasicParsing }
        $parts = $data | Where-Object { $_.name -match "^map44-$([regex]::Escape($need))-\d+\.zip$" } | Sort-Object name
        if (-not $parts) { throw "Kartendaten $need nicht gefunden." }
        $i = 0
        foreach ($p in $parts) {
            $i++
            Say "Kartendaten Teil $i/$($parts.Count)"
            Fetch $p.browser_download_url (Join-Path $Dl $p.name) (SumOf $dsumFile $p.name)
        }
        Say 'Entpacke Kartendaten ...'
        $dataDir = Join-Path $Dest 'data'
        if (Test-Path $dataDir) { Remove-Item -Recurse -Force $dataDir }
        foreach ($p in $parts) { Expand (Join-Path $Dl $p.name) $Dest }
        Set-Content -Path $verFile -Value $need -NoNewline
        if (-not $env:MAP44_KEEP_ZIPS) { foreach ($p in $parts) { Remove-Item -Force (Join-Path $Dl $p.name) } }
    } else {
        Say "Kartendaten $have sind aktuell."
    }

    # Verknüpfungen
    $exe = Join-Path $Dest 'map44.exe'
    $ws = New-Object -ComObject WScript.Shell
    foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
        $lnk = $ws.CreateShortcut((Join-Path $dir 'Map44 Dresden.lnk'))
        $lnk.TargetPath = $exe
        $lnk.WorkingDirectory = $Dest
        $lnk.Save()
    }
    Say 'Fertig! Start über das Startmenü oder die Desktop-Verknüpfung "Map44 Dresden".'
    Say 'Hinweis: Beim ersten Start kann Windows SmartScreen warnen (Spiel ist nicht signiert) -> "Weitere Informationen" -> "Trotzdem ausführen".'
}
