# Worker PowerShell nativo para Windows.Devices.Radios & NetworkOperatorTetheringManager
# Executa fora da thread de renderizacao e responde via stdin/stdout
param()

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function AwaitTask($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

[Windows.Devices.Radios.Radio, Windows.Devices.Radios, ContentType = WindowsRuntime] | Out-Null

function Get-RadiosJson {
    try {
        $radios = AwaitTask ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
        $list = @()
        foreach ($r in $radios) {
            $list += @{
                name = $r.Name
                kind = $r.Kind.ToString()
                state = $r.State.ToString()
            }
        }
        if ($list.Count -eq 0) {
            return "[]"
        }
        return (ConvertTo-Json -InputObject @($list) -Compress)
    } catch {
        return "[]"
    }
}

function Set-RadioState($targetKind, $targetState) {
    try {
        $radios = AwaitTask ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
        foreach ($r in $radios) {
            if ($r.Kind.ToString().Equals($targetKind, [System.StringComparison]::OrdinalIgnoreCase)) {
                $st = if ($targetState.Equals("On", [System.StringComparison]::OrdinalIgnoreCase)) {
                    [Windows.Devices.Radios.RadioState]::On
                } else {
                    [Windows.Devices.Radios.RadioState]::Off
                }
                $res = AwaitTask ($r.SetStateAsync($st)) ([Windows.Devices.Radios.RadioAccessStatus])
                return (@{
                    kind = $targetKind
                    requestedState = $targetState
                    result = $res.ToString()
                    actualState = $r.State.ToString()
                } | ConvertTo-Json -Compress)
            }
        }
        return '{"error":"RadioNotFound"}'
    } catch {
        return (@{ error = $_.Exception.Message } | ConvertTo-Json -Compress)
    }
}

function Request-Access {
    try {
        $acc = AwaitTask ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
        return $acc.ToString()
    } catch {
        return "DeniedBySystem"
    }
}

function Get-TetheringJson {
    try {
        [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime] | Out-Null
        [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
        $prof = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($prof -eq $null) {
            return '{"supported":false,"active":false,"state":"NoProfile"}'
        }
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($prof)
        $op = $tm.TetheringOperationalState.ToString()
        $isAct = ($op -eq "On")
        return (@{ supported = $true; active = $isAct; state = $op } | ConvertTo-Json -Compress)
    } catch {
        return '{"supported":false,"active":false,"state":"Unavailable"}'
    }
}

function Set-TetheringState($targetOn) {
    try {
        [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime] | Out-Null
        [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
        $prof = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($prof -eq $null) {
            return '{"supported":false,"active":false,"state":"NoProfile"}'
        }
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($prof)
        if ($targetOn -eq "On") {
            $res = AwaitTask ($tm.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        } else {
            $res = AwaitTask ($tm.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        }
        $op = $tm.TetheringOperationalState.ToString()
        return (@{ supported = $true; active = ($op -eq "On"); state = $op; result = $res.Status.ToString() } | ConvertTo-Json -Compress)
    } catch {
        return '{"supported":false,"active":false,"state":"Unavailable"}'
    }
}

# Inicialização e emissão do estado de prontidão
[Console]::Out.WriteLine("READY:$(Get-RadiosJson)")
[Console]::Out.Flush()

# Loop de escuta assíncrono via standard input
while ($line = [Console]::In.ReadLine()) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $line = $line.Trim()

    if ($line -eq "QUIT") {
        break
    }
    elseif ($line -eq "GET_RADIOS") {
        $json = Get-RadiosJson
        [Console]::Out.WriteLine("RADIOS:$json")
        [Console]::Out.Flush()
    }
    elseif ($line -like "SET:*") {
        $parts = $line.Split(":")
        if ($parts.Length -ge 3) {
            $k = $parts[1]
            $s = $parts[2]
            $res = Set-RadioState $k $s
            [Console]::Out.WriteLine("SET_RESULT:$res")
            [Console]::Out.Flush()
        }
    }
    elseif ($line -eq "REQUEST_ACCESS") {
        $accResult = Request-Access
        [Console]::Out.WriteLine("ACCESS:$accResult")
        [Console]::Out.Flush()
    }
    elseif ($line -eq "GET_TETHERING") {
        [Console]::Out.WriteLine("TETHERING:$(Get-TetheringJson)")
        [Console]::Out.Flush()
    }
    elseif ($line -like "SET_TETHERING:*") {
        $target = $line.Split(":")[1]
        [Console]::Out.WriteLine("TETHERING:$(Set-TetheringState $target)")
        [Console]::Out.Flush()
    }
}
