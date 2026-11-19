# Map44 – Dresden: Installer für Windows 10/11 (x64)
#
#   irm https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.ps1 | iex
#
# Lädt die neueste Spielversion und die Kartendaten (~5 GB, einmalig) von GitHub-Releases, installiert nach
# %LOCALAPPDATA%\Map44 und legt Verknüpfungen im Startmenü und auf dem Desktop an. Erneut ausführen = Update
# (von den Kartendaten nur geänderte Pakete; abgebrochene Downloads werden fortgesetzt).
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

    # >>> Kartendaten (Hilfsfunktionen und Kartendaten-Logik; tools/test_installer.ps1 lädt diesen Abschnitt)
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

    # Kartendaten alter Datenversionen (ohne Manifest): alle Teile laden, data\ komplett ersetzen
    function LegacyData($need) {
        Say "Lade die Kartendaten $need (rund 5 GB, einmalig - das dauert je nach Leitung eine Weile) ..."
        $data = Assets "$Api/tags/$need"
        $dsum = $data | Where-Object { $_.name -eq "map44-$need.sha256" } | Select-Object -First 1
        $dsumFile = Join-Path $Dl 'data.sha256'
        if ($dsum) { Invoke-WebRequest -Uri $dsum.browser_download_url -OutFile $dsumFile -UseBasicParsing }
        $parts = @($data | Where-Object { $_.name -match "^map44-$([regex]::Escape($need))-\d+\.zip$" } | Sort-Object name)
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
        Set-Content -Path (Join-Path $dataDir 'VERSION') -Value $need -NoNewline
        if (-not $env:MAP44_KEEP_ZIPS) { foreach ($p in $parts) { Remove-Item -Force (Join-Path $Dl $p.name) } }
    }

    # Kartendaten inkrementell (Datenversionen mit Manifest): nur geänderte Pakete laden; entspricht dem
    # Kartendaten-Block in install.sh. Zustand in data\MANIFEST und data\.packs\<paket>.files (vor dem Entpacken
    # geschrieben), pro Schritt fortgeschrieben; gelöscht wird erst nach geprüftem Manifest und vollständigem Download.
    # Getestet von tools/test_installer.ps1 (pwsh).
    $ManifestLine = '^[0-9a-f]{64} [0-9]+ map44-[^ /\\]+\.zip [^ /\\]+( [0-9a-f]{64})?$'
    function ReadManifest($file) {
        $r = [ordered]@{}
        if (Test-Path $file) {
            foreach ($line in Get-Content $file) {
                $p = $line.Trim() -split '\s+'
                if ($p.Count -ge 4) { $r[$p[2]] = [pscustomobject]@{ Sha = $p[0].ToLower(); Size = [int64]$p[1]; Name = $p[2]; Tag = $p[3] } }
            }
        }
        return $r
    }
    function InstallData($need) {
        $dataDir = Join-Path $Dest 'data'
        $st = Join-Path $dataDir '.packs'
        $inst = Join-Path $dataDir 'MANIFEST'
        $mf = Join-Path $Dl 'data.manifest'
        $url = "https://github.com/$Repo/releases/download/$need/map44-$need.manifest"
        $ok = $false
        for ($try = 1; $try -le 5 -and -not $ok; $try++) {
            try {
                Invoke-WebRequest -Uri $url -OutFile $mf -UseBasicParsing
                $ok = $true
            } catch {
                $code = 0
                try { $code = [int]$_.Exception.Response.StatusCode } catch {}
                if ($code -eq 404) { LegacyData $need; return }
                if ($try -eq 5) { throw "Manifest der Kartendaten $need nicht abrufbar (HTTP $code) - bitte später erneut versuchen." }
                Start-Sleep -Seconds 3
            }
        }
        # Manifest prüfen, bevor irgendetwas gelöscht wird
        $lines = @(Get-Content $mf)
        if (-not $lines.Count -or @($lines | Where-Object { $_ -cnotmatch $ManifestLine }).Count) {
            throw "Manifest der Kartendaten $need ist leer oder beschädigt - nichts verändert."
        }
        $fresh = -not (Test-Path $inst)          # Installation ohne Manifest: einmal alles neu
        $want = ReadManifest $mf
        $have = if ($fresh) { [ordered]@{} } else { ReadManifest $inst }
        $todo = @($want.Values | Where-Object { -not $have.Contains($_.Name) -or $have[$_.Name].Sha -ne $_.Sha })
        # veraltet: installierte Pakete und Dateilisten (auch abgebrochener Entpackvorgänge), die das Manifest nicht nennt
        $gone = @()
        if (-not $fresh) {
            $names = @($have.Keys) + @(Get-ChildItem -Path $st -Filter '*.files' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name -replace '\.files$', '' })
            $gone = @($names | Sort-Object -Unique | Where-Object { -not $want.Contains($_) })
        }
        if ($todo.Count) {
            $mb = [math]::Round((($todo | Measure-Object -Property Size -Sum).Sum) / 1e6)
            Say "Lade die Kartendaten ${need}: $($todo.Count) Paket(e), rund $mb MB ..."
            $i = 0
            foreach ($p in $todo) {
                $i++
                Say "Kartendaten Teil $i/$($todo.Count) ($($p.Name))"
                Fetch "https://github.com/$Repo/releases/download/$($p.Tag)/$($p.Name)" (Join-Path $Dl $p.Name) $p.Sha
            }
        }
        # alles geladen - ab hier wird der Bestand verändert
        Remove-Item -Force (Join-Path $dataDir 'VERSION') -ErrorAction SilentlyContinue
        if ($fresh) {
            if (Test-Path $dataDir) { Remove-Item -Recurse -Force $dataDir }
            New-Item -ItemType Directory -Force -Path $st | Out-Null
            New-Item -ItemType File -Force -Path $inst | Out-Null
        }
        # veraltete Pakete entfernen; schlägt ein Löschen fehl (Datei gesperrt), bleiben Liste und Manifestzeile
        foreach ($name in $gone) {
            $list = Join-Path $st "$name.files"
            if (Test-Path $list) {
                foreach ($f in Get-Content $list) {
                    if (-not $f -or $f.EndsWith('/')) { continue }
                    $path = Join-Path $Dest $f
                    if (Test-Path -LiteralPath $path) {
                        try { Remove-Item -Force -LiteralPath $path -ErrorAction Stop }
                        catch { throw "Kann $path nicht löschen - läuft Map44 noch? Bitte beenden und den Installer erneut starten." }
                    }
                }
                Remove-Item -Force $list
            }
            $keep = @(Get-Content $inst | Where-Object { ($_ -split '\s+')[2] -ne $name })
            Set-Content -Path $inst -Value $keep
        }
        if ($gone.Count) {
            Get-ChildItem -Path $dataDir -Directory -Recurse | Where-Object { $_.FullName -ne (Get-Item $st).FullName } |
                Sort-Object { $_.FullName.Length } -Descending |
                Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } | Remove-Item -Force
        }
        # ... dann neue entpacken (Dateiliste zuerst, damit auch ein abgebrochenes Entpacken später aufgeräumt wird)
        New-Item -ItemType Directory -Force -Path $st | Out-Null
        if ($todo.Count) {
            Say 'Entpacke Kartendaten ...'
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            foreach ($p in $todo) {
                $zip = Join-Path $Dl $p.Name
                $z = [IO.Compression.ZipFile]::OpenRead($zip)
                try { Set-Content -Path (Join-Path $st "$($p.Name).files") -Value @($z.Entries | ForEach-Object { $_.FullName }) } finally { $z.Dispose() }
                Expand $zip $Dest
                $keep = @(Get-Content $inst | Where-Object { ($_ -split '\s+')[2] -ne $p.Name })
                Set-Content -Path $inst -Value ($keep + "$($p.Sha) $($p.Size) $($p.Name) $($p.Tag)")
                if (-not $env:MAP44_KEEP_ZIPS) { Remove-Item -Force $zip }
            }
        }
        # Reste abgebrochener Updates: Pakete, die das Manifest nicht nennt
        if (-not $env:MAP44_KEEP_ZIPS) {
            Get-ChildItem -Path $Dl -Filter 'map44-data-*.zip' -ErrorAction SilentlyContinue |
                Where-Object { -not $want.Contains($_.Name) } | Remove-Item -Force
        }
        Set-Content -Path (Join-Path $dataDir 'VERSION') -Value $need -NoNewline
    }
    # <<< Kartendaten

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
        InstallData $need
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
