# Worker PowerShell para sessoes de midia do Windows (SMTC)
# Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager
# Emite no stdout apenas quando o estado muda:
#   READY:<json>      estado inicial
#   MEDIA:<json>      {playing, status, app, title, artist}
#   CMD_RESULT:<json> resultado de comando
# Comandos via stdin: play_pause | next | prev | refresh | exit
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function AwaitTask($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(4000) | Out-Null
    return $netTask.Result
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null

$manager = $null
try {
    $manager = AwaitTask ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
} catch {
    [Console]::Out.WriteLine('READY:{"playing":false,"status":"Unavailable","app":"","title":"","artist":"","error":"SMTC indisponivel"}')
    [Console]::Out.Flush()
    exit 0
}

function Get-ActiveSession {
    # Prioriza qualquer sessao efetivamente em Playing; senao, a sessao atual do sistema
    try {
        $sessions = $manager.GetSessions()
        foreach ($s in $sessions) {
            try {
                if ($s.GetPlaybackInfo().PlaybackStatus.ToString() -eq "Playing") { return $s }
            } catch {}
        }
        return $manager.GetCurrentSession()
    } catch { return $null }
}

$script:lastKey = ""
$script:lastPropsAt = [DateTime]::MinValue
$script:cachedTitle = ""
$script:cachedArtist = ""
$script:cachedSessionId = ""

function Get-State([bool]$forceProps) {
    $s = Get-ActiveSession
    if ($null -eq $s) {
        return @{ playing = $false; status = "Closed"; app = ""; title = ""; artist = "" }
    }
    $status = "Closed"
    try { $status = $s.GetPlaybackInfo().PlaybackStatus.ToString() } catch {}
    $appId = ""
    try { $appId = $s.SourceAppUserModelId } catch {}

    $now = [DateTime]::UtcNow
    $needProps = $forceProps -or ($appId -ne $script:cachedSessionId) -or (($status -eq "Playing") -and (($now - $script:lastPropsAt).TotalMilliseconds -gt 1500))
    if ($needProps) {
        try {
            $props = AwaitTask ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
            if ($props) {
                $script:cachedTitle = [string]$props.Title
                $script:cachedArtist = [string]$props.Artist
            }
        } catch {}
        $script:cachedSessionId = $appId
        $script:lastPropsAt = $now
    }
    return @{
        playing = ($status -eq "Playing")
        status = $status
        app = $appId
        title = $script:cachedTitle
        artist = $script:cachedArtist
    }
}

function Emit-IfChanged($prefix, [bool]$force) {
    $st = Get-State $force
    $json = ($st | ConvertTo-Json -Compress)
    if ($force -or $json -ne $script:lastKey) {
        $script:lastKey = $json
        [Console]::Out.WriteLine("$($prefix):$json")
        [Console]::Out.Flush()
    }
}

function Invoke-Command($cmd) {
    $s = Get-ActiveSession
    if ($null -eq $s) { return '{"ok":false,"error":"NoSession"}' }
    try {
        $op = switch ($cmd) {
            "play_pause" { $s.TryTogglePlayPauseAsync() }
            "next"       { $s.TrySkipNextAsync() }
            "prev"       { $s.TrySkipPreviousAsync() }
        }
        $ok = AwaitTask $op ([bool])
        return (@{ ok = [bool]$ok; cmd = $cmd } | ConvertTo-Json -Compress)
    } catch {
        return (@{ ok = $false; cmd = $cmd; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    }
}

Emit-IfChanged "READY" $true

$stdin = [Console]::In
$pending = $stdin.ReadLineAsync()
while ($true) {
    if ($pending.IsCompleted) {
        $line = $pending.Result
        if ($null -eq $line) { break }
        $line = $line.Trim()
        if ($line -eq "exit") { break }
        if ($line -in @("play_pause", "next", "prev")) {
            $res = Invoke-Command $line
            [Console]::Out.WriteLine("CMD_RESULT:$res")
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 150
            Emit-IfChanged "MEDIA" $true
        } elseif ($line -eq "refresh") {
            Emit-IfChanged "MEDIA" $true
        }
        $pending = $stdin.ReadLineAsync()
    }
    Emit-IfChanged "MEDIA" $false
    Start-Sleep -Milliseconds 350
}
