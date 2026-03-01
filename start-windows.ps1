param(
    [switch]$CheckOnly,
    [switch]$ReinstallDeps
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$scriptDir = Split-Path -Parent $PSCommandPath
$logFile = Join-Path $scriptDir 'start-windows-last.log'
$venvDir = Join-Path $scriptDir 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirements = Join-Path $scriptDir 'requirements.txt'
$appPath = Join-Path $scriptDir 'app.py'

if (Test-Path $logFile) {
    Remove-Item $logFile -Force -ErrorAction SilentlyContinue
}

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter()][string[]]$Arguments = @(),
        [switch]$IgnoreExitCode,
        [switch]$Quiet
    )

    $previousEap = $ErrorActionPreference
    $previousNativeEap = $null
    if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
        $previousNativeEap = $Global:PSNativeCommandUseErrorActionPreference
        $Global:PSNativeCommandUseErrorActionPreference = $false
    }

    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& $Command @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousEap
        if ($null -ne $previousNativeEap) {
            $Global:PSNativeCommandUseErrorActionPreference = $previousNativeEap
        }
    }

    $lines = @($output | ForEach-Object { $_.ToString() })
    if (-not $Quiet) {
        foreach ($line in $lines) {
            Write-Log $line
        }
    }

    if (-not $IgnoreExitCode -and $exitCode -ne 0) {
        throw "Command failed ($exitCode): $Command $($Arguments -join ' ')"
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        Lines = $lines
    }
}

function Test-PortAvailable {
    param(
        [Parameter(Mandatory = $true)][int]$Port
    )

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Resolve-WebPort {
    $requested = 5000
    if ($env:WEBUI_PORT -and ($env:WEBUI_PORT -as [int])) {
        $requested = [int]$env:WEBUI_PORT
    }

    $candidates = @($requested, 5000, 5001, 5002, 5050, 5080, 18080) | Select-Object -Unique
    foreach ($port in $candidates) {
        if (Test-PortAvailable -Port $port) {
            return $port
        }
    }
    throw 'No available localhost port found for WebUI.'
}

function Resolve-BinaryName {
    param(
        [Parameter(Mandatory = $true)][string]$ServiceDir
    )

    $candidates = @('cli-proxy-api.exe', 'CLIProxyAPI.exe', 'cli-proxy-api', 'CLIProxyAPI')
    foreach ($name in $candidates) {
        $fullPath = Join-Path $ServiceDir $name
        if (Test-Path $fullPath) {
            return $name
        }
    }

    return 'CLIProxyAPI'
}

function Resolve-ConfigFromInstallDir {
    param(
        [Parameter(Mandatory = $true)][string]$InstallDir
    )

    $configPath = Join-Path $InstallDir 'config.yaml'
    if (Test-Path $configPath) {
        return $configPath
    }
    return $null
}

function Auto-DetectCliProxyApiConfig {
    $sources = @()

    if ($env:CLIPROXYAPI_DIR) {
        $sources += [PSCustomObject]@{
            Name = 'CLIPROXYAPI_DIR'
            Dir  = $env:CLIPROXYAPI_DIR
        }
    }

    $sources += [PSCustomObject]@{
        Name = 'DefaultInstallDir'
        Dir  = (Join-Path $env:USERPROFILE 'cliproxyapi')
    }

    $sources += [PSCustomObject]@{
        Name = 'SiblingSourceDir'
        Dir  = (Join-Path $scriptDir '..\CLIProxyAPI')
    }

    foreach ($src in $sources) {
        if (-not $src.Dir) {
            continue
        }
        $configPath = Resolve-ConfigFromInstallDir -InstallDir $src.Dir
        if ($configPath) {
            return [PSCustomObject]@{
                Source = $src.Name
                InstallDir = (Resolve-Path $src.Dir).Path
                ConfigPath = (Resolve-Path $configPath).Path
            }
        }
    }

    return $null
}

function Configure-CliProxyApiEnvironment {
    $hasExplicitConfig = $false
    if ($env:CPA_CONFIG_PATH -and (Test-Path $env:CPA_CONFIG_PATH)) {
        $resolvedConfig = (Resolve-Path $env:CPA_CONFIG_PATH).Path
        $env:CPA_CONFIG_PATH = $resolvedConfig
        $hasExplicitConfig = $true
        Write-Log "INFO  Using existing CPA_CONFIG_PATH: $resolvedConfig"
    }

    if (-not $hasExplicitConfig) {
        $detected = Auto-DetectCliProxyApiConfig
        if ($detected) {
            $env:CPA_CONFIG_PATH = $detected.ConfigPath
            if (-not $env:CPA_SERVICE_DIR) {
                $env:CPA_SERVICE_DIR = $detected.InstallDir
            }
            Write-Log "INFO  Auto-detected CLIProxyAPI config from $($detected.Source): $($detected.ConfigPath)"
        }
        else {
            Write-Log 'WARN  CLIProxyAPI config not auto-detected; app.py will use defaults.'
        }
    }

    if ($env:CPA_CONFIG_PATH -and (-not $env:CPA_SERVICE_DIR)) {
        $env:CPA_SERVICE_DIR = Split-Path -Parent $env:CPA_CONFIG_PATH
    }

    if ($env:CPA_SERVICE_DIR) {
        $env:CPA_SERVICE_DIR = (Resolve-Path $env:CPA_SERVICE_DIR).Path
        if (-not $env:CPA_BINARY_NAME) {
            $env:CPA_BINARY_NAME = Resolve-BinaryName -ServiceDir $env:CPA_SERVICE_DIR
            Write-Log "INFO  Auto-selected CPA_BINARY_NAME: $($env:CPA_BINARY_NAME)"
        }
        if (-not $env:CPA_LOG_FILE) {
            $env:CPA_LOG_FILE = Join-Path $env:CPA_SERVICE_DIR 'cliproxyapi.log'
        }
    }

    if ($env:CPA_CONFIG_PATH) { Write-Log "INFO  Effective CPA_CONFIG_PATH: $($env:CPA_CONFIG_PATH)" }
    if ($env:CPA_SERVICE_DIR) { Write-Log "INFO  Effective CPA_SERVICE_DIR: $($env:CPA_SERVICE_DIR)" }
    if ($env:CPA_BINARY_NAME) { Write-Log "INFO  Effective CPA_BINARY_NAME: $($env:CPA_BINARY_NAME)" }
    if ($env:CPA_LOG_FILE) { Write-Log "INFO  Effective CPA_LOG_FILE: $($env:CPA_LOG_FILE)" }
}

function Find-SystemPython {
    $candidates = @(
        @('py', '-3'),
        @('python', ''),
        @('python3', '')
    )

    foreach ($candidate in $candidates) {
        $cmd = $candidate[0]
        $arg = $candidate[1]
        try {
            if ($arg -ne '') {
                $null = & $cmd $arg --version 2>$null
            } else {
                $null = & $cmd --version 2>$null
            }
            if ($LASTEXITCODE -eq 0) {
                return [PSCustomObject]@{ Command = $cmd; Arg = $arg }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Ensure-Venv {
    param($SystemPython)

    if (Test-Path $venvPython) {
        Write-Log "INFO  Virtual env exists: $venvDir"
        return
    }

    Write-Log "INFO  Creating virtual env: $venvDir"
    if ($SystemPython.Arg -ne '') {
        Invoke-Native -Command $SystemPython.Command -Arguments @($SystemPython.Arg, '-m', 'venv', $venvDir) | Out-Null
    } else {
        Invoke-Native -Command $SystemPython.Command -Arguments @('-m', 'venv', $venvDir) | Out-Null
    }
    if (-not (Test-Path $venvPython)) {
        throw 'Failed to create virtual environment.'
    }
}

function Test-PythonPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Package
    )

    $res = Invoke-Native -Command $venvPython -Arguments @('-m', 'pip', '--disable-pip-version-check', 'show', $Package) -IgnoreExitCode -Quiet
    return $res.ExitCode -eq 0
}

function Ensure-Dependencies {
    if (-not (Test-Path $requirements)) {
        throw "Missing requirements file: $requirements"
    }

    if ($ReinstallDeps) {
        Write-Log 'INFO  ReinstallDeps enabled, installing requirements...'
        Invoke-Native -Command $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') | Out-Null
        Invoke-Native -Command $venvPython -Arguments @('-m', 'pip', 'install', '-r', $requirements) | Out-Null
        return
    }

    $requiredPackages = @('flask', 'requests', 'PyYAML', 'psutil')
    $missing = @()
    foreach ($pkg in $requiredPackages) {
        if (-not (Test-PythonPackage -Package $pkg)) {
            $missing += $pkg
        }
    }

    if ($missing.Count -eq 0) {
        Write-Log 'INFO  Dependencies already installed.'
        return
    }

    Write-Log ("INFO  Missing packages: {0}" -f ($missing -join ', '))

    Write-Log 'INFO  Installing requirements...'
    Invoke-Native -Command $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') | Out-Null
    Invoke-Native -Command $venvPython -Arguments @('-m', 'pip', 'install', '-r', $requirements) | Out-Null
}

try {
    Write-Log 'INFO  CPA-Dashboard Windows launcher started.'
    Write-Log "INFO  Script dir: $scriptDir"
    Write-Log "INFO  Log file: $logFile"
    Write-Log "INFO  CheckOnly: $CheckOnly"
    Write-Log "INFO  ReinstallDeps: $ReinstallDeps"

    $osBuild = [Environment]::OSVersion.Version.Build
    if ($osBuild -lt 10240) {
        Write-Log "ERROR Unsupported Windows build: $osBuild"
        Write-Log 'HINT  This launcher supports Windows 10/11 only.'
        exit 1
    }
    Write-Log "INFO  Windows build: $osBuild"

    if (-not (Test-Path $appPath)) {
        Write-Log "ERROR Missing app file: $appPath"
        exit 1
    }

    $systemPython = Find-SystemPython
    if (-not $systemPython) {
        Write-Log 'ERROR Python 3 was not found on this system.'
        Write-Log 'HINT  Install Python 3.10+ and enable PATH.'
        exit 1
    }
    Write-Log "INFO  System Python command: $($systemPython.Command) $($systemPython.Arg)"

    Configure-CliProxyApiEnvironment

    Ensure-Venv -SystemPython $systemPython
    Ensure-Dependencies

    if ($CheckOnly) {
        Write-Log 'INFO  CheckOnly passed. Service not started.'
        exit 0
    }

    $selectedPort = Resolve-WebPort
    $env:WEBUI_PORT = "$selectedPort"
    Write-Log "INFO  Selected WEBUI_PORT: $selectedPort"
    Write-Log ("INFO  Open in browser: http://127.0.0.1:{0}" -f $selectedPort)
    Write-Log 'INFO  Starting app.py with venv Python (foreground, Ctrl+C to stop)...'
    Push-Location $scriptDir
    try {
        & $venvPython -u $appPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    Write-Log "INFO  App exit code: $exitCode"
    exit $exitCode
}
catch {
    Write-Log ("ERROR Launcher exception: {0}" -f $_.Exception.Message)
    if ($_.ScriptStackTrace) {
        Write-Log ("ERROR Script stack: {0}" -f $_.ScriptStackTrace)
    }
    if ($_.Exception.InnerException) {
        Write-Log ("ERROR Inner exception: {0}" -f $_.Exception.InnerException.Message)
    }
    exit 1
}
